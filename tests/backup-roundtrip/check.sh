#!/usr/bin/env bash
# =============================================================================
# CS-NocoDB backup round trip - check
# =============================================================================
# Exits 0 when the seeded data is in the state ROUNDTRIP_EXPECT names:
#   present  NocoDB returns the record, both attachment files are on the data
#            volume with their exact content and NocoDB serves them back; once
#            a snapshot exists, its REST export holds the record and, for each
#            of its attachments, a file of its own with that attachment's bytes
#   absent   no record and no file
# Each item is checked on its own, so "absent" proves the mutation removed every
# one of them and "present" proves the restore brought every one of them back.
# A failing API call or container command ends the script (set -e) - an error
# is never read as "absent".
# =============================================================================
set -euo pipefail
# shellcheck source=tests/backup-roundtrip/common.sh
source "$(dirname "$0")/common.sh"

case "${ROUNDTRIP_EXPECT:?set by the round-trip module}" in
  present) WANT=1 ;;
  absent)  WANT=0 ;;
  *) echo "unknown ROUNDTRIP_EXPECT '$ROUNDTRIP_EXPECT'" >&2; exit 2 ;;
esac
FAILED=0
# The seeded contents, one per line and sorted, to compare file sets with.
EXPECTED=$(printf '%s\n' "${ATTACHMENT_CONTENTS[@]}" | sort)

expect_count() {
  local what="$1" got="$2" want="${3:-$WANT}"
  if [ "$got" = "$want" ]; then
    echo "ok   $what: $got (expected $want)"
  else
    echo "FAIL $what: $got (expected $want)"; FAILED=1
  fi
}

NOCODB_URL=$(nocodb_url)
NC_TOKEN=$(sidecar_token)

# -- database (component "database"), read through NocoDB ---------------------
TABLE_ID=$(table_id)
RECORDS=$(marker_records "$TABLE_ID")
expect_count "record" "$(jq -er '.list | length' <<< "$RECORDS")"

# -- data volume (component "nocodb-data") -------------------------------------
WANT_FILES=$((WANT * ${#ATTACHMENT_CONTENTS[@]}))
FILES=$(marker_files)
FILE_COUNT=$(grep -c . <<< "$FILES" || true)
expect_count "attachment files" "$FILE_COUNT" "$WANT_FILES"
if [ "$ROUNDTRIP_EXPECT" = "present" ] && [ "$FILE_COUNT" = "$WANT_FILES" ]; then
  # stdin from /dev/null: docker compose exec would read the file list.
  CONTENTS=$(while IFS= read -r file; do
      docker compose exec -T nocodb-server cat "$file" < /dev/null; echo
    done <<< "$FILES" | sort)
  if [ "$CONTENTS" = "$EXPECTED" ]; then
    echo "ok   attachment file contents: as seeded"
  else
    echo "FAIL attachment file contents: '$CONTENTS'"; FAILED=1
  fi
fi

# -- application: NocoDB serves the record's attachments -----------------------
if [ "$ROUNDTRIP_EXPECT" = "present" ] && [ "$FAILED" -eq 0 ]; then
  SERVED=$(jq -er '.list[0].Files[] | .signedPath // .path' <<< "$RECORDS" \
    | while IFS= read -r link; do
        curl --silent --show-error --fail --max-time 60 "${NOCODB_URL}/${link#/}"; echo
      done | sort)
  if [ "$SERVED" = "$EXPECTED" ]; then
    echo "ok   NocoDB serves the attachments back"
  else
    echo "FAIL NocoDB served '${SERVED:0:400}' for the attachments"; FAILED=1
  fi
fi

# -- REST export in the snapshot (component "nocodb") --------------------------
# The full restore leaves this component alone: it is restored on demand with
# 'backuphelper nocodb restore-*'. What has to hold is that the snapshot carries
# the seeded record and the bytes of each of its attachments, read through the
# plugin's own snapshot access (integrity check, extraction) and the file
# lookup of those commands. The attachments share their title, so an export
# that names files by title alone keeps only one of them.
if [ "$ROUNDTRIP_EXPECT" = "present" ] && [ -n "${ROUNDTRIP_SNAPSHOT_ID:-}" ]; then
  docker compose exec -T "$ROUNDTRIP_BACKUP_SERVICE" python - \
      "$ROUNDTRIP_SNAPSHOT_ID" "$ROUNDTRIP_MARKER" "$BASE_TITLE" "$TABLE_TITLE" \
      "${ATTACHMENT_CONTENTS[@]}" <<'PY' || FAILED=1
import gzip
import json
import sys

from nocodb_backup_ext._snapshot import open_export
from nocodb_backup_ext.commands import _find_backup_file, _load_attachment_index

snapshot_id, marker, base, table = sys.argv[1:5]
contents = sorted(sys.argv[5:])
failed = False
with open_export(snapshot_id) as export:
    table_dir = export / "bases" / base / "tables" / table
    records = json.loads(gzip.decompress((table_dir / "records.json.gz").read_bytes()))
    hits = [r for r in records if r.get("Marker") == marker]
    if len(hits) == 1:
        print("ok   REST export: record with the marker")
    else:
        print(f"FAIL REST export: {len(hits)} records with the marker (expected 1)")
        failed = True
    index = _load_attachment_index(table_dir)
    files = [_find_backup_file(table_dir / "attachments", "Files", att, index)
             for att in ((hits[0].get("Files") or []) if hits else [])]
    got = sorted(f.read_text() if f else "<no file>" for f in files)
    if index is not None and got == contents:
        print(f"ok   REST export: {len(files)} attachments, each with its own file and content")
    else:
        att_dir = table_dir / "attachments"
        found = sorted(p.name for p in att_dir.rglob("*") if p.is_file()) if att_dir.is_dir() else []
        print(f"FAIL REST export: attachment contents {got} (expected {contents}, "
              f"index {'present' if index is not None else 'missing'}, files: {found})")
        failed = True
sys.exit(1 if failed else 0)
PY
fi

exit "$FAILED"
