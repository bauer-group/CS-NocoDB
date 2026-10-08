"""Tests for the NocoDB REST source: config-activation contract + export tree."""

import gzip
import json
import tarfile

import httpx
import pytest

from nocodb_backup_ext.rest_source import NocoDBRestSource


def test_produce_skips_when_disabled(tmp_path):
    src = NocoDBRestSource({"type": "nocodb-rest", "token": "t", "enabled": False})
    assert src.produce(tmp_path) == []


def test_produce_skips_when_no_token(tmp_path):
    src = NocoDBRestSource({"type": "nocodb-rest", "token": ""})
    assert src.produce(tmp_path) == []


def _mock_client(source, routes):
    def handler(request: httpx.Request) -> httpx.Response:
        key = request.url.path
        if request.url.query:
            # records endpoint keys on offset so pagination terminates
            offset = request.url.params.get("offset", "0")
            key = f"{key}?offset={offset}"
        body = routes.get(key)
        if body is None:
            return httpx.Response(404, json={"msg": f"no route for {key}"})
        return httpx.Response(200, json=body)

    return httpx.Client(base_url=source.api_url, transport=httpx.MockTransport(handler))


def test_produce_writes_full_export_tree(tmp_path, monkeypatch):
    src = NocoDBRestSource({"type": "nocodb-rest", "token": "t",
                            "api_url": "http://nocodb:8080", "include_attachments": False})
    routes = {
        "/api/v2/meta/bases": {"list": [{"id": "b1", "title": "Base A"}]},
        "/api/v2/meta/bases/b1/tables": {"list": [{"id": "t1", "title": "Tbl"}]},
        "/api/v2/meta/tables/t1": {"id": "t1", "title": "Tbl",
                                   "columns": [{"title": "Name", "uidt": "SingleLineText"}]},
        "/api/v2/tables/t1/records?offset=0": {
            "list": [{"Id": 1, "Name": "a"}, {"Id": 2, "Name": "b"}],
            "pageInfo": {"totalRows": 2},
        },
    }
    monkeypatch.setattr(src, "_client", lambda: _mock_client(src, routes))

    components = src.produce(tmp_path)
    assert len(components) == 1
    comp = components[0]
    assert comp.kind == "nocodb" and comp.error is None
    assert comp.metadata == {"bases": 1, "tables": 1, "records": 2,
                             "attachments": 0, "total_size": comp.metadata["total_size"]}

    # unpack the produced nocodb.tar.gz and assert the portable tree
    with tarfile.open(comp.path, "r:gz") as tar:
        names = set(tar.getnames())
        assert "manifest.json" in names
        assert "bases/Base A/tables/Tbl/schema.json" in names
        assert "bases/Base A/tables/Tbl/records.json.gz" in names

        recs_member = tar.extractfile("bases/Base A/tables/Tbl/records.json.gz")
        records = json.loads(gzip.decompress(recs_member.read()))
        assert [r["Name"] for r in records] == ["a", "b"]

        manifest = json.loads(tar.extractfile("manifest.json").read())
        assert manifest["version"] == "1.0"
        assert manifest["bases"][0]["title"] == "Base A"


def _export_tree(component) -> dict[str, bytes]:
    with tarfile.open(component.path, "r:gz") as tar:
        return {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}


def test_produce_downloads_local_storage_attachments(tmp_path, monkeypatch):
    # NocoDB's default Local storage adapter stores an attachment as a
    # NocoDB-relative "path" (plus a "signedPath" when read through the API) -
    # there is no "url". The export must still carry the file.
    src = NocoDBRestSource({"type": "nocodb-rest", "token": "t", "api_url": "http://nocodb:8080"})
    stored = "2026/10/08/abc/report_X1y2Z.txt"
    attachment = {"path": f"download/{stored}", "signedPath": f"dltemp/sig/1700000000/{stored}",
                  "title": "report.txt", "mimetype": "text/plain", "size": 7}
    routes = {
        "/api/v2/meta/bases": {"list": [{"id": "b1", "title": "Base A"}]},
        "/api/v2/meta/bases/b1/tables": {"list": [{"id": "t1", "title": "Tbl"}]},
        "/api/v2/meta/tables/t1": {"id": "t1", "title": "Tbl", "columns": [
            {"title": "Name", "uidt": "SingleLineText"}, {"title": "Files", "uidt": "Attachment"}]},
        "/api/v2/tables/t1/records?offset=0": {
            "list": [{"Id": 1, "Name": "a", "Files": [attachment]}], "pageInfo": {"totalRows": 1}},
    }
    served = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/dltemp/sig/1700000000/{stored}":
            served.append(request.url.path)
            return httpx.Response(200, content=b"content")
        key = request.url.path
        if request.url.query:
            key = f"{key}?offset={request.url.params.get('offset', '0')}"
        body = routes.get(key)
        return httpx.Response(200, json=body) if body is not None else httpx.Response(404)

    monkeypatch.setattr(src, "_client", lambda: httpx.Client(
        base_url=src.api_url, transport=httpx.MockTransport(handler)))

    [comp] = src.produce(tmp_path)
    assert comp.error is None
    assert comp.metadata["attachments"] == 1
    assert served == [f"/dltemp/sig/1700000000/{stored}"]  # the signed link, which also works with secure attachments
    assert _export_tree(comp)["bases/Base A/tables/Tbl/attachments/Files/report.txt"] == b"content"


def test_attachment_link_prefers_signed_links():
    from nocodb_backup_ext.rest_source import _attachment_link

    assert _attachment_link({"path": "download/a", "signedPath": "dltemp/s/1/a"}) == "dltemp/s/1/a"
    assert _attachment_link({"path": "download/a"}) == "download/a"
    assert _attachment_link({"url": "https://s3/a", "signedUrl": "https://s3/a?sig"}) == "https://s3/a?sig"
    assert _attachment_link({"url": "https://s3/a"}) == "https://s3/a"
    assert _attachment_link({"title": "no link"}) is None
