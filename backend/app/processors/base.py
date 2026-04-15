"""
BaseProcessor — abstract base for all raw_transaction consumers.

Flow:
  1. Load checkpoint from service_checkpoints (NULL = replay from beginning)
  2. Fetch raw_transactions WHERE id > checkpoint ORDER BY id ASC in batches of 500
  3. Call process_batch() on each batch
  4. After all batches succeed, advance checkpoint (skipped for date-range reruns)
  5. Write ProcessorRun audit record

Date-range rerun mode (date_from / date_to provided):
  - Queries raw_transactions WHERE raw_date BETWEEN dates AND id > cursor
  - Does NOT read or advance the checkpoint
  - ProcessorRun.triggered_by = 'date_range_rerun'

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
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import cast, Date as SADate, select
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
        run_id: Optional[UUID] = None,
        date_from: Optional[date_type] = None,
        date_to: Optional[date_type] = None,
    ):
        """
        Run the processor for a single portfolio.
        Manages checkpoint, batching, and audit record.

        If run_id is supplied the caller already created a ProcessorRun with
        status='pending' — this method updates that record to 'running' rather
        than inserting a new one.  This lets the trigger endpoint return the
        run_id immediately so the frontend can poll for it.

        If date_from / date_to are supplied, runs in date-range mode:
        - Ignores checkpoint — queries all rows in the date range
        - Does NOT advance checkpoint after run
        - Sets triggered_by = 'date_range_rerun' on the ProcessorRun

        Returns the ProcessorRun ORM object.
        """
        from app.database import AsyncSessionLocal
        from app.models.raw_layer import ProcessorRun, RawTransaction, ServiceCheckpoint

        is_date_range = date_from is not None or date_to is not None
        actual_run_id = run_id or uuid.uuid4()
        started_at = datetime.now(timezone.utc)

        if is_date_range:
            triggered_by = "date_range_rerun"

        async with AsyncSessionLocal() as db:
            # Load checkpoint (ignored in date-range mode)
            checkpoint = await db.get(
                ServiceCheckpoint,
                {"service_name": self.processor_name, "portfolio_id": portfolio_id},
            )
            checkpoint_from: Optional[UUID] = (
                None if is_date_range
                else (checkpoint.last_raw_id if checkpoint else None)
            )

            # Use pre-created record if run_id was provided, else create fresh
            proc_run = await db.get(ProcessorRun, actual_run_id) if run_id else None
            if proc_run is None:
                proc_run = ProcessorRun(
                    id=actual_run_id,
                    processor_name=self.processor_name,
                    portfolio_id=portfolio_id,
                    triggered_by=triggered_by,
                )
                db.add(proc_run)

            proc_run.status = "running"
            proc_run.triggered_by = triggered_by
            proc_run.checkpoint_from = checkpoint_from
            proc_run.started_at = started_at
            proc_run.date_from = date_from
            proc_run.date_to = date_to
            await db.flush()

            total_read = 0
            total_written = 0
            total_skipped = 0
            # id cursor — starts from checkpoint (or beginning for date-range)
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
                    # Date-range filter (cast raw_date to DATE for timezone-safe comparison)
                    if date_from is not None:
                        q = q.where(cast(RawTransaction.raw_date, SADate) >= date_from)
                    if date_to is not None:
                        q = q.where(cast(RawTransaction.raw_date, SADate) <= date_to)
                    # id cursor for pagination (works in both modes)
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

                # Advance checkpoint ONLY for normal runs (not date-range reruns)
                if not is_date_range and last_id is not None and last_id != checkpoint_from:
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
                    "%s portfolio=%s%s — read=%d written=%d skipped=%d (%dms)",
                    self.processor_name, portfolio_id,
                    f" date_range={date_from}..{date_to}" if is_date_range else "",
                    total_read, total_written, total_skipped,
                    proc_run.duration_ms,
                )

            except Exception as e:
                await db.rollback()
                async with AsyncSessionLocal() as err_db:
                    proc_run = await err_db.get(ProcessorRun, actual_run_id)
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
        Write to domain tables and return counts.
        Must be idempotent — skip rows where reviewed_at IS NOT NULL.
        """
        ...
