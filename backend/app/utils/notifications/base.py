"""
Notification channel base classes and shared data structures.

All report data flows through ReportData — a pure data object with no
channel-specific formatting. NotificationChannel subclasses handle
formatting and transport for each channel independently.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ConnectorResult:
    name: str
    type: str
    status: str           # success | failed | skipped | no_data
    duration_ms: int
    transactions_created: int
    transactions_skipped: int
    prices_updated: int
    fx_rates_updated: int
    valuations_created: int
    assets_created: int
    error_message: Optional[str]


@dataclass
class TransactionSummary:
    source: str
    count: int
    volume: float
    currency: str
    types: list


@dataclass
class BudgetSummary:
    month: str                   # e.g. "May 2026"
    total_income: float
    total_income_planned: float
    total_expenses: float
    total_expenses_planned: float
    top_categories: list         # [{"name": str, "amount": float}]
    new_today: int
    auto_classified: int
    ai_classified: int
    needs_review: int


@dataclass
class PortfolioSummary:
    total_value_ils: float
    daily_change_ils: float
    daily_change_pct: float
    top_gainer_symbol: str
    top_gainer_pct: float
    top_loser_symbol: str
    top_loser_pct: float


@dataclass
class SystemSummary:
    total_connectors: int
    succeeded: int
    failed: int
    skipped: int
    snapshot_rebuilt_at: str
    total_duration_seconds: float


@dataclass
class ReportData:
    """Pure data object — no formatting, no channel-specific logic."""
    date: str
    time: str
    portfolio_id: str
    connectors: list
    transactions: list
    needs_review_count: int
    budget: BudgetSummary
    portfolio: PortfolioSummary
    system: SystemSummary


class NotificationChannel(ABC):
    """Abstract base for all notification channels."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if required env vars are set for this channel."""

    @abstractmethod
    def format(self, report: ReportData) -> Any:
        """Format ReportData into a channel-specific payload (str or dict)."""

    @abstractmethod
    async def send(self, payload: Any) -> bool:
        """Send the formatted payload. Return True on success."""

    async def deliver(self, report: ReportData) -> bool:
        """Full pipeline: check → format → send. Override only if needed."""
        if not self.is_configured():
            return False
        payload = self.format(report)
        return await self.send(payload)
