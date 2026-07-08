"""Regression test for the batched record insert: a failed batch must not shift
subsequent records' attachments onto the wrong new id (issue #4). The inserted
records and the collected new ids must stay in lockstep."""

import httpx

from nocodb_backup_ext.commands import _insert_records_batched


def _client(handler):
    return httpx.Client(base_url="http://nc", transport=httpx.MockTransport(handler))


def test_failed_batch_keeps_records_and_ids_in_lockstep():
    # 3 records, batch_size=2 -> batch A = recs[0:2] (FAILS 500), batch B = recs[2:3] (OK -> id "X2").
    orig = [{"Id": 10, "n": "a"}, {"Id": 11, "n": "b"}, {"Id": 12, "n": "c"}]
    clean = [{"n": r["n"]} for r in orig]

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        body = json.loads(request.content)
        if len(body) == 2:            # the first (full) batch fails
            return httpx.Response(500, json={"msg": "boom"})
        return httpx.Response(200, json=[{"Id": "X2"}])  # second batch succeeds

    restored, inserted, new_ids, errs = _insert_records_batched(
        _client(handler), "tbl", clean, orig, collect_ids=True, batch_size=2)

    assert restored == 1                       # only the 1-record batch landed
    assert len(errs) == 1 and errs[0][0] == 0  # the failed batch reported at offset 0
    # lockstep: the surviving record and its new id line up positionally
    assert inserted == [{"Id": 12, "n": "c"}]
    assert new_ids == ["X2"]
    assert len(inserted) == len(new_ids)


def test_all_batches_succeed_pairs_every_record():
    orig = [{"Id": 1}, {"Id": 2}, {"Id": 3}]
    clean = [{} for _ in orig]

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        rows = json.loads(request.content)
        return httpx.Response(200, json=[{"Id": f"new{i}"} for i in range(len(rows))])

    restored, inserted, new_ids, errs = _insert_records_batched(
        _client(handler), "tbl", clean, orig, collect_ids=True, batch_size=2)

    assert restored == 3 and not errs
    assert inserted == orig                    # every original record paired
    assert len(new_ids) == 3
