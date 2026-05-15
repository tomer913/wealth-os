"""
Telegram notification channel.

Requires env vars:
  TELEGRAM_BOT_TOKEN  — from @BotFather
  TELEGRAM_CHAT_ID    — your personal chat ID (send /start to @userinfobot)
"""
import logging
import os

import httpx

from .base import NotificationChannel, ReportData

log = logging.getLogger(__name__)

_STATUS_ICON = {
    "success": "✅",
    "failed":  "❌",
    "skipped": "⚠️",
    "no_data": "⏭️",
}


class TelegramChannel(NotificationChannel):

    def is_configured(self) -> bool:
        return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))

    def format(self, report: ReportData) -> str:
        lines = []

        lines.append("🤖 <b>Wealth OS — Daily Report</b>")
        lines.append(f"📅 {report.date} | {report.time} IL\n")

        # ── Connectors ────────────────────────────────────────────────────────
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("🔌 <b>CONNECTORS</b>")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        for c in report.connectors:
            icon = _STATUS_ICON.get(c.status, "❓")
            dur = f"({c.duration_ms / 1000:.1f}s)" if c.duration_ms else ""
            lines.append(f"{icon} <b>{c.name}</b> {dur}")
            if c.status == "success":
                parts = []
                if c.transactions_created: parts.append(f"{c.transactions_created} tx")
                if c.transactions_skipped: parts.append(f"{c.transactions_skipped} skipped")
                if c.prices_updated:       parts.append(f"{c.prices_updated} prices")
                if c.fx_rates_updated:     parts.append(f"{c.fx_rates_updated} fx")
                if c.valuations_created:   parts.append(f"{c.valuations_created} valuations")
                if c.assets_created:       parts.append(f"{c.assets_created} new assets")
                lines.append(f"   └ {' | '.join(parts) or 'no new data'}")
            elif c.status == "failed":
                lines.append(f"   └ FAILED: {c.error_message}")

        # ── Transactions ─────────────────────────────────────────────────────
        lines.append("\n━━━━━━━━━━━━━━━━━━━━")
        lines.append("💳 <b>TRANSACTIONS</b>")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        total_new = sum(t.count for t in report.transactions)
        if report.transactions:
            for t in report.transactions:
                types_str = " | ".join(t.types[:3])
                lines.append(f"<code>{t.source:<15}</code> {t.count} new | {t.currency}{t.volume:,.0f}")
                if types_str:
                    lines.append(f"   └ {types_str}")
        else:
            lines.append("No new transactions today")
        lines.append(f"\nTotal new: {total_new}")
        if report.needs_review_count:
            lines.append(f"⚠️ Needs review: {report.needs_review_count}")

        # ── Budget ────────────────────────────────────────────────────────────
        b = report.budget
        lines.append(f"\n━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📊 <b>BUDGET — {b.month}</b>")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"💰 Income:   ₪{b.total_income:,.0f} / ₪{b.total_income_planned:,.0f}")
        lines.append(f"💸 Expenses: ₪{b.total_expenses:,.0f} / ₪{b.total_expenses_planned:,.0f}")
        if b.top_categories:
            lines.append("Top categories:")
            for cat in b.top_categories[:3]:
                lines.append(f"  • {cat['name']}: ₪{cat['amount']:,.0f}")
        lines.append(
            f"New today: {b.new_today} | "
            f"Auto: {b.auto_classified} | "
            f"🤖 AI: {b.ai_classified}"
        )
        if b.needs_review:
            lines.append(f"⚠️ Needs review: {b.needs_review}")

        # ── Portfolio ─────────────────────────────────────────────────────────
        p = report.portfolio
        lines.append("\n━━━━━━━━━━━━━━━━━━━━")
        lines.append("📈 <b>PORTFOLIO</b>")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"💰 Total: ₪{p.total_value_ils:,.0f}")
        change_icon = "📈" if p.daily_change_ils >= 0 else "📉"
        sign = "+" if p.daily_change_ils >= 0 else ""
        lines.append(
            f"{change_icon} Today: {sign}₪{p.daily_change_ils:,.0f} "
            f"({sign}{p.daily_change_pct:.2f}%)"
        )
        if p.top_gainer_symbol:
            lines.append(f"🏆 Top gainer: {p.top_gainer_symbol} +{p.top_gainer_pct:.1f}%")
        if p.top_loser_symbol:
            lines.append(f"📉 Top loser:  {p.top_loser_symbol} {p.top_loser_pct:.1f}%")

        # ── System ────────────────────────────────────────────────────────────
        s = report.system
        lines.append("\n━━━━━━━━━━━━━━━━━━━━")
        lines.append("⚙️ <b>SYSTEM</b>")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"Connectors: {s.succeeded}✅ {s.failed}❌ {s.skipped}⚠️")
        lines.append(f"Snapshot:   rebuilt at {s.snapshot_rebuilt_at}")
        lines.append(f"Run time:   {s.total_duration_seconds / 60:.1f}m")

        return "\n".join(lines)

    async def send(self, payload: str) -> bool:
        token   = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        # Split at 4000 chars to stay under Telegram's 4096 limit
        chunks = [payload[i:i + 4000] for i in range(0, len(payload), 4000)]
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                for chunk in chunks:
                    resp = await client.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"},
                    )
                    resp.raise_for_status()
            log.info("Telegram report delivered (%d chunk(s))", len(chunks))
            return True
        except Exception as exc:
            log.error("Telegram send failed: %s", exc)
            return False
