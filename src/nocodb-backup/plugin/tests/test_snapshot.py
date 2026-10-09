"""open_export says why a snapshot has no REST export to restore from."""

import pytest
from backuphelper.archive.manifest import Component, Manifest

from nocodb_backup_ext import _snapshot
from nocodb_backup_ext._snapshot import SnapshotError, open_export

SID = "2026-10-09_05-15-00"


def _snapshot_with(tmp_path, monkeypatch, *components: Component) -> None:
    (tmp_path / f"{SID}.tar.gz").write_bytes(b"archive")
    manifest = Manifest(snapshot_id=SID, instance_name="nocodb",
                        created_at="2026-10-09T05:15:00+00:00", components=list(components))
    (tmp_path / f"{SID}.manifest.json").write_text(manifest.model_dump_json())
    monkeypatch.setenv("BACKUP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(_snapshot, "_pick_job", lambda job_name: object())
    monkeypatch.setattr(_snapshot, "_hydrate_from_destinations", lambda job, dd, sid: None)


DATABASE = Component(name="database", kind="postgres", size=10, sha256="x")


def test_names_the_switches_when_the_export_was_not_captured(tmp_path, monkeypatch):
    _snapshot_with(tmp_path, monkeypatch, DATABASE)
    with pytest.raises(SnapshotError) as err, open_export(SID):
        pass
    assert "NOCODB_BACKUP_API_EXPORT=true" in str(err.value)
    assert "NOCODB_API_TOKEN" in str(err.value)


def test_reports_the_error_of_a_failed_export(tmp_path, monkeypatch):
    # Since BackupHelper 1.7.7 a failed component is stored with its error; it
    # was captured, so "check that the export is switched on" would mislead.
    failed = Component(name="nocodb", kind="nocodb", size=0, sha256="", error="HTTP 401 for /api/v2/meta/bases")
    _snapshot_with(tmp_path, monkeypatch, DATABASE, failed)
    with pytest.raises(SnapshotError, match="failed when this backup ran .*HTTP 401"), open_export(SID):
        pass
