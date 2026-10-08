#!/usr/bin/env bash
# =============================================================================
# CS-NocoDB backup round trip - check
# =============================================================================
# Exits 0 when the seeded data is in the state ROUNDTRIP_EXPECT names:
#   present  NocoDB returns the record, the attachment file is on the data
#            volume with its exact content and NocoDB serves it back; once a
#            snapshot exists, its REST export holds the record and the file
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

expect_count() {
  local what="$1" got="$2"
  if [ "$got" = "$WANT" ]; then
    echo "ok   $what: $got (expected $WANT)"
  else
    echo "FAIL $what: $got (expected $WANT)"; FAILED=1
  fi
}

NOCODB_URL=$(nocodb_url)
NC_TOKEN=$(sidecar_token)

# -- database (component "database"), read through NocoDB ---------------------
TABLE_ID=$(table_id)
RECORDS=$(marker_records "$TABLE_ID")
expect_count "record" "$(jq -er '.list | length' <<< "$RECORDS")"

# -- data volume (component "nocodb-data") -------------------------------------
FILES=$(marker_files)
FILE_COUNT=$(grep -c . <<< "$FILES" || true)
expect_count "attachment file" "$FILE_COUNT"
if [ "$ROUNDTRIP_EXPECT" = "present" ] && [ "$FILE_COUNT" = 1 ]; then
  CONTENT=$(docker compose exec -T nocodb-server cat "$FILES")
  if [ "$CONTENT" = "$ATTACHMENT_CONTENT" ]; then
    echo "ok   attachment file content: as seeded"
  else
    echo "FAIL attachment file content of $FILES: '$CONTENT'"; FAILED=1
  fi
fi

# -- application: NocoDB serves the record's attachment ------------------------
if [ "$ROUNDTRIP_EXPECT" = "present" ] && [ "$FAILED" -eq 0 ]; then
  LINK=$(jq -er '.list[0].Files[0] | .signedPath // .path' <<< "$RECORDS")
  LINK=${LINK#/}
  SERVED=$(curl --silent --show-error --fail --max-time 60 "${NOCODB_URL}/${LINK}")
  if [ "$SERVED" = "$ATTACHMENT_CONTENT" ]; then
    echo "ok   NocoDB serves the attachment back"
  else
    echo "FAIL NocoDB served '${SERVED:0:200}' for the attachment"; FAILED=1
  fi
fi

# -- REST export in the snapshot (component "nocodb") --------------------------
# The full restore leaves this component alone: it is restored on demand with
# 'backuphelper nocodb restore-*'. What has to hold is that the snapshot carries
# the seeded record and its attachment bytes, read through the plugin's own
# snapshot access (integrity check, extraction) that those commands use.
if [ "$ROUNDTRIP_EXPECT" = "present" ] && [ -n "${ROUNDTRIP_SNAPSHOT_ID:-}" ]; then
  docker compose exec -T "$ROUNDTRIP_BACKUP_SERVICE" python - \
      "$ROUNDTRIP_SNAPSHOT_ID" "$ROUNDTRIP_MARKER" "$BASE_TITLE" "$TABLE_TITLE" \
      "$ATTACHMENT_NAME" "$ATTACHMENT_CONTENT" <<'PY' || FAILED=1
import gzip
import json
import sys

from nocodb_backup_ext._snapshot import open_export

snapshot_id, marker, base, table, attachment, content = sys.argv[1:7]
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
    file = table_dir / "attachments" / "Files" / attachment
    if file.is_file() and file.read_text() == content:
        print("ok   REST export: attachment file with the seeded content")
    else:
        found = sorted(p.name for p in (table_dir / "attachments").rglob("*") if p.is_file())
        print(f"FAIL REST export: attachment {attachment} missing or changed (files: {found})")
        failed = True
sys.exit(1 if failed else 0)
PY
fi

exit "$FAILED"
