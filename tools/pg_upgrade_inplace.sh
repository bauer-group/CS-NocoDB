#!/usr/bin/env bash
# =============================================================================
# pg_upgrade_inplace.sh - PostgreSQL In-Place Major Version Upgrade
# =============================================================================
# Führt ein in-place Upgrade von PostgreSQL im selben Docker Volume durch.
# Nutzt Hardlinks - benötigt keinen zusätzlichen Speicherplatz.
#
# Nutzung:
#   ./pg_upgrade_inplace.sh [OPTIONS] <VOLUME_PATH>
#   ./pg_upgrade_inplace.sh [OPTIONS] --volume-name <DOCKER_VOLUME_NAME>
#
# Optionen:
#   --from <VERSION>      Quell-Version (default: 15)
#   --to <VERSION>        Ziel-Version (default: 18)
#   --volume-name <NAME>  Docker Volume Name statt Pfad
#   --dry-run             Nur prüfen, nichts ändern
#   --force               Keine Bestätigung abfragen
#   --help                Diese Hilfe anzeigen
#
# Beispiele:
#   ./pg_upgrade_inplace.sh /var/lib/docker/volumes/mydb-postgres
#   ./pg_upgrade_inplace.sh --volume-name mystack-postgres
#   ./pg_upgrade_inplace.sh --from 15 --to 18 --dry-run /var/lib/docker/volumes/mydb
#
# Voraussetzungen:
#   - Docker muss installiert sein
#   - Alle Container mit diesem Volume müssen gestoppt sein
#   - Root-Rechte (sudo) für Dateisystem-Operationen
# =============================================================================

set -euo pipefail

# =============================================================================
# Konfiguration
# =============================================================================
MAJOR_OLD="${MAJOR_OLD:-15}"
MAJOR_NEW="${MAJOR_NEW:-18}"
PG_UID="${PG_UID:-999}"
PG_GID="${PG_GID:-999}"
DRY_RUN=false
FORCE=false
VOLUME_NAME=""
VOL_DIR=""

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# Hilfsfunktionen
# =============================================================================
log()     { echo -e "${GREEN}[pg-upgrade]${NC} $*"; }
log_info(){ echo -e "${BLUE}[pg-upgrade]${NC} $*"; }
log_warn(){ echo -e "${YELLOW}[pg-upgrade][WARN]${NC} $*"; }
die()     { echo -e "${RED}[pg-upgrade][ERROR]${NC} $*" >&2; exit 1; }

usage() {
    grep -E '^#' "$0" | grep -v '^#!/' | sed 's/^# //' | sed 's/^#//'
    exit 0
}

# =============================================================================
# Cleanup bei Abbruch (CTRL+C, Fehler)
# =============================================================================
UPGRADE_STARTED=false
cleanup() {
    local exit_code=$?
    if [[ "${UPGRADE_STARTED}" == "true" && ${exit_code} -ne 0 ]]; then
        echo ""
        log_warn "Upgrade wurde unterbrochen!"
        log_warn "Status prüfen:"
        log_warn "  - Neuer Cluster: ${DATA_DIR:-unbekannt}"
        log_warn "  - Alter Cluster: ${V_OLD_DIR:-unbekannt}"
        echo ""
        log_warn "Falls Rollback nötig:"
        log_warn "  rm -rf \"${DATA_DIR:-}\""
        log_warn "  mv \"${V_OLD_DIR:-}\" \"${DATA_DIR:-}\""
    fi
    exit ${exit_code}
}
trap cleanup EXIT INT TERM

# =============================================================================
# Argumente parsen
# =============================================================================
while [[ $# -gt 0 ]]; do
    case $1 in
        --from)
            MAJOR_OLD="$2"
            shift 2
            ;;
        --to)
            MAJOR_NEW="$2"
            shift 2
            ;;
        --volume-name)
            VOLUME_NAME="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --help|-h)
            usage
            ;;
        -*)
            die "Unbekannte Option: $1"
            ;;
        *)
            VOL_DIR="$1"
            shift
            ;;
    esac
done

# =============================================================================
# Volume-Pfad ermitteln
# =============================================================================
if [[ -n "${VOLUME_NAME}" ]]; then
    command -v docker >/dev/null || die "docker nicht gefunden"
    VOL_DIR=$(docker volume inspect "${VOLUME_NAME}" --format '{{.Mountpoint}}' 2>/dev/null | sed 's|/_data$||') \
        || die "Docker Volume '${VOLUME_NAME}' nicht gefunden"
    VOL_DIR=$(dirname "${VOL_DIR}")
fi

