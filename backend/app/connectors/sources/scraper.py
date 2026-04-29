"""
ScraperConnector — triggers the GitHub Actions credit card scraper,
polls until completion, then chains BankProcessor + BudgetProcessor.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx

from app.connectors.base import BaseConnector, ConnectorResult
from app.connectors.registry import register

log = logging.getLogger(__name__)


@register
class ScraperConnector(BaseConnector):
    """
    Controls the GitHub Actions credit card scraper.
    Triggers workflow, waits for completion (up to 15 min), then chains processors.
    Raises on failure so _run_single_connector records status = "failed".
    """

    CONNECTOR_TYPE = "scraper"
    DISPLAY_NAME = "Credit Card Scraper"
    DESCRIPTION = "Scrapes Israeli credit cards via GitHub Actions (Isracard, Cal, Max, Amex…)"
    CONFIG_FIELDS = [
        {
            "key": "cards",
            "label": "Active cards",
            "type": "text",
            "default": "isracard",
            "hint": "Comma-separated card types: isracard, cal, max, leumi_card, amex",
        },
    ]
    WRITES_RAW = False  # overrides run() directly; scraper writes via /ingest endpoint

    GITHUB_REPO = "tomer913/wealth-os"
    WORKFLOW_FILE = "scrape-cards.yml"
    POLL_INTERVAL = 30   # seconds between status polls
    MAX_WAIT = 900        # 15 minutes total timeout

    @property
    def _token(self) -> str:
        return os.getenv("GITHUB_TOKEN", "")

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github.v3+json",
        }

    async def run(self) -> ConnectorResult:
        if not self._token:
            raise RuntimeError("GITHUB_TOKEN is not set — cannot trigger GitHub Actions")

        triggered_at = datetime.now(timezone.utc)
        run_id = await self._trigger_workflow(triggered_at)

        log.info("GitHub Actions triggered, run_id: %s", run_id)

        outcome = await self._wait_for_completion(run_id)
        conclusion = outcome["conclusion"]
        run_url = outcome.get("url", "")

        if conclusion == "timed_out":
            raise RuntimeError(
                f"GitHub Actions run {run_id} did not complete in {self.MAX_WAIT}s — {run_url}"
            )

        if conclusion != "success":
            raise RuntimeError(
                f"GitHub Actions run {run_id} concluded '{conclusion}' — {run_url}"
            )

        await self._run_processors()

        return ConnectorResult(
            checkpoint={"github_run_id": run_id, "github_run_url": run_url},
        )

    async def _trigger_workflow(self, triggered_at: datetime) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://api.github.com/repos/{self.GITHUB_REPO}"
                f"/actions/workflows/{self.WORKFLOW_FILE}/dispatches",
                headers=self._headers,
                json={"ref": "main"},
            )
            if resp.status_code != 204:
                raise RuntimeError(f"Failed to trigger GitHub Actions: {resp.status_code} {resp.text}")

            # Give GitHub a moment to register the new run
            await asyncio.sleep(5)

            runs_resp = await client.get(
                f"https://api.github.com/repos/{self.GITHUB_REPO}"
                f"/actions/runs?workflow_id={self.WORKFLOW_FILE}&per_page=5",
                headers=self._headers,
            )
            runs_data = runs_resp.json()

            # Prefer the run created at or after our trigger time
            for run in runs_data.get("workflow_runs", []):
                created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
                if created >= triggered_at:
                    return str(run["id"])

            # Fallback to most recent if timestamp filtering finds nothing
            workflow_runs = runs_data.get("workflow_runs", [])
            if not workflow_runs:
                raise RuntimeError("Triggered workflow but no run appeared in GitHub API")
            return str(workflow_runs[0]["id"])

    async def _wait_for_completion(self, run_id: str) -> dict:
        elapsed = 0
        async with httpx.AsyncClient(timeout=30) as client:
            while elapsed < self.MAX_WAIT:
                await asyncio.sleep(self.POLL_INTERVAL)
                elapsed += self.POLL_INTERVAL

                resp = await client.get(
                    f"https://api.github.com/repos/{self.GITHUB_REPO}/actions/runs/{run_id}",
                    headers=self._headers,
                )
                run = resp.json()
                status = run.get("status")
                conclusion = run.get("conclusion")

                log.info(
                    "GitHub run %s: %s/%s (%ds elapsed)",
                    run_id, status, conclusion, elapsed,
                )

                if status == "completed":
                    return {"conclusion": conclusion, "url": run.get("html_url"), "duration": elapsed}

        return {"conclusion": "timed_out"}

    async def _run_processors(self):
        log.info("Scraper complete — running bank + budget processors for portfolio %s", self.portfolio_id)

        from app.processors.bank_processor import BankProcessor
        from app.processors.budget_processor import BudgetProcessor

        bank = BankProcessor()
        await bank.run(self.portfolio_id, triggered_by="scraper")
        log.info("Bank processor complete")

        budget = BudgetProcessor()
        await budget.run(self.portfolio_id, triggered_by="scraper")
        log.info("Budget processor complete")
