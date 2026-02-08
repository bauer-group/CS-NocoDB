"""Tests for backup module."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch


def test_dump_result_dataclass():
    """Test DumpResult dataclass."""
    from backup.pg_dump import DumpResult

    result = DumpResult(success=True, path=Path("/test"), size=1024)
    assert result.success is True
    assert result.path == Path("/test")
    assert result.size == 1024

    failed = DumpResult(success=False, error="Test error")
    assert failed.success is False
    assert failed.error == "Test error"


def test_export_result_dataclass():
    """Test ExportResult dataclass."""
    from backup.nocodb_exporter import ExportResult

    result = ExportResult(
        success=True,
        bases_count=2,
        tables_count=10,
        records_count=1000,
        total_size=50000,
    )
    assert result.success is True
    assert result.bases_count == 2
    assert result.tables_count == 10
    assert result.records_count == 1000


def test_format_size():
    """Test size formatting."""
    from ui.console import format_size

    assert format_size(500) == "500 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1024 * 1024) == "1.0 MB"
    assert format_size(1024 * 1024 * 1024) == "1.00 GB"
