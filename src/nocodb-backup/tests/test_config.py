"""Tests for configuration module."""

import os
import pytest


def test_settings_default_values(monkeypatch):
    """Test that settings have sensible defaults."""
    # Set required env vars
    monkeypatch.setenv("DATABASE_PASSWORD", "test_password")

    from config import Settings
    settings = Settings()

    assert settings.db_host == "database-server"
    assert settings.db_port == 5432
    assert settings.db_name == "nocodb"
    assert settings.db_user == "nocodb"
    assert settings.backup_retention_count == 30
    assert settings.backup_schedule_mode == "cron"
    assert settings.backup_schedule_hour == 5
    assert settings.backup_schedule_minute == 15


def test_settings_s3_enabled(monkeypatch):
    """Test S3 enabled detection."""
    monkeypatch.setenv("DATABASE_PASSWORD", "test_password")

    from config import Settings

    # Without S3 config
    settings = Settings()
    assert settings.s3_enabled is False

    # With S3 config
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")

    settings = Settings()
    assert settings.s3_enabled is True


def test_settings_alert_channels(monkeypatch):
    """Test alert channel parsing."""
    monkeypatch.setenv("DATABASE_PASSWORD", "test_password")
    monkeypatch.setenv("ALERT_CHANNELS", "email,teams")

    from config import Settings
    settings = Settings()

    channels = settings.get_alert_channels()
    assert "email" in channels
    assert "teams" in channels


def test_settings_day_of_week_validation(monkeypatch):
    """Test day of week validation."""
    monkeypatch.setenv("DATABASE_PASSWORD", "test_password")
    monkeypatch.setenv("BACKUP_SCHEDULE_DAY_OF_WEEK", "0,2,4")

    from config import Settings
    settings = Settings()

    assert settings.backup_schedule_day_of_week == "0,2,4"
