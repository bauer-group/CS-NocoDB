#!/usr/bin/env bash
# =============================================================================
# CS-NocoDB backup round trip - seed
# =============================================================================
# Writes, through NocoDB itself, data that every backup component carries:
#
#   database     a base, a table and a record whose Marker field holds the
#                run's marker (PostgreSQL dump)
#   nocodb-data  a text attachment on that record, stored by NocoDB's Local
#                storage adapter on the data volume (file archive)
#   nocodb       the record and its attachment as the sidecar's REST export
#                sees them
#
# The REST export needs an API token, which only exists once a user does. The
# seed signs up the first user (super admin) with throwaway credentials,
# creates a token through NocoDB, writes it to the .env as NOCODB_API_TOKEN and
# recreates the sidecar so it exports with it.
# =============================================================================
set -euo pipefail
# shellcheck source=tests/backup-roundtrip/common.sh
source "$(dirname "$0")/common.sh"

NOCODB_URL=$(nocodb_url)

# -- first user and API token ---------------------------------------------------
PASSWORD="Rt1-$(openssl rand -hex 16)"
echo "::add-mask::$PASSWORD"
NC_JWT=$(jq -n --arg email "roundtrip@example.com" --arg password "$PASSWORD" '{$email, $password}' \
  | nc_api POST /api/v1/auth/user/signup -H 'Content-Type: application/json' --data-binary @- \
  | jq -er '.token')
echo "::add-mask::$NC_JWT"

NC_TOKEN=$(jq -n '{description: "backup round trip"}' \
  | nc_api POST /api/v1/tokens -H 'Content-Type: application/json' --data-binary @- \
  | jq -er '.token')
echo "::add-mask::$NC_TOKEN"
unset NC_JWT

# The sidecar resolves NOCODB_API_TOKEN from its environment, which is fixed
# when the container is created: put the token into the .env (in place, the
# template already has the key) and recreate only the sidecar. Every later
# 'docker compose up' reads the same .env, so the sidecar keeps the token.
if grep -q '^NOCODB_API_TOKEN=' .env; then
  NEW_TOKEN="$NC_TOKEN" awk '/^NOCODB_API_TOKEN=/ { print "NOCODB_API_TOKEN=" ENVIRON["NEW_TOKEN"]; next } { print }' \
    .env > .env.roundtrip
  mv .env.roundtrip .env
else
  printf 'NOCODB_API_TOKEN=%s\n' "$NC_TOKEN" >> .env
fi
docker compose up -d --no-deps --wait --wait-timeout 300 "$ROUNDTRIP_BACKUP_SERVICE"
[ "$(sidecar_token)" = "$NC_TOKEN" ] || { echo "the sidecar did not pick up the API token" >&2; exit 1; }
echo "API token created and handed to $ROUNDTRIP_BACKUP_SERVICE"

# -- base, table, attachment, record ---------------------------------------------
BASE_ID=$(jq -n --arg title "$BASE_TITLE" '{$title}' \
  | nc_api POST /api/v2/meta/bases -H 'Content-Type: application/json' --data-binary @- \
  | jq -er '.id')

TABLE_ID=$(jq -n --arg title "$TABLE_TITLE" '{$title, table_name: $title, columns: [
      {title: "Marker", column_name: "marker", uidt: "SingleLineText"},
      {title: "Files",  column_name: "files",  uidt: "Attachment"}]}' \
  | nc_api POST "/api/v2/meta/bases/${BASE_ID}/tables" -H 'Content-Type: application/json' --data-binary @- \
  | jq -er '.id')

UPLOAD=$(mktemp)
trap 'rm -f "$UPLOAD"' EXIT
printf '%s' "$ATTACHMENT_CONTENT" > "$UPLOAD"
ATTACHMENT=$(nc_api POST /api/v2/storage/upload -F "files=@${UPLOAD};filename=${ATTACHMENT_NAME};type=text/plain" \
  | jq -ec 'if type == "array" and length == 1 then .[0] else error("unexpected upload response") end')

RECORD_ID=$(jq -n --arg marker "$ROUNDTRIP_MARKER" --argjson attachment "$ATTACHMENT" \
    '[{Marker: $marker, Files: [$attachment]}]' \
  | nc_api POST "/api/v2/tables/${TABLE_ID}/records" -H 'Content-Type: application/json' --data-binary @- \
  | jq -er 'if type == "array" then .[0].Id else .Id end')

echo "seeded base $BASE_ID, table $TABLE_ID, record $RECORD_ID with attachment:"
marker_files
