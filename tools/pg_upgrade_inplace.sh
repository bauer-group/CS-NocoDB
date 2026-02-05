#!/usr/bin/env bash
# =============================================================================
# pg_upgrade_inplace.sh - PostgreSQL In-Place Major Version Upgrade
# =============================================================================
# Führt ein in-place Upgrade von PostgreSQL im selben Docker Volume durch.
# Standardmäßig werden Daten KOPIERT (sicher, aber benötigt doppelten Speicher).
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
#   --link                Hardlinks statt Kopie (schnell, KEIN Rollback möglich!)
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
PG_UID=""  # Wird aus bestehenden Daten ausgelesen
PG_GID=""  # Wird aus bestehenden Daten ausgelesen
PG_USER="${PG_USER:-nocodb}"
PG_DATABASE="${PG_DATABASE:-nocodb}"
DRY_RUN=false
FORCE=false
USE_LINK=false
NO_CHECKSUMS=true  # Standard: Checksums deaktivieren (Kompatibilität mit älteren Clustern)
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
        --link)
            USE_LINK=true
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

VOL_DIR="$(readlink -f "${VOL_DIR}" 2>/dev/null)" || die "Ungültiger Volume-Pfad: ${VOL_DIR}"
[[ -n "${VOL_DIR}" ]] || die "Volume-Pfad konnte nicht aufgelöst werden"
[[ -d "${VOL_DIR}" ]] || die "Volume-Verzeichnis existiert nicht: ${VOL_DIR}"
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

# UID/GID aus bestehenden Daten auslesen
PG_UID=$(stat -c '%u' "${DATA_DIR}/PG_VERSION" 2>/dev/null) || PG_UID=999
PG_GID=$(stat -c '%g' "${DATA_DIR}/PG_VERSION" 2>/dev/null) || PG_GID=999
log_info "Erkannte Eigentümer: UID=${PG_UID}, GID=${PG_GID}"

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

# Speicherplatz prüfen
AVAILABLE_KB=$(df -k "${VOL_DIR}" | tail -1 | awk '{print $4}')
DATA_SIZE_KB=$(du -sk "${DATA_DIR}" 2>/dev/null | awk '{print $1}' || echo "0")

if [[ "${USE_LINK}" == "false" ]]; then
    # Copy-Modus: benötigt genug Platz für komplette Datenkopie
    NEEDED_KB=$((DATA_SIZE_KB + 102400))  # Daten + 100MB Puffer
    if [[ ${AVAILABLE_KB} -lt ${NEEDED_KB} ]]; then
        die "Nicht genug Speicherplatz für Copy-Modus!\n  Benötigt: ~$((NEEDED_KB / 1024)) MB\n  Verfügbar: $((AVAILABLE_KB / 1024)) MB\n\nOptionen:\n  1. Speicher freigeben\n  2. --link verwenden (ACHTUNG: kein Rollback möglich!)"
    fi
    log_info "Speicherplatz ausreichend: $((AVAILABLE_KB / 1024)) MB frei, ~$((DATA_SIZE_KB / 1024)) MB benötigt ✓"
else
    # Link-Modus: nur minimaler Platz für Logs nötig
    if [[ ${AVAILABLE_KB} -lt 102400 ]]; then
        log_warn "Weniger als 100MB freier Speicher verfügbar"
    fi
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
echo "  Quell-Version:     PostgreSQL ${MAJOR_OLD} (${OLD_VER})"
echo "  Ziel-Version:      PostgreSQL ${MAJOR_NEW}"
echo "  Volume-Pfad:       ${VOL_DIR}"
echo "  Helper-Image:      ${HELPER_IMAGE}"
echo ""
echo "  Verzeichnisstruktur VORHER:"
echo "    ${DATA_DIR}/                        ← PG ${MAJOR_OLD} Daten"
echo ""
echo "  Verzeichnisstruktur NACHHER:"
echo "    ${DATA_DIR}/${MAJOR_NEW}/docker/    ← PG ${MAJOR_NEW} Daten"
echo "    ${V_OLD_DIR}/                       ← PG ${MAJOR_OLD} Backup"
echo ""
if [[ "${USE_LINK}" == "true" ]]; then
    echo "  Methode: Hardlinks (schnell, KEIN Rollback nach Start möglich!)"
else
    echo "  Methode: Kopie (sicher, Rollback jederzeit möglich)"
fi
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
if ! mkdir -p "${LOG_ROOT}"/{logs,markers} 2>/dev/null; then
    # Fallback zu temporärem Verzeichnis wenn /var/lib/docker nicht schreibbar
    LOG_ROOT="/tmp/pg-upgrade-$(basename "${VOL_DIR}")"
    mkdir -p "${LOG_ROOT}"/{logs,markers} || die "Kann Log-Verzeichnis nicht erstellen: ${LOG_ROOT}"
    log_warn "Verwende Fallback Log-Verzeichnis: ${LOG_ROOT}"
