"""
Slack notification channel (stub — ready to implement via Incoming Webhooks).

Requires env vars:
  SLACK_WEBHOOK_URL — Incoming Webhook URL from api.slack.com/apps
"""
import os

from .base import NotificationChannel, ReportData


class SlackChannel(NotificationChannel):

    def is_configured(self) -> bool:
        return bool(os.getenv("SLACK_WEBHOOK_URL"))

    def format(self, report: ReportData) -> dict:
        # TODO: build Slack Block Kit payload from ReportData
        # See https://api.slack.com/block-kit
        return {
            "text": f"Wealth OS Daily Report — {report.date}",
            "blocks": [],
        }

    async def send(self, payload: dict) -> bool:
        # TODO: POST to SLACK_WEBHOOK_URL
        # import httpx, os
        # async with httpx.AsyncClient() as client:
        #     await client.post(os.getenv("SLACK_WEBHOOK_URL"), json=payload)
        raise NotImplementedError("SlackChannel.send() not yet implemented")