if [[ -z "${VOL_DIR}" ]]; then
    echo "Fehler: Volume-Pfad oder --volume-name erforderlich"
    echo ""
    echo "Nutzung: $0 [OPTIONS] <VOLUME_PATH>"
    echo "         $0 [OPTIONS] --volume-name <DOCKER_VOLUME_NAME>"
    echo ""
    echo "Für Hilfe: $0 --help"
    exit 1
fi

VOL_DIR="$(readlink -f "${VOL_DIR}")"
DATA_DIR="${VOL_DIR}/_data"
V_OLD_DIR="${VOL_DIR}/v${MAJOR_OLD}"
HELPER_IMAGE="tianon/postgres-upgrade:${MAJOR_OLD}-to-${MAJOR_NEW}"

# =============================================================================
# Pre-Flight Checks
# =============================================================================
log "PostgreSQL Upgrade ${MAJOR_OLD} → ${MAJOR_NEW}"
log "Volume: ${VOL_DIR}"
echo ""

# Docker verfügbar?
command -v docker >/dev/null || die "docker nicht gefunden"

# Data-Verzeichnis existiert?
[[ -d "${DATA_DIR}" ]] || die "_data existiert nicht: ${DATA_DIR}"

# PG_VERSION prüfen
if [[ -f "${DATA_DIR}/PG_VERSION" ]]; then
    OLD_VER="$(tr -d '[:space:]' < "${DATA_DIR}/PG_VERSION")"
    log_info "Gefundene Cluster-Version: ${OLD_VER}"

    # Prüfen ob Version passt
    if [[ ! "${OLD_VER}" =~ ^${MAJOR_OLD} ]]; then
        die "PG_VERSION ist ${OLD_VER}, erwartet ${MAJOR_OLD}.x"
    fi
else
    die "PG_VERSION nicht gefunden in ${DATA_DIR}"
fi

# Backup-Verzeichnis existiert bereits?
if [[ -e "${V_OLD_DIR}" ]]; then
    die "Verzeichnis ${V_OLD_DIR} existiert bereits – bitte löschen oder umbenennen."
fi

# Laufende Container prüfen
log_info "Prüfe auf laufende Container..."
RUNNING_CONTAINERS=$(docker ps --format '{{.Names}}:{{.Mounts}}' 2>/dev/null | grep -F "${VOL_DIR}" | cut -d: -f1 || true)
if [[ -n "${RUNNING_CONTAINERS}" ]]; then
    die "Folgende Container nutzen dieses Volume:\n${RUNNING_CONTAINERS}\n\nBitte zuerst stoppen!"
fi
log_info "Keine laufenden Container gefunden ✓"

# Speicherplatz prüfen (für Logs, mindestens 100MB frei)
AVAILABLE_KB=$(df -k "${VOL_DIR}" | tail -1 | awk '{print $4}')
if [[ ${AVAILABLE_KB} -lt 102400 ]]; then
    log_warn "Weniger als 100MB freier Speicher verfügbar"
fi

# Helper-Image verfügbar?
log_info "Prüfe Helper-Image ${HELPER_IMAGE}..."
if ! docker image inspect "${HELPER_IMAGE}" >/dev/null 2>&1; then
    log_info "Image nicht lokal vorhanden, wird heruntergeladen..."
    if [[ "${DRY_RUN}" == "false" ]]; then
        docker pull "${HELPER_IMAGE}" || die "Konnte Image nicht herunterladen: ${HELPER_IMAGE}"
    else
        log_info "[DRY-RUN] Würde Image herunterladen: ${HELPER_IMAGE}"
    fi
else
    log_info "Image lokal vorhanden ✓"
fi

# =============================================================================
# Zusammenfassung & Bestätigung
# =============================================================================
echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo " UPGRADE-PLAN"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""
echo "  Quell-Version:    PostgreSQL ${MAJOR_OLD} (${OLD_VER})"
echo "  Ziel-Version:     PostgreSQL ${MAJOR_NEW}"
echo "  Volume-Pfad:      ${VOL_DIR}"
echo "  Aktueller Cluster: ${DATA_DIR}"
echo "  Backup nach:      ${V_OLD_DIR}"
echo "  Helper-Image:     ${HELPER_IMAGE}"
echo ""
echo "  Methode: Hardlinks (kein zusätzlicher Speicher benötigt)"
echo ""
echo "═══════════════════════════════════════════════════════════════════════════"

if [[ "${DRY_RUN}" == "true" ]]; then
    echo ""
    log_info "[DRY-RUN] Alle Checks bestanden. Keine Änderungen vorgenommen."
    exit 0
