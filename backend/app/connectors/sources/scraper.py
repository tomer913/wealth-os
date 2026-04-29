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
_GH_ACTIONS_BASE = f"https://github.com/{_GITHUB_REPO}/actions/runs"


class CardScraperError(RuntimeError):
    """RuntimeError that carries a checkpoint dict so the DB run record gets
    github_run_url even when the workflow fails."""
    def __init__(self, message: str, checkpoint: dict | None = None):
        super().__init__(message)
        self.checkpoint = checkpoint or {}


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

    def _run_url(self, run_id: str) -> str:
        return f"{_GH_ACTIONS_BASE}/{run_id}"

    async def run(self) -> ConnectorResult:
        if not self._token:
            raise CardScraperError("GITHUB_TOKEN is not set — cannot trigger GitHub Actions")

        triggered_at = datetime.now(timezone.utc)
        run_id = await self._trigger_workflow(triggered_at)
        log.info("GitHub Actions triggered for %s, run_id: %s", self._company, run_id)

        outcome = await self._wait_for_completion(run_id)
        conclusion = outcome["conclusion"]
        run_url = outcome.get("url") or self._run_url(run_id)
        checkpoint = {"github_run_id": run_id, "github_run_url": run_url}

        if conclusion == "timed_out":
            raise CardScraperError(
                f"GitHub Actions run {run_id} timed out after {self.MAX_WAIT}s\n\nFull logs: {run_url}",
                checkpoint=checkpoint,
            )

        if conclusion != "success":
            detail = outcome.get("error") or f"Workflow concluded '{conclusion}'"
            raise CardScraperError(
                f"{detail}\n\nFull logs: {run_url}",
                checkpoint=checkpoint,
            )

        await self._run_processors()

        return ConnectorResult(checkpoint=checkpoint)

    async def _trigger_workflow(self, triggered_at: datetime) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://api.github.com/repos/{_GITHUB_REPO}"
                f"/actions/workflows/{_WORKFLOW_FILE}/dispatches",
                headers=self._headers,
                json={"ref": "main", "inputs": {"connector_id": str(self.connector_id or "")}},
            )
            if resp.status_code != 204:
                raise CardScraperError(
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
                raise CardScraperError("Triggered workflow but no run appeared in GitHub API")
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
                    error_detail = None
                    if conclusion != "success":
                        error_detail = await self._get_failure_reason(client, run_id)
                    return {
                        "conclusion": conclusion,
                        "url": run.get("html_url"),
                        "duration": elapsed,
                        "error": error_detail,
                    }

        return {
            "conclusion": "timed_out",
            "error": f"Workflow did not complete in {self.MAX_WAIT}s",
        }

    async def _get_failure_reason(self, client: httpx.AsyncClient, run_id: str) -> str:
        """Fetch the actual failure details from GitHub Actions job logs."""
        try:
            jobs_resp = await client.get(
                f"https://api.github.com/repos/{_GITHUB_REPO}/actions/runs/{run_id}/jobs",
                headers=self._headers,
            )
            jobs_data = jobs_resp.json()

            error_parts: list[str] = []

            for job in jobs_data.get("jobs", []):
                if job.get("conclusion") != "failure":
                    continue

                job_name = job.get("name", "unknown")

                # Record which step failed
                for step in job.get("steps", []):
                    if step.get("conclusion") == "failure":
                        error_parts.append(
                            f"Job '{job_name}' failed at step '{step.get('name', 'unknown')}'"
                        )

                # Fetch the raw log text for the failed job
                logs_resp = await client.get(
                    f"https://api.github.com/repos/{_GITHUB_REPO}"
                    f"/actions/jobs/{job['id']}/logs",
                    headers=self._headers,
                    follow_redirects=True,
                )

                if logs_resp.status_code == 200:
                    lines = logs_resp.text.strip().split("\n")

                    def strip_ts(line: str) -> str:
                        # GitHub log lines: "2024-01-01T00:00:00.0000000Z message"
                        parts = line.split(" ", 1)
                        return parts[1].strip() if len(parts) > 1 else line.strip()

                    clean = [strip_ts(ln) for ln in lines if ln.strip()]

                    keywords = ("error", "failed", "exception", "invalid", "unauthorized", "scrape failed")
                    error_lines = [ln for ln in clean if any(kw in ln.lower() for kw in keywords)]

                    if error_lines:
                        error_parts.extend(error_lines[-5:])

            return "\n".join(error_parts) if error_parts else "Run failed — no specific error captured in logs"

        except Exception as exc:
            log.warning("Could not fetch GitHub job logs for run %s: %s", run_id, exc)
            return "Run failed (log fetch unavailable)"

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
