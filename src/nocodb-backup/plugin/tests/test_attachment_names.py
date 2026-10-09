"""Attachments that share a title must survive export and restore apart.

The export stored every attachment of a field as attachments/<field>/<title>,
so two different files with the same title (two records, each with its own
"invoice.pdf") overwrote each other: the snapshot kept the last one, and the
restore linked that one file to both records.
"""

import gzip
import json
import tarfile

import httpx

from nocodb_backup_ext.commands import _find_backup_file, _restore_attachments_for_table
from nocodb_backup_ext.rest_source import NocoDBRestSource, _unique_name


def _routes(records: list[dict]) -> dict:
    return {
        "/api/v2/meta/bases": {"list": [{"id": "b1", "title": "Base A"}]},
        "/api/v2/meta/bases/b1/tables": {"list": [{"id": "t1", "title": "Tbl"}]},
        "/api/v2/meta/tables/t1": {"id": "t1", "title": "Tbl",
                                   "columns": [{"title": "Files", "uidt": "Attachment"}]},
        "/api/v2/tables/t1/records?offset=0": {"list": records,
                                               "pageInfo": {"totalRows": len(records)}},
    }


def _export(tmp_path, monkeypatch, records, files):
    """Run the export against a mock NocoDB; return (component, served paths)."""
    src = NocoDBRestSource({"type": "nocodb-rest", "token": "t", "api_url": "http://nocodb:8080"})
    routes = _routes(records)
    served = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in files:
            served.append(request.url.path)
            return httpx.Response(200, content=files[request.url.path])
        key = request.url.path
        if request.url.query:
            key = f"{key}?offset={request.url.params.get('offset', '0')}"
        body = routes.get(key)
        return httpx.Response(200, json=body) if body is not None else httpx.Response(404)

    monkeypatch.setattr(src, "_client", lambda: httpx.Client(
        base_url=src.api_url, transport=httpx.MockTransport(handler)))
    [comp] = src.produce(tmp_path / "staging")
    assert comp.error is None
    return comp, served


TWO_INVOICES = [
    {"Id": 1, "Files": [{"path": "download/2026/a/invoice_Ab1.pdf", "title": "invoice.pdf"}]},
    {"Id": 2, "Files": [{"path": "download/2026/b/invoice_Cd2.pdf", "title": "invoice.pdf"}]},
]
INVOICE_BYTES = {"/download/2026/a/invoice_Ab1.pdf": b"first", "/download/2026/b/invoice_Cd2.pdf": b"second"}


def test_same_title_attachments_are_all_kept(tmp_path, monkeypatch):
    comp, _ = _export(tmp_path, monkeypatch, TWO_INVOICES, INVOICE_BYTES)
    with tarfile.open(comp.path, "r:gz") as tar:
        tree = {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}

    table = "bases/Base A/tables/Tbl"
    assert tree[f"{table}/attachments/Files/invoice.pdf"] == b"first"
    assert tree[f"{table}/attachments/Files/invoice (2).pdf"] == b"second"
    assert comp.metadata["attachments"] == 2
    index = json.loads(tree[f"{table}/attachments.json"])
    assert index == {"version": 1, "fields": {"Files": {
        "download/2026/a/invoice_Ab1.pdf": "invoice.pdf",
        "download/2026/b/invoice_Cd2.pdf": "invoice (2).pdf"}}}


def test_a_shared_stored_file_is_downloaded_once(tmp_path, monkeypatch):
    # Two cells referencing the same stored file hold the same bytes.
    shared = {"path": "download/2026/a/logo_Xy1.png", "title": "logo.png"}
    records = [{"Id": 1, "Files": [shared]}, {"Id": 2, "Files": [dict(shared)]}]
    comp, served = _export(tmp_path, monkeypatch, records, {"/download/2026/a/logo_Xy1.png": b"png"})
    assert served == ["/download/2026/a/logo_Xy1.png"]
    assert comp.metadata["attachments"] == 1


def _extract(comp, dest):
    with tarfile.open(comp.path, "r:gz") as tar:
        tar.extractall(dest, filter="data")
    return dest / "bases" / "Base A" / "tables" / "Tbl"


def test_restore_links_each_record_to_its_own_file(tmp_path, monkeypatch):
    comp, _ = _export(tmp_path, monkeypatch, TWO_INVOICES, INVOICE_BYTES)
    table_dir = _extract(comp, tmp_path / "export")
    records = json.loads(gzip.decompress((table_dir / "records.json.gz").read_bytes()))

    uploads, patches = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/storage/upload":
            body = request.read()
            content = b"first" if b"first" in body else b"second" if b"second" in body else b"?"
            name = "invoice.pdf" if b'filename="invoice.pdf"' in body else "other"
            uploads.append((name, content))
            return httpx.Response(200, json=[{"title": name, "path": f"new/{content.decode()}"}])
        patches.extend(json.loads(request.content))
        return httpx.Response(200, json=[])

    client = httpx.Client(base_url="http://nc", transport=httpx.MockTransport(handler))
    uploaded, errors = _restore_attachments_for_table(
        client, client, "t1", table_dir, records, ["Files"], [1, 2])

    assert (uploaded, errors) == (2, 0)
    # The upload keeps the attachment's title, not the archive's "invoice (2).pdf".
    assert uploads == [("invoice.pdf", b"first"), ("invoice.pdf", b"second")]
    linked = {p["Id"]: p["Files"][0]["path"] for p in patches}
    assert linked == {1: "new/first", 2: "new/second"}


def test_indexed_lookup_never_falls_back_to_another_file(tmp_path):
    # With an index, an attachment it does not list (its download failed) has
    # no file - the title fallback would hand it another attachment's bytes.
    att = tmp_path / "attachments"
    (att / "Files").mkdir(parents=True)
    (att / "Files" / "invoice.pdf").write_bytes(b"first")
    index = {"Files": {"download/a/invoice_Ab1.pdf": "invoice.pdf"}}

    hit = _find_backup_file(att, "Files", {"path": "download/a/invoice_Ab1.pdf", "title": "invoice.pdf"}, index)
    assert hit is not None and hit.read_bytes() == b"first"
    assert _find_backup_file(att, "Files", {"path": "download/b/invoice_Cd2.pdf", "title": "invoice.pdf"},
                             index) is None
    # Legacy snapshots (no index) keep the title lookup.
    assert _find_backup_file(att, "Files", {"path": "download/b/invoice_Cd2.pdf", "title": "invoice.pdf"}
                             ).name == "invoice.pdf"


def test_indexed_lookup_rejects_names_outside_the_field_dir(tmp_path):
    att = tmp_path / "attachments"
    (att / "Files").mkdir(parents=True)
    (att / "secret.txt").write_bytes(b"x")
    for name in ("../secret.txt", "..", "."):
        assert _find_backup_file(att, "Files", {"path": "p"}, {"Files": {"p": name}}) is None


def test_unique_name():
    assert _unique_name("a.pdf", set()) == "a.pdf"
    assert _unique_name("a.pdf", {"a.pdf"}) == "a (2).pdf"
    assert _unique_name("a.pdf", {"a.pdf", "a (2).pdf"}) == "a (3).pdf"
    assert _unique_name("README", {"README"}) == "README (2)"
    assert _unique_name(".env", {".env"}) == ".env (2)"
    long = "x" * 96 + ".pdf"
    renamed = _unique_name(long, {long})
    assert len(renamed) <= 100 and renamed.endswith(" (2).pdf")
    for unusable in ("", ".", ".."):
        assert _unique_name(unusable, set()) == "attachment"