fi
LOG_FILE="${LOG_ROOT}/logs/pg_upgrade_${MAJOR_OLD}_to_${MAJOR_NEW}_$(date +%Y%m%d_%H%M%S).log"

log "Log-Datei: ${LOG_FILE}"

# =============================================================================
# Upgrade durchführen
# =============================================================================
UPGRADE_STARTED=true

# Schritt 1: Alte Daten verschieben
log "Schritt 1/4: Verschiebe ${DATA_DIR} → ${V_OLD_DIR} (Backup)..."
if ! mv "${DATA_DIR}" "${V_OLD_DIR}"; then
    die "Konnte Datenverzeichnis nicht verschieben: ${DATA_DIR} → ${V_OLD_DIR}"
fi

# Schritt 2: Neues Verzeichnis vorbereiten
log "Schritt 2/4: Erstelle neues _data Verzeichnis..."
if ! mkdir -p "${DATA_DIR}"; then
    log_warn "mkdir fehlgeschlagen - führe Rollback durch..."
    mv "${V_OLD_DIR}" "${DATA_DIR}" 2>/dev/null || true
    die "Konnte neues Datenverzeichnis nicht erstellen: ${DATA_DIR}"
fi

if ! chown -R "${PG_UID}:${PG_GID}" "${V_OLD_DIR}" "${DATA_DIR}"; then
    log_warn "chown fehlgeschlagen - führe Rollback durch..."
    rm -rf "${DATA_DIR}"
    mv "${V_OLD_DIR}" "${DATA_DIR}" 2>/dev/null || true
    die "Konnte Eigentümer nicht setzen für: ${V_OLD_DIR}, ${DATA_DIR}"
fi

# Schritt 3: pg_upgrade ausführen
log "Schritt 3/4: Starte pg_upgrade..."
echo "--- pg_upgrade Start: $(date) ---" >> "${LOG_FILE}"

# pg_upgrade Optionen
PG_UPGRADE_OPTS=""
if [[ "${USE_LINK}" == "true" ]]; then
    PG_UPGRADE_OPTS="--link"
    log_warn "ACHTUNG: Hardlink-Modus aktiv - nach erstem Start ist KEIN Rollback mehr möglich!"
fi

# initdb Optionen für neuen Cluster
INITDB_ARGS="--username=${PG_USER}"
if [[ "${NO_CHECKSUMS}" == "true" ]]; then
    INITDB_ARGS="${INITDB_ARGS} --no-data-checksums"
    log_info "Checksums deaktiviert (Kompatibilität mit altem Cluster)"
fi
log_info "Neuer Cluster wird mit Superuser '${PG_USER}' initialisiert"

if ! docker run --rm \
    -e PGUSER="${PG_USER}" \
    -e POSTGRES_USER="${PG_USER}" \
    -e POSTGRES_INITDB_ARGS="${INITDB_ARGS}" \
    -v "${DATA_DIR}:/var/lib/postgresql" \
    -v "${V_OLD_DIR}:/var/lib/postgresql/${MAJOR_OLD}/data" \
    "${HELPER_IMAGE}" ${PG_UPGRADE_OPTS} 2>&1 | tee -a "${LOG_FILE}"; then

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

# Neuer PGDATA Pfad (tianon-Image erstellt /var/lib/postgresql/18/docker)
NEW_PGDATA="${DATA_DIR}/${MAJOR_NEW}/docker"

if [[ ! -f "${NEW_PGDATA}/PG_VERSION" ]]; then
    log_warn "PG_VERSION fehlt im neuen Cluster!"
    log_warn "Erwartet: ${NEW_PGDATA}/PG_VERSION"
    log_warn "Rollback wird durchgeführt..."

    rm -rf "${DATA_DIR}/${MAJOR_NEW}"
    mv "${V_OLD_DIR}" "${DATA_DIR}"

    die "Upgrade fehlgeschlagen: Neuer Cluster unvollständig"
fi

NEW_VER="$(tr -d '[:space:]' < "${NEW_PGDATA}/PG_VERSION")"
log_info "Neuer Cluster erstellt: ${NEW_PGDATA} (PG_VERSION: ${NEW_VER})"

# Daten bleiben in _data/18/docker/ - dort erwartet PG18 sie!

# pg_hba.conf vom alten Cluster übernehmen (Authentifizierungseinstellungen)
OLD_PG_HBA="${V_OLD_DIR}/pg_hba.conf"
NEW_PG_HBA="${NEW_PGDATA}/pg_hba.conf"
if [[ -f "${OLD_PG_HBA}" ]]; then
    log_info "Kopiere pg_hba.conf vom alten Cluster..."
    cp "${OLD_PG_HBA}" "${NEW_PG_HBA}"
    log_info "pg_hba.conf übernommen ✓"
else
    log_warn "Keine pg_hba.conf im alten Cluster gefunden: ${OLD_PG_HBA}"