fi

if [[ "${FORCE}" == "false" ]]; then
    echo ""
    read -p "Upgrade starten? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Abgebrochen."
        exit 0
    fi
fi

# =============================================================================
# Logging Setup
# =============================================================================
LOG_ROOT="/var/lib/docker/pg-upgrade-$(basename "${VOL_DIR}")"
mkdir -p "${LOG_ROOT}"/{logs,markers}
LOG_FILE="${LOG_ROOT}/logs/pg_upgrade_${MAJOR_OLD}_to_${MAJOR_NEW}_$(date +%Y%m%d_%H%M%S).log"

log "Log-Datei: ${LOG_FILE}"

# =============================================================================
# Upgrade durchführen
# =============================================================================
UPGRADE_STARTED=true

# Schritt 1: Alte Daten verschieben
log "Schritt 1/4: Verschiebe ${DATA_DIR} → ${V_OLD_DIR} (Backup)..."
mv "${DATA_DIR}" "${V_OLD_DIR}"

# Schritt 2: Neues Verzeichnis vorbereiten
log "Schritt 2/4: Erstelle neues _data Verzeichnis..."
mkdir -p "${DATA_DIR}"
chown -R "${PG_UID}:${PG_GID}" "${V_OLD_DIR}" "${DATA_DIR}"

# Schritt 3: pg_upgrade ausführen
log "Schritt 3/4: Starte pg_upgrade..."
echo "--- pg_upgrade Start: $(date) ---" >> "${LOG_FILE}"

if ! docker run --rm \
    -e PGUSER=nocodb \
    -v "${V_OLD_DIR}:/var/lib/postgresql/old/data:ro" \
    -v "${DATA_DIR}:/var/lib/postgresql/new/data" \
    "${HELPER_IMAGE}" 2>&1 | tee -a "${LOG_FILE}"; then

    echo ""
    log_warn "pg_upgrade fehlgeschlagen!"
    log_warn ""
    log_warn "Rollback wird durchgeführt..."

    rm -rf "${DATA_DIR}"
    mv "${V_OLD_DIR}" "${DATA_DIR}"

    log "Rollback abgeschlossen. Alter Cluster wiederhergestellt."
    die "Upgrade fehlgeschlagen. Siehe Log: ${LOG_FILE}"
fi

echo "--- pg_upgrade Ende: $(date) ---" >> "${LOG_FILE}"

# Schritt 4: Erfolg prüfen
log "Schritt 4/4: Verifiziere neuen Cluster..."

if [[ ! -f "${DATA_DIR}/PG_VERSION" ]]; then
    log_warn "PG_VERSION fehlt im neuen Cluster!"
    log_warn "Rollback wird durchgeführt..."

    rm -rf "${DATA_DIR}"
    mv "${V_OLD_DIR}" "${DATA_DIR}"

    die "Upgrade fehlgeschlagen: Neuer Cluster unvollständig"
fi

NEW_VER="$(tr -d '[:space:]' < "${DATA_DIR}/PG_VERSION")"
log_info "Neuer Cluster erstellt (PG_VERSION: ${NEW_VER})"

# Eigentümer sicherstellen
chown -R "${PG_UID}:${PG_GID}" "${DATA_DIR}"

# Erfolgs-Marker
touch "${LOG_ROOT}/markers/upgraded_${MAJOR_OLD}_to_${MAJOR_NEW}.ok"

# =============================================================================
# Erfolg
# =============================================================================
UPGRADE_STARTED=false

echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo " UPGRADE ERFOLGREICH"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""
echo "  Aktiver Cluster (neu):  ${DATA_DIR}  (PostgreSQL ${NEW_VER})"
echo "  Backup (alt):           ${V_OLD_DIR}  (PostgreSQL ${OLD_VER})"
echo "  Log-Datei:              ${LOG_FILE}"
echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""
echo "Nächste Schritte:"
echo ""
echo "  1. Container starten:"
echo "     docker compose up -d"
echo ""
echo "  2. Statistiken aktualisieren (empfohlen):"
echo "     docker exec <container> vacuumdb --all --analyze-in-stages"
echo ""
echo "  3. Extensions aktualisieren (falls genutzt):"
echo "     docker exec <container> psql -U nocodb -d nocodb -c 'ALTER EXTENSION <name> UPDATE;'"
echo ""
echo "  4. Nach erfolgreicher Prüfung - Backup löschen (optional):"
echo "     rm -rf \"${V_OLD_DIR}\""
echo ""
echo "═══════════════════════════════════════════════════════════════════════════"

exit 0
