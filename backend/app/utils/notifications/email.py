"""
Email notification channel (stub — ready to implement via Resend).

Requires env vars:
  RESEND_API_KEY    — from resend.com
  REPORT_EMAIL_TO   — recipient address (e.g. you@example.com)
  REPORT_EMAIL_FROM — verified sender (e.g. reports@yourdomain.com)
"""
import os

from .base import NotificationChannel, ReportData


class EmailChannel(NotificationChannel):

    def is_configured(self) -> bool:
        return bool(os.getenv("RESEND_API_KEY") and os.getenv("REPORT_EMAIL_TO"))

    def format(self, report: ReportData) -> dict:
        # TODO: build HTML email from ReportData
        return {
            "subject": f"Wealth OS Daily Report — {report.date}",
            "html": f"<p>Report for {report.date}</p>",
        }

    async def send(self, payload: dict) -> bool:
        # TODO: POST to Resend API
        # import httpx, os
        # async with httpx.AsyncClient() as client:
        #     await client.post(
        #         "https://api.resend.com/emails",
        #         headers={"Authorization": f"Bearer {os.getenv('RESEND_API_KEY')}"},
        #         json={
        #             "from": os.getenv("REPORT_EMAIL_FROM"),
        #             "to": [os.getenv("REPORT_EMAIL_TO")],
        #             "subject": payload["subject"],
        #             "html": payload["html"],
        #         },
        #     )
        raise NotImplementedError("EmailChannel.send() not yet implemented")
