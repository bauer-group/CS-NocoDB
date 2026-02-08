"""
NocoDB Backup - Email Alerter
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

from alerting.base import Alerter, BackupAlert
from ui.console import backup_logger, format_size

if TYPE_CHECKING:
    from config import Settings


class EmailAlerter(Alerter):
    """Sends alerts via email."""

    def is_configured(self) -> bool:
        """Check if email is configured."""
        return bool(
            self.settings.smtp_host
            and self.settings.smtp_from
            and self.settings.smtp_to
        )

    def get_configuration_errors(self) -> list[str]:
        """Get configuration errors."""
        errors = []
        if not self.settings.smtp_host:
            errors.append("Email: SMTP_HOST not configured")
        if not self.settings.smtp_from:
            errors.append("Email: SMTP_SENDER not configured")
        if not self.settings.smtp_to:
            errors.append("Email: SMTP_TO not configured")
        return errors

    def send(self, alert: BackupAlert) -> bool:
        """Send email alert."""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = self._get_subject(alert)
            msg["From"] = f"{self.settings.smtp_from_name} <{self.settings.smtp_from}>"
            msg["To"] = self.settings.smtp_to

            # Create plain text and HTML versions
            text = self._get_plain_text(alert)
            html = self._get_html(alert)

            msg.attach(MIMEText(text, "plain"))
            msg.attach(MIMEText(html, "html"))

            # Connect and send
            if self.settings.smtp_ssl:
                server = smtplib.SMTP_SSL(
                    self.settings.smtp_host,
                    self.settings.smtp_port,
                )
            else:
                server = smtplib.SMTP(
                    self.settings.smtp_host,
                    self.settings.smtp_port,
                )
                if self.settings.smtp_tls:
                    server.starttls()

            if self.settings.smtp_user and self.settings.smtp_password:
                server.login(self.settings.smtp_user, self.settings.smtp_password)

            recipients = self.settings.get_smtp_recipients()
            server.sendmail(self.settings.smtp_from, recipients, msg.as_string())
            server.quit()

            backup_logger.debug(f"Email sent to {self.settings.smtp_to}")
            return True

        except Exception as e:
            backup_logger.error(f"Failed to send email: {e}")
            return False

    def _get_subject(self, alert: BackupAlert) -> str:
        """Generate email subject."""
        status_emoji = {"success": "+", "warning": "!", "error": "X"}
        emoji = status_emoji.get(alert.status, "?")
        return f"[{emoji}] NocoDB Backup - {alert.instance_name} - {alert.status.upper()}"

    def _get_plain_text(self, alert: BackupAlert) -> str:
        """Generate plain text body."""
        lines = [
            f"NocoDB Backup Report",
            f"=" * 40,
            f"Instance: {alert.instance_name}",
            f"Backup ID: {alert.backup_id}",
            f"Status: {alert.status.upper()}",
            f"Message: {alert.message}",
            "",
        ]

        if alert.bases_count > 0:
            lines.append(f"Bases: {alert.bases_count}")
            lines.append(f"Tables: {alert.tables_count}")
            lines.append(f"Records: {alert.records_count}")

        if alert.database_dump_size > 0:
            lines.append(f"Database Dump: {format_size(alert.database_dump_size)}")

        if alert.file_backup_size > 0:
            lines.append(f"Data Files: {format_size(alert.file_backup_size)}")

        if alert.total_size > 0:
            lines.append(f"Total Size: {format_size(alert.total_size)}")

        lines.append(f"Duration: {alert.duration_seconds:.1f}s")
        lines.append("")

        if alert.local_path:
            lines.append(f"Local Path: {alert.local_path}")
        if alert.s3_path:
            lines.append(f"S3 Path: {alert.s3_path}")

        if alert.error_messages:
            lines.append("")
            lines.append("Errors:")
            for error in alert.error_messages:
                lines.append(f"  - {error}")

        return "\n".join(lines)

    def _get_html(self, alert: BackupAlert) -> str:
        """Generate HTML body."""
        status_color = {
            "success": "#28a745",
            "warning": "#ffc107",
            "error": "#dc3545",
        }
        color = status_color.get(alert.status, "#6c757d")

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background-color: {color}; color: white; padding: 15px; text-align: center;">
                <h2 style="margin: 0;">NocoDB Backup - {alert.status.upper()}</h2>
            </div>
            <div style="padding: 20px; background-color: #f8f9fa;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;"><strong>Instance</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">{alert.instance_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;"><strong>Backup ID</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">{alert.backup_id}</td>
                    </tr>
        """

        if alert.bases_count > 0:
            html += f"""
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;"><strong>Bases</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">{alert.bases_count}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;"><strong>Tables</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">{alert.tables_count}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;"><strong>Records</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">{alert.records_count}</td>
                    </tr>
            """

        if alert.database_dump_size > 0:
            html += f"""
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;"><strong>Database Dump</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">{format_size(alert.database_dump_size)}</td>
                    </tr>
            """

        if alert.file_backup_size > 0:
            html += f"""
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;"><strong>Data Files</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">{format_size(alert.file_backup_size)}</td>
                    </tr>
            """

        if alert.total_size > 0:
            html += f"""
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;"><strong>Total Size</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">{format_size(alert.total_size)}</td>
                    </tr>
            """

        html += f"""
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;"><strong>Duration</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">{alert.duration_seconds:.1f}s</td>
                    </tr>
                </table>
        """

        if alert.error_messages:
            html += """
                <div style="margin-top: 20px; padding: 10px; background-color: #f8d7da; border-radius: 5px;">
                    <strong>Errors:</strong>
                    <ul style="margin: 10px 0;">
            """
            for error in alert.error_messages:
                html += f"<li>{error}</li>"
            html += """
                    </ul>
                </div>
            """

        html += """
            </div>
        </body>
        </html>
        """

        return html
