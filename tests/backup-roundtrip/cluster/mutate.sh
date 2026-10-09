#!/usr/bin/env bash
# =============================================================================
# CS-NocoDB backup round trip, cluster stack - mutate
# =============================================================================
# Loses data and metadata through the load balancer:
#
#   data      the single-instance mutation (../mutate.sh): the seeded record
#             through the data API, its attachment files on the data volume
#   metadata  the table's attachment field, through the meta API. NocoDB drops
#             the column and removes it from the column list in the Redis cache
#             the instances share. The restore brings the column back in the
#             database only: running instances serve it again only once that
#             cache has been emptied.
#
# Then it records what the check after the restore compares against: the
# container and start time of every instance (none may be restarted - NocoDB
# empties the cache whenever an instance starts, which would hide whether the
# sidecar did) and a sentinel key in the instances' Redis database.
# =============================================================================
set -euo pipefail
# shellcheck source=tests/backup-roundtrip/cluster/common.sh
source "$(dirname "$0")/common.sh"

# -- data ------------------------------------------------------------------------
bash "$(dirname "$0")/../mutate.sh"

# -- metadata --------------------------------------------------------------------
NOCODB_URL=$(nocodb_url)
NC_TOKEN=$(sidecar_token)
TABLE_ID=$(table_id)
COLUMN_ID=$(nc_api GET "/api/v2/meta/tables/${TABLE_ID}" \
  | jq -er --arg t "$ATTACHMENT_FIELD" '[.columns[] | select(.title == $t)]
      | if length == 1 then .[0].id else error("\(length) columns titled \($t)") end')
nc_api DELETE "/api/v2/meta/columns/${COLUMN_ID}" > /dev/null
echo "dropped field $ATTACHMENT_FIELD ($COLUMN_ID) of table $TABLE_ID"

# -- reference for the check after the restore ----------------------------------
instance_containers > "$INSTANCES_FILE"
REPLY=$(nc_redis SET "$SENTINEL_KEY" mutated)
[ "$REPLY" = "OK" ] || { echo "Redis did not store the sentinel key: '$REPLY'" >&2; exit 1; }
echo "recorded the containers of $(wc -l < "$INSTANCES_FILE") instances and set Redis key $SENTINEL_KEY"
