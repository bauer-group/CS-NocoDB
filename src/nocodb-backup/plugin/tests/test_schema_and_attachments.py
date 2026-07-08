"""Regression tests for the NocoDB plugin's app-aware restore logic.

These cover the exact pieces a faithful port must not break: schema-aware column
preparation (which columns NocoDB recreates vs. which we must send) and the
4-strategy attachment-file finder (backup filenames rarely equal live URLs).
"""

import json

import pytest

from nocodb_backup_ext.commands import (
    _find_backup_file,
    _get_attachment_fields,
    _prepare_columns_for_create,
)
from nocodb_backup_ext.rest_source import _sanitize_filename as src_sanitize
from nocodb_backup_ext.commands import _sanitize_filename as cmd_sanitize


def test_sanitize_is_shared_between_source_and_commands():
    # Exporter and restorer MUST sanitize identically or restore never finds files.
    assert src_sanitize is cmd_sanitize
    assert src_sanitize('a/b:c<d>e"f|g?h*i') == "a_b_c_d_e_f_g_h_i"
    assert len(src_sanitize("x" * 200)) == 100


def test_prepare_columns_skips_system_pk_and_virtual():
    columns = [
        {"title": "Id", "uidt": "ID", "pk": True},
        {"title": "Created", "uidt": "CreatedTime"},
        {"title": "Owner", "uidt": "LinkToAnotherRecord"},
        {"title": "Total", "uidt": "Rollup"},
        {"title": "Name", "uidt": "SingleLineText"},
    ]
    creatable, skipped = _prepare_columns_for_create(columns)
    titles = [c["title"] for c in creatable]
    assert titles == ["Name"]  # only the real, user-defined column survives
    assert "Owner (LinkToAnotherRecord)" in skipped
    assert "Total (Rollup)" in skipped


def test_prepare_columns_keeps_only_create_props():
    columns = [{
        "title": "Amount", "column_name": "amount", "uidt": "Decimal",
        "dtxp": "10", "dtxs": "2", "rqd": True, "cdf": "0", "pv": False,
        "meta": {"x": 1},
        "id": "col_abc", "base_id": "b1", "fk_model_id": "m1",  # must be dropped
    }]
    creatable, _ = _prepare_columns_for_create(columns)
    assert set(creatable[0]) == {"title", "column_name", "uidt", "dtxp", "dtxs", "rqd", "cdf", "pv", "meta"}


def test_prepare_columns_builds_select_dtxp_from_coloptions():
    columns = [{
        "title": "Status", "uidt": "SingleSelect",
        "colOptions": {"options": [{"title": "open"}, {"title": "done"}]},
    }]
    creatable, _ = _prepare_columns_for_create(columns)
    assert creatable[0]["dtxp"] == "'open','done'"


def test_prepare_columns_keeps_existing_select_dtxp():
    columns = [{
        "title": "Status", "uidt": "MultiSelect", "dtxp": "'a','b'",
        "colOptions": {"options": [{"title": "x"}]},
    }]
    creatable, _ = _prepare_columns_for_create(columns)
    assert creatable[0]["dtxp"] == "'a','b'"  # do not clobber an explicit dtxp


def test_get_attachment_fields():
    schema = {"columns": [
        {"title": "Name", "uidt": "SingleLineText"},
        {"title": "Files", "uidt": "Attachment"},
        {"title": "Photo", "uidt": "Attachment"},
    ]}
    assert _get_attachment_fields(schema) == ["Files", "Photo"]


@pytest.fixture
def field_dir(tmp_path):
    d = tmp_path / _sanitize_field("Photos")
    d.mkdir()
    return tmp_path, d


def _sanitize_field(name):
    return src_sanitize(name)


def test_find_backup_file_by_title(tmp_path):
    att = tmp_path / "attachments"
    fd = att / src_sanitize("Photos")
    fd.mkdir(parents=True)
    (fd / src_sanitize("cat.png")).write_bytes(b"x")
    found = _find_backup_file(att, "Photos", {"title": "cat.png"})
    assert found is not None and found.name == "cat.png"


def test_find_backup_file_by_path_then_url(tmp_path):
    att = tmp_path / "attachments"
    fd = att / src_sanitize("Photos")
    fd.mkdir(parents=True)
    (fd / src_sanitize("real.jpg")).write_bytes(b"x")
    # title miss, path hit
    assert _find_backup_file(att, "Photos", {"title": "gone.jpg", "path": "d/real.jpg"}).name == "real.jpg"
    # title+path miss, url hit (query stripped)
    assert _find_backup_file(att, "Photos", {"url": "http://h/x/real.jpg?t=1"}).name == "real.jpg"


def test_find_backup_file_fuzzy_single_file(tmp_path):
    att = tmp_path / "attachments"
    fd = att / src_sanitize("Photos")
    fd.mkdir(parents=True)
    (fd / "only.bin").write_bytes(b"x")
    # nothing matches by title/path/url, but a single file in the dir → use it
    assert _find_backup_file(att, "Photos", {"title": "no-match"}).name == "only.bin"


def test_find_backup_file_missing_returns_none(tmp_path):
    att = tmp_path / "attachments"
    fd = att / src_sanitize("Photos")
    fd.mkdir(parents=True)
    (fd / "a.bin").write_bytes(b"x")
    (fd / "b.bin").write_bytes(b"x")  # 2 files, no match → ambiguous → None
    assert _find_backup_file(att, "Photos", {"title": "no-match"}) is None
    assert _find_backup_file(att, "Missing", {"title": "x"}) is None  # no field dir
