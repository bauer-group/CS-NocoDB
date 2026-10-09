#!/usr/bin/env bash
# =============================================================================
# CS-NocoDB backup round trip - mutate
# =============================================================================
# Deletes the seeded record through NocoDB's data API, the way users lose data,
# and the attachment files from the data volume. NocoDB itself keeps the files
# of deleted records until its clean-up job removes orphans
# (NC_ATTACHMENT_RETENTION_DAYS, 10 days by default) - the script deletes the
# files the way that job, or a lost volume, would. The restore has to bring
# back the record and the files.
# =============================================================================
set -euo pipefail
# shellcheck source=tests/backup-roundtrip/common.sh
source "$(dirname "$0")/common.sh"

NOCODB_URL=$(nocodb_url)
NC_TOKEN=$(sidecar_token)
TABLE_ID=$(table_id)

IDS=$(marker_records "$TABLE_ID" \
  | jq -ec '[.list[] | {Id}] | if length == 1 then . else error("\(length) seeded records, expected 1") end')
nc_api DELETE "/api/v2/tables/${TABLE_ID}/records" -H 'Content-Type: application/json' --data-binary "$IDS" > /dev/null

DELETED=$(docker compose exec -T "$NOCODB_FILES_SERVICE" \
  find "$NOCODB_DATA_DIR" -type f -name "*${ROUNDTRIP_MARKER}*" -print -delete)
[ -n "$DELETED" ] || { echo "no attachment file carrying the marker to delete" >&2; exit 1; }

echo "deleted record $(jq -r '.[0].Id' <<< "$IDS") and attachment files:"
echo "$DELETED"
