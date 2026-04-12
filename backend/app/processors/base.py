"""
BaseProcessor — abstract base for all raw_transaction consumers.

Flow:
  1. Load checkpoint from service_checkpoints (NULL = replay from beginning)
  2. Fetch raw_transactions WHERE id > checkpoint ORDER BY id ASC in batches of 500
  3. Call process_batch() on each batch
  4. After all batches succeed, advance checkpoint
  5. Write ProcessorRun audit record

Subclasses implement:
  - processor_name: str
  - sources: list[str]
  - process_batch(rows, db, portfolio_id) -> ProcessResult
"""
import logging
import traceback
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

BATCH_SIZE = 500


@dataclass
class ProcessResult:
    rows_written: int = 0
    rows_skipped: int = 0
    warnings: List[str] = field(default_factory=list)


class BaseProcessor(ABC):
    processor_name: str = "base_processor"
    sources: List[str] = []

    async def run(
        self,
        portfolio_id: UUID,
        triggered_by: str = "scheduler",
    ):
        """
        Run the processor for a single portfolio.
        Manages checkpoint, batching, and audit record.
        Returns the ProcessorRun ORM object.
        """
        from app.database import AsyncSessionLocal
        from app.models.raw_layer import ProcessorRun, RawTransaction, ServiceCheckpoint

        run_id = uuid.uuid4()
        started_at = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as db:
            # Load or create checkpoint
            checkpoint = await db.get(
                ServiceCheckpoint,
                {"service_name": self.processor_name, "portfolio_id": portfolio_id},
            )
            checkpoint_from: Optional[UUID] = checkpoint.last_raw_id if checkpoint else None

            # Create ProcessorRun audit record
            proc_run = ProcessorRun(
                id=run_id,
                processor_name=self.processor_name,
                portfolio_id=portfolio_id,
                status="running",
                triggered_by=triggered_by,
                checkpoint_from=checkpoint_from,
                started_at=started_at,
            )
            db.add(proc_run)
            await db.flush()

            total_read = 0
            total_written = 0
            total_skipped = 0
            last_id: Optional[UUID] = checkpoint_from

            try:
                # Batch loop
                while True:
                    q = (
                        select(RawTransaction)
                        .where(
                            RawTransaction.portfolio_id == portfolio_id,
                            RawTransaction.source.in_(self.sources),
                        )
                        .order_by(RawTransaction.id.asc())
                        .limit(BATCH_SIZE)
                    )
                    if last_id is not None:
                        q = q.where(RawTransaction.id > last_id)

                    rows = (await db.execute(q)).scalars().all()
                    if not rows:
                        break

                    result = await self.process_batch(rows, db, portfolio_id)
                    total_read += len(rows)
                    total_written += result.rows_written
                    total_skipped += result.rows_skipped
                    last_id = rows[-1].id

                    if len(rows) < BATCH_SIZE:
                        break

                # Advance checkpoint
                if last_id is not None and last_id != checkpoint_from:
                    if checkpoint is None:
                        checkpoint = ServiceCheckpoint(
                            service_name=self.processor_name,
                            portfolio_id=portfolio_id,
                        )
                        db.add(checkpoint)
                    checkpoint.last_raw_id = last_id
                    checkpoint.last_processed_at = datetime.now(timezone.utc)

                finished_at = datetime.now(timezone.utc)
                proc_run.status = "success"
                proc_run.finished_at = finished_at
                proc_run.duration_ms = int(
                    (finished_at - started_at).total_seconds() * 1000
                )
                proc_run.rows_read = total_read
                proc_run.rows_written = total_written
                proc_run.rows_skipped = total_skipped
                proc_run.checkpoint_to = last_id

                await db.commit()
                log.info(
                    "%s portfolio=%s — read=%d written=%d skipped=%d (%dms)",
                    self.processor_name, portfolio_id,
                    total_read, total_written, total_skipped,
                    proc_run.duration_ms,
                )

            except Exception as e:
                await db.rollback()
                async with AsyncSessionLocal() as err_db:
                    proc_run = await err_db.get(ProcessorRun, run_id)
                    if proc_run:
                        finished_at = datetime.now(timezone.utc)
                        proc_run.status = "failed"
                        proc_run.finished_at = finished_at
                        proc_run.duration_ms = int(
                            (finished_at - started_at).total_seconds() * 1000
                        )
                        proc_run.rows_read = total_read
                        proc_run.rows_written = total_written
                        proc_run.rows_skipped = total_skipped
                        proc_run.error_message = str(e)
                        proc_run.error_traceback = traceback.format_exc()
                        await err_db.commit()
                log.error("%s failed for portfolio %s: %s", self.processor_name, portfolio_id, e)
                raise

        return proc_run

    async def reset_checkpoint(self, portfolio_id: UUID) -> None:
        """Reset checkpoint to NULL so the next run replays from the beginning."""
        from app.database import AsyncSessionLocal
        from app.models.raw_layer import ServiceCheckpoint

        async with AsyncSessionLocal() as db:
            checkpoint = await db.get(
                ServiceCheckpoint,
                {"service_name": self.processor_name, "portfolio_id": portfolio_id},
            )
            if checkpoint:
                checkpoint.last_raw_id = None
                checkpoint.last_processed_at = None
                await db.commit()
                log.info(
                    "Checkpoint reset for %s / portfolio %s",
                    self.processor_name, portfolio_id,
                )

    @abstractmethod
    async def process_batch(
        self,
        rows: list,
        db: AsyncSession,
        portfolio_id: UUID,
    ) -> ProcessResult:
        """
        Process a batch of RawTransaction rows.
        Write to domain tables (transactions, etc.) and return counts.
        Must be idempotent — dedup by external_reference_id or similar.
        """
        ...
