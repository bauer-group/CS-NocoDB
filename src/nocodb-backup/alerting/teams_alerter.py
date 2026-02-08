"""
NocoDB Backup - Microsoft Teams Alerter
"""

import json
from typing import TYPE_CHECKING

import httpx

from alerting.base import Alerter, BackupAlert
from ui.console import backup_logger, format_size

if TYPE_CHECKING:
    from config import Settings


class TeamsAlerter(Alerter):
    """Sends alerts via Microsoft Teams webhook."""

    def is_configured(self) -> bool:
        """Check if Teams is configured."""
        return bool(self.settings.teams_webhook_url)

    def get_configuration_errors(self) -> list[str]:
        """Get configuration errors."""
        if not self.settings.teams_webhook_url:
            return ["Teams: TEAMS_WEBHOOK_URL not configured"]
        return []

    def send(self, alert: BackupAlert) -> bool:
        """Send Teams alert."""
        try:
            payload = self._build_payload(alert)

            response = httpx.post(
                self.settings.teams_webhook_url,
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()

            backup_logger.debug("Teams alert sent")
            return True

        except Exception as e:
            backup_logger.error(f"Failed to send Teams alert: {e}")
            return False

    def _build_payload(self, alert: BackupAlert) -> dict:
        """Build Teams adaptive card payload."""
        status_color = {
            "success": "good",
            "warning": "warning",
            "error": "attention",
        }
        color = status_color.get(alert.status, "default")

        # Build facts
        facts = [
            {"title": "Instance", "value": alert.instance_name},
            {"title": "Backup ID", "value": alert.backup_id},
            {"title": "Status", "value": alert.status.upper()},
        ]

        if alert.bases_count > 0:
            facts.extend([
                {"title": "Bases", "value": str(alert.bases_count)},
                {"title": "Tables", "value": str(alert.tables_count)},
                {"title": "Records", "value": str(alert.records_count)},
            ])

        if alert.database_dump_size > 0:
            facts.append({"title": "Database Dump", "value": format_size(alert.database_dump_size)})

        if alert.total_size > 0:
            facts.append({"title": "Total Size", "value": format_size(alert.total_size)})

        facts.append({"title": "Duration", "value": f"{alert.duration_seconds:.1f}s"})

        if alert.local_path:
            facts.append({"title": "Local Path", "value": alert.local_path})
        if alert.s3_path:
            facts.append({"title": "S3 Path", "value": alert.s3_path})

        # Build message card
        card = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": f"NocoDB Backup - {alert.status.upper()}",
                                "weight": "bolder",
                                "size": "large",
                                "color": color,
                            },
                            {
                                "type": "TextBlock",
                                "text": alert.message,
                                "wrap": True,
                            },
                            {
                                "type": "FactSet",
                                "facts": facts,
                            },
                        ],
                    },
                }
            ],
        }

        # Add errors if present
        if alert.error_messages:
            card["attachments"][0]["content"]["body"].append({
                "type": "TextBlock",
                "text": "**Errors:**",
                "weight": "bolder",
                "color": "attention",
            })
            for error in alert.error_messages:
                card["attachments"][0]["content"]["body"].append({
                    "type": "TextBlock",
                    "text": f"- {error}",
                    "wrap": True,
                    "color": "attention",
                })

        return card