fi

# Eigentümer sicherstellen
chown -R "${PG_UID}:${PG_GID}" "${DATA_DIR}"

# Schritt 5/5: Statistiken aktualisieren (vacuumdb)
log "Schritt 5/5: Aktualisiere Statistiken (vacuumdb)..."
TEMP_CONTAINER="pg_upgrade_vacuum_$$"

# Temporären PostgreSQL-Container starten (existierender Cluster, kein initdb)
# Das postgres-Image erkennt existierende Daten und startet direkt ohne initdb
log_info "Starte temporären PostgreSQL ${MAJOR_NEW} Container..."
if docker run -d --rm \
    --name "${TEMP_CONTAINER}" \
    -e PGDATA="/var/lib/postgresql/${MAJOR_NEW}/docker" \
    -v "${DATA_DIR}:/var/lib/postgresql" \
    "postgres:${MAJOR_NEW}" >/dev/null 2>&1; then

    # Warten bis PostgreSQL bereit ist
    log_info "Warte auf PostgreSQL..."
    WAIT_COUNT=0
    while ! docker exec "${TEMP_CONTAINER}" pg_isready -U "${PG_USER}" >/dev/null 2>&1; do
        sleep 1
        WAIT_COUNT=$((WAIT_COUNT + 1))
        if [[ ${WAIT_COUNT} -ge 30 ]]; then
            log_warn "Timeout beim Warten auf PostgreSQL - überspringe vacuumdb"
            docker stop "${TEMP_CONTAINER}" >/dev/null 2>&1 || true
            break
        fi
    done

    if [[ ${WAIT_COUNT} -lt 30 ]]; then
        log_info "PostgreSQL bereit, führe vacuumdb aus..."
        if docker exec "${TEMP_CONTAINER}" vacuumdb \
            --all \
            --analyze-in-stages \
            --username="${PG_USER}" 2>&1 | tee -a "${LOG_FILE}"; then
            log_info "vacuumdb erfolgreich ✓"
        else
            log_warn "vacuumdb fehlgeschlagen (nicht kritisch)"
        fi

        # Container stoppen
        log_info "Stoppe temporären Container..."
        docker stop "${TEMP_CONTAINER}" >/dev/null 2>&1 || true
    fi
else
    log_warn "Konnte temporären Container nicht starten - überspringe vacuumdb"
    log_warn "Führe nach dem ersten Start manuell aus: vacuumdb --all --analyze-in-stages"
fi

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
echo "  Neuer Cluster:          ${NEW_PGDATA}  (PostgreSQL ${NEW_VER})"
echo "  Backup (alt):           ${V_OLD_DIR}  (PostgreSQL ${OLD_VER})"
echo "  Log-Datei:              ${LOG_FILE}"
if [[ "${USE_LINK}" == "true" ]]; then
    echo ""
    echo "  ⚠️  HARDLINK-MODUS: Nach dem ersten Start des neuen Clusters"
    echo "     ist ein Rollback NICHT mehr möglich!"
else
    echo ""
    echo "  ✅ COPY-MODUS: Rollback jederzeit möglich (vor UND nach Start)"
fi
echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""
echo "  Host-Struktur:"
echo "    _data/${MAJOR_NEW}/docker/    ← PG ${MAJOR_NEW} Daten"
echo ""
echo "  docker-compose.yml anpassen:"
echo "    image: postgres:${MAJOR_NEW}"
echo "    volumes:"
echo "      - postgres-data:/var/lib/postgresql        # War: /var/lib/postgresql/data"
echo "    environment:"
echo "      - PGDATA=/var/lib/postgresql/${MAJOR_NEW}/docker"
echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""
echo "Nächste Schritte:"
echo ""
echo "  1. docker-compose.yml anpassen (siehe oben)"
echo ""
echo "  2. Container starten:"
echo "     docker compose up -d"
echo ""
echo "  3. Extensions aktualisieren (falls genutzt):"
echo "     docker exec <container> psql -U ${PG_USER} -d ${PG_DATABASE} -c 'ALTER EXTENSION <name> UPDATE;'"
echo ""
if [[ "${USE_LINK}" == "false" ]]; then
    echo "  4. Falls Rollback nötig:"
    echo "     docker compose down"
    echo "     rm -rf \"${DATA_DIR}/${MAJOR_NEW}\""
    echo "     mv \"${V_OLD_DIR}\" \"${DATA_DIR}\""
    echo "     # docker-compose.yml: Mount zurück auf /var/lib/postgresql/data"
    echo ""
    echo "  5. Nach erfolgreicher Prüfung - Backup löschen (optional):"
else
    echo "  4. Nach erfolgreicher Prüfung - Backup löschen (optional):"
fi
echo "     rm -rf \"${V_OLD_DIR}\""
echo ""
echo "═══════════════════════════════════════════════════════════════════════════"

exit 0
