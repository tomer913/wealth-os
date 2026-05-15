"""
Notification router — delivers a ReportData to all configured channels.

To add a new channel:
1. Create backend/app/utils/notifications/yourchannel.py
2. Implement is_configured(), format(), send()
3. Import and add to CHANNELS below
4. Add env vars to Railway + CLAUDE.md
Zero changes to report logic or other channels needed.
"""
import logging

from .notifications.base import ReportData
from .notifications.email import EmailChannel
from .notifications.slack import SlackChannel
from .notifications.telegram import TelegramChannel

log = logging.getLogger(__name__)

CHANNELS = [
    TelegramChannel(),
    EmailChannel(),
    SlackChannel(),
]


async def deliver_report(report: ReportData) -> None:
    """Send report to ALL configured channels. Errors in one channel don't block others."""
    delivered = 0
    for channel in CHANNELS:
        if not channel.is_configured():
            continue
        channel_name = channel.__class__.__name__
        try:
            ok = await channel.deliver(report)
            if ok:
                log.info("Report delivered via %s", channel_name)
                delivered += 1
            else:
                log.warning("Report delivery returned False via %s", channel_name)
        except NotImplementedError:
            log.debug("%s not yet implemented — skipping", channel_name)
        except Exception as exc:
            log.error("Report delivery failed via %s: %s", channel_name, exc)

    if delivered == 0:
        log.info("No notification channels configured — report not sent")
