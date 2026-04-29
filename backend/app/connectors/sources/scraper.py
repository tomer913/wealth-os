"""
Card scraper connectors — one per Israeli credit card company.
Each triggers the GitHub Actions workflow for its specific company,
polls to completion, then chains BankProcessor + BudgetProcessor.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx

from app.connectors.base import BaseConnector, ConnectorResult
from app.connectors.registry import register

log = logging.getLogger(__name__)

_GITHUB_REPO = "tomer913/wealth-os"
_WORKFLOW_FILE = "scrape-cards.yml"


class CardScraperConnector(BaseConnector):
    """
    Base for all per-company card scrapers.
    Subclasses set COMPANY and CONNECTOR_TYPE; everything else is shared.
    """

    WRITES_RAW = False
    COMPANY: str = ""
    CONFIG_FIELDS = []

    POLL_INTERVAL = 30
    MAX_WAIT = 900

    @property
    def _company(self) -> str:
        return self.config.get("company", self.COMPANY)

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
        log.info("GitHub Actions triggered for %s, run_id: %s", self._company, run_id)

        outcome = await self._wait_for_completion(run_id)
        conclusion = outcome["conclusion"]
        run_url = outcome.get("url", "")

        if conclusion == "timed_out":
            raise RuntimeError(
                f"GitHub Actions run {run_id} timed out after {self.MAX_WAIT}s"
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
                f"https://api.github.com/repos/{_GITHUB_REPO}"
                f"/actions/workflows/{_WORKFLOW_FILE}/dispatches",
                headers=self._headers,
                json={"ref": "main", "inputs": {"company": self._company}},
            )
            if resp.status_code != 204:
                raise RuntimeError(
                    f"Failed to trigger GitHub Actions: {resp.status_code} {resp.text}"
                )

            await asyncio.sleep(5)

            runs_resp = await client.get(
                f"https://api.github.com/repos/{_GITHUB_REPO}"
                f"/actions/runs?workflow_id={_WORKFLOW_FILE}&per_page=5",
                headers=self._headers,
            )
            runs_data = runs_resp.json()

            for run in runs_data.get("workflow_runs", []):
                created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
                if created >= triggered_at:
                    return str(run["id"])

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
                    f"https://api.github.com/repos/{_GITHUB_REPO}/actions/runs/{run_id}",
                    headers=self._headers,
                )
                run = resp.json()
                status = run.get("status")
                conclusion = run.get("conclusion")

                log.info(
                    "GitHub run %s [%s]: %s/%s (%ds elapsed)",
                    run_id, self._company, status, conclusion, elapsed,
                )

                if status == "completed":
                    return {
                        "conclusion": conclusion,
                        "url": run.get("html_url"),
                        "duration": elapsed,
                    }

        return {"conclusion": "timed_out"}

    async def _run_processors(self):
        log.info(
            "Scraper complete — running bank + budget processors for portfolio %s",
            self.portfolio_id,
        )
        from app.processors.bank_processor import BankProcessor
        from app.processors.budget_processor import BudgetProcessor

        bank = BankProcessor()
        await bank.run(self.portfolio_id, triggered_by="scraper")
        log.info("Bank processor complete")

        budget = BudgetProcessor()
        await budget.run(self.portfolio_id, triggered_by="scraper")
        log.info("Budget processor complete")


@register
class IsracardScraperConnector(CardScraperConnector):
    CONNECTOR_TYPE = "isracard_scraper"
    DISPLAY_NAME = "Isracard"
    DESCRIPTION = "Scrapes Isracard credit cards via GitHub Actions"
    COMPANY = "isracard"


@register
class CalScraperConnector(CardScraperConnector):
    CONNECTOR_TYPE = "cal_scraper"
    DISPLAY_NAME = "Cal"
    DESCRIPTION = "Scrapes Cal (Visa Cal) credit cards via GitHub Actions"
    COMPANY = "cal"


@register
class MaxScraperConnector(CardScraperConnector):
    CONNECTOR_TYPE = "max_scraper"
    DISPLAY_NAME = "Max"
    DESCRIPTION = "Scrapes Max credit cards via GitHub Actions"
    COMPANY = "max"


@register
class LeumiCardScraperConnector(CardScraperConnector):
    CONNECTOR_TYPE = "leumi_card_scraper"
    DISPLAY_NAME = "Leumi Card"
    DESCRIPTION = "Scrapes Leumi Card credit cards via GitHub Actions"
    COMPANY = "leumi_card"


@register
class AmexScraperConnector(CardScraperConnector):
    CONNECTOR_TYPE = "amex_scraper"
    DISPLAY_NAME = "Amex Israel"
    DESCRIPTION = "Scrapes American Express Israel credit cards via GitHub Actions"
    COMPANY = "amex"
