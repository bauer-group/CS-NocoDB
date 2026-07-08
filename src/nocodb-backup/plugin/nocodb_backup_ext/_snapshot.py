"""Bridge the engine's snapshot-archive model to the bespoke ``bases/`` tree.

The bespoke restore commands read the REST export from a local directory
(``<data_dir>/<backup_id>/bases/…``). In the central engine a snapshot is a
single ``<id>.tar.gz`` archive with the REST export carried as a nested
``<name>.tar.gz`` component. ``open_export`` reproduces the engine's own restore
front-half — off-site S3 hydration, the sha256 integrity gate, optional
decrypt, then extraction — and hands the restore commands the extracted export
directory, so their schema/record/attachment logic ports over unchanged.
"""

from __future__ import annotations

import logging
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from backuphelper.archive.bundle import extract_bundle
from backuphelper.archive.manifest import read_manifest
from backuphelper.config.loader import load_config
from backuphelper.integrity.hashing import sha256_file
from backuphelper.runner import (
    _decrypt_if_needed,
    _find_artifact,
    _hydrate_from_destinations,
)

log = logging.getLogger("backuphelper.plugin.nocodb")


class SnapshotError(RuntimeError):
    """Raised when a snapshot cannot be opened for NocoDB restore."""


def _data_dir() -> Path:
    return Path(os.environ.get("BACKUP_DATA_DIR", "/data"))


def _pick_job(job_name: Optional[str]):
    """Pick the job whose export we restore: the named one, else the first job
    that actually declares a ``nocodb-rest`` source, else the first job."""
    jobs = load_config().jobs
    if not jobs:
        return None
    if job_name:
        return next((j for j in jobs if j.name == job_name), None)
    for job in jobs:
        if any(getattr(s, "type", None) == "nocodb-rest" for s in job.sources):
            return job
    return jobs[0]


@contextmanager
def open_export(snapshot_id: str, *, job_name: Optional[str] = None) -> Iterator[Path]:
    """Yield a directory holding the extracted NocoDB REST export (``bases/`` +
    ``manifest.json``) for ``snapshot_id``.

    Hydrates the snapshot from the off-site S3 destination when the local copy
    is gone, verifies the archive's sha256 against its manifest before touching
    anything, decrypts if needed, and extracts the nested ``nocodb`` component.
    The directory is a temp dir removed on context exit.
    """
    job = _pick_job(job_name)
    if job is None:
        raise SnapshotError("no job configured — cannot locate a snapshot")

    dd = _data_dir()
    _hydrate_from_destinations(job, dd, snapshot_id)  # DR: pull back from S3 if local is gone
    artifact = _find_artifact(dd, snapshot_id)
    sidecar = dd / f"{snapshot_id}.manifest.json"
    if artifact is None or not sidecar.exists():
        raise SnapshotError(f"snapshot {snapshot_id} not found (archive or manifest missing)")

    manifest = read_manifest(sidecar)
    if manifest.archive_sha256 and sha256_file(artifact) != manifest.archive_sha256:
        raise SnapshotError(f"snapshot {snapshot_id} failed its sha256 integrity check")

    comp = next((c for c in manifest.components if c.kind == "nocodb" and not c.error), None)
    if comp is None:
        raise SnapshotError(
            f"snapshot {snapshot_id} contains no NocoDB REST export "
            "(was BACKUP_API_EXPORT enabled when it was taken?)"
        )

    with tempfile.TemporaryDirectory(prefix="nocodb-restore-") as td:
        work = Path(td)
        bundle = _decrypt_if_needed(artifact, work)
        extracted = extract_bundle(bundle, work / "extracted")
        nested = extracted / f"{comp.name}.tar.gz"
        if not nested.exists():
            raise SnapshotError(
                f"NocoDB export component {comp.name}.tar.gz is missing from snapshot {snapshot_id}"
            )
        export_dir = extract_bundle(nested, work / "export")
        yield export_dir
