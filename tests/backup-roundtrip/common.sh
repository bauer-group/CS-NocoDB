#!/usr/bin/env bash
# =============================================================================
# CS-NocoDB backup round trip - shared helpers (sourced, not executed)
# =============================================================================
# Used by seed.sh, mutate.sh and check.sh, which the automation-templates module
# modules-backup-roundtrip-test.yml runs against the started stack. The module
# exports COMPOSE_FILE, COMPOSE_PROJECT_NAME and COMPOSE_PROFILES, so a plain
# `docker compose` reaches this stack, plus ROUNDTRIP_MARKER - a unique token
# ([a-z0-9-]) per run that tags everything the scripts write - and
# ROUNDTRIP_BACKUP_SERVICE, the sidecar.
#
# Data is written and read through NocoDB's REST API (curl and jq on the
# runner) - the same API the sidecar's nocodb-rest source exports from.
# =============================================================================

# Command substitutions keep set -e: a failing call inside VALUE=$(helper) then
# stops the helper there instead of running on with an empty result.
shopt -s inherit_errexit

: "${ROUNDTRIP_MARKER:?set by the round-trip module}"
: "${ROUNDTRIP_BACKUP_SERVICE:?set by the round-trip module}"
# The marker ends up in a file name and a NocoDB filter expression.
[[ "$ROUNDTRIP_MARKER" =~ ^[a-z0-9-]+$ ]] || { echo "unexpected marker format" >&2; exit 2; }

# What seed.sh creates: a base with one table and a record carrying the marker
# with two text attachments whose name and content carry it as well. Both have
# the same name and so the same title - NocoDB keeps the uploaded file name as
# the title, so two "invoice.pdf" in one field are common - but different
# content: the REST export has to keep them apart. The attachment values are
# used by the scripts that source this file.
BASE_TITLE="roundtrip"
TABLE_TITLE="markers"
# shellcheck disable=SC2034
ATTACHMENT_NAME="roundtrip-${ROUNDTRIP_MARKER}.txt"
# shellcheck disable=SC2034
ATTACHMENT_CONTENTS=(
  "backup round trip attachment ${ROUNDTRIP_MARKER} one"
  "backup round trip attachment ${ROUNDTRIP_MARKER} two"
)

# The NocoDB data volume inside nocodb-server. The Local storage adapter puts
# uploads below nc/uploads; the scripts search the whole volume for the marker,
# so a changed upload layout cannot hide a file.
NOCODB_DATA_DIR="/usr/app/data"

# NocoDB as published on the runner, whatever EXPOSED_APP_PORT says.
nocodb_url() {
  local published
  published=$(docker compose port nocodb-server 8080)
  [ -n "$published" ] || { echo "nocodb-server does not publish port 8080" >&2; return 1; }
  echo "http://127.0.0.1:${published##*:}"
}

# The API token the sidecar exports with. seed.sh creates it through NocoDB and
# hands it to the sidecar; mutate.sh and check.sh read it back from there.
sidecar_token() {
  docker compose exec -T "$ROUNDTRIP_BACKUP_SERVICE" printenv NOCODB_API_TOKEN
}

# nc_api METHOD PATH [curl args...] - one NocoDB REST call against NOCODB_URL.
# Authenticates with NC_TOKEN (API token) or, before seed.sh has created one,
# with NC_JWT (the session of the user it signed up). Prints the response body;
# any status other than 2xx is an error, never an empty result.
nc_api() {
  local method="$1" path="$2" response status
  local auth=()
  shift 2
  if [ -n "${NC_TOKEN:-}" ]; then
    auth=(-H "xc-token: $NC_TOKEN")
  elif [ -n "${NC_JWT:-}" ]; then
    auth=(-H "xc-auth: $NC_JWT")
  fi
  response=$(curl --silent --show-error --max-time 60 --write-out '\n%{http_code}' \
    -X "$method" "${auth[@]}" "$@" "${NOCODB_URL:?}${path}") || return
  status=${response##*$'\n'}
  response=${response%$'\n'*}
  if [[ "$status" != 2?? ]]; then
    echo "NocoDB API $method $path: HTTP $status ${response:0:500}" >&2
    return 1
  fi
  printf '%s\n' "$response"
}

# Id of the seeded table, looked up by base and table title. Exactly one match
# each, or the call fails.
table_id() {
  local bases base_id tables
  bases=$(nc_api GET /api/v2/meta/bases)
  base_id=$(jq -er --arg t "$BASE_TITLE" '[.list[] | select(.title == $t)]
    | if length == 1 then .[0].id else error("\(length) bases titled \($t)") end' <<< "$bases")
  tables=$(nc_api GET "/api/v2/meta/bases/${base_id}/tables")
  jq -er --arg t "$TABLE_TITLE" '[.list[] | select(.title == $t)]
    | if length == 1 then .[0].id else error("\(length) tables titled \($t)") end' <<< "$tables"
}

# Records of the seeded table whose Marker field holds this run's marker.
marker_records() {
  nc_api GET "/api/v2/tables/$1/records" --get \
    --data-urlencode "where=(Marker,eq,${ROUNDTRIP_MARKER})"
}

# Files on the NocoDB data volume whose name carries the marker, one per line.
marker_files() {
  docker compose exec -T nocodb-server \
    find "$NOCODB_DATA_DIR" -type f -name "*${ROUNDTRIP_MARKER}*"
}
