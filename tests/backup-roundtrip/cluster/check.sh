#!/usr/bin/env bash
# =============================================================================
# CS-NocoDB backup round trip, cluster stack - check
# =============================================================================
# Exits 0 when the seeded data is in the state ROUNDTRIP_EXPECT names on EVERY
# NocoDB instance, each one asked directly on its own port:
#   present  the table has the attachment field, the record is there and the
#            instance serves both attachments with their seeded content
#   absent   neither the attachment field nor the record
# and when everything the single-instance check covers (../check.sh) holds
# through the load balancer: the record, both files on the data volume, the
# attachments served, the REST export in the snapshot.
#
# Once mutate.sh has run, also:
#   - every instance still runs in the container it ran in at the mutation,
#     never restarted: NocoDB empties its Redis cache whenever an instance
#     starts, which would hide whether the sidecar did
#   - the key mutate.sh wrote into the instances' Redis database is there
#     before the restore and gone after it: the sidecar's post_restore hook
#     emptied the database the instances read their metadata from
# A failing API call or container command ends the script (set -e) - an error
# is never read as "absent".
# =============================================================================
set -euo pipefail
# shellcheck source=tests/backup-roundtrip/cluster/common.sh
source "$(dirname "$0")/common.sh"

WANT=$(expected_count)
FAILED=0
# The seeded contents, one per line and sorted, to compare served files with.
EXPECTED=$(printf '%s\n' "${ATTACHMENT_CONTENTS[@]}" | sort)
NC_TOKEN=$(sidecar_token)

# -- since the mutation: no instance restarted, Redis emptied by the restore ------
if [ -f "$INSTANCES_FILE" ]; then
  CONTAINERS=$(instance_containers)
  if [ "$CONTAINERS" = "$(cat "$INSTANCES_FILE")" ]; then
    echo "ok   instances: $(wc -l <<< "$CONTAINERS"), none restarted since the mutation"
  else
    echo "FAIL instances were recreated or restarted since the mutation:"
    diff "$INSTANCES_FILE" - <<< "$CONTAINERS" || true
    FAILED=1
  fi
  expect_count "Redis key set by mutate.sh" "$(nc_redis EXISTS "$SENTINEL_KEY")" "$((1 - WANT))"
fi

# -- every instance, asked directly ---------------------------------------------
INSTANCES=$(nocodb_instances)
mapfile -t INSTANCE_LIST <<< "$INSTANCES"
for SERVICE in "${INSTANCE_LIST[@]}"; do
  NOCODB_URL=$(nocodb_url "$SERVICE")
  TABLE_ID=$(table_id)
  FIELDS=$(nc_api GET "/api/v2/meta/tables/${TABLE_ID}" \
    | jq -er --arg t "$ATTACHMENT_FIELD" '[.columns[] | select(.title == $t)] | length')
  expect_count "$SERVICE: field $ATTACHMENT_FIELD" "$FIELDS"
  RECORDS=$(marker_records "$TABLE_ID")
  COUNT=$(jq -er '.list | length' <<< "$RECORDS")
  expect_count "$SERVICE: record" "$COUNT"
  if [ "$WANT" = 1 ] && [ "$FIELDS" = 1 ] && [ "$COUNT" = 1 ]; then
    SERVED=$(served_attachments "$RECORDS")
    if [ "$SERVED" = "$EXPECTED" ]; then
      echo "ok   $SERVICE: serves the attachments with their seeded content"
    else
      echo "FAIL $SERVICE: served '${SERVED:0:400}' for the attachments"; FAILED=1
    fi
  fi
done

# -- everything the single-instance check covers, through the load balancer -----
echo "single-instance check through the load balancer:"
bash "$(dirname "$0")/../check.sh" || FAILED=1

exit "$FAILED"
