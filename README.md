# NocoDB Docker Stack

Production-ready Docker Compose Setup für [NocoDB](https://nocodb.com/) mit PostgreSQL, optimiert für Performance und Sicherheit.

## Features

- **PostgreSQL 18** mit Production-Tuning (SSD/NVMe optimiert)
- **5 Deployment-Modi** fuer verschiedene Umgebungen
- **Automatisierte Backups** mit S3-Support und Alerting
- **Init Container** fuer Datenbank-Wartung (Collation Check/Auto-Fix)
- **IPv4 + IPv6** Dual-Stack Netzwerk
- **Healthchecks** fuer alle Services
- **Strukturierte Logs** mit Rotation
- **Umfangreiche Dokumentation** auf Deutsch

## Quick Start

```bash
# 1. Repository klonen / Dateien kopieren
cd /opt/stacks/nocodb

# 2. Konfiguration erstellen
cp .env.example .env

# 3. .env anpassen (mindestens DATABASE_PASSWORD ändern!)
nano .env

# 4. Stack starten
docker compose -f docker-compose.local.yml up -d

# 5. Browser öffnen
open http://localhost:8080
```

## Deployment-Modi

| Modus | Compose-File | Beschreibung | Anwendungsfall |
|-------|--------------|--------------|----------------|
| **Local** | `docker-compose.local.yml` | Direkter Port-Zugriff | Entwicklung, lokaler Test |
| **Traefik** | `docker-compose.traefik.yml` | HTTPS + Let's Encrypt | Production |
| **Traefik Local** | `docker-compose.traefik-local.yml` | HTTP + IP-Whitelist | Internes Netzwerk |
| **Traefik Header Auth** | `docker-compose.traefik-header-auth.yml` | HTTPS + Header-Auth | API-Zugriff, Reverse Proxy |
| **Development** | `docker-compose.development.yml` | Lokale Image-Builds + MinIO | Entwicklung, Testing |

### Local Mode

Direkter Zugriff über Port - ideal für Entwicklung:

```bash
docker compose -f docker-compose.local.yml up -d
# Zugriff: http://localhost:${EXPOSED_APP_PORT}
```

### Traefik HTTPS (Production)

Vollständig abgesichert mit automatischen Let's Encrypt Zertifikaten:

```bash
docker compose -f docker-compose.traefik.yml up -d
# Zugriff: https://${SERVICE_HOSTNAME}
```

**Voraussetzungen:**
- Externes Traefik-Netzwerk (`PROXY_NETWORK`)
- DNS-Eintrag für `SERVICE_HOSTNAME`
- Traefik mit `letsencrypt` Certresolver

### Traefik Local (IP-Whitelist)

HTTP-Zugriff nur von bestimmten IP-Bereichen - ideal für interne Netzwerke:

```bash
docker compose -f docker-compose.traefik-local.yml up -d
# Zugriff: http://${SERVICE_HOSTNAME} (nur von IPs in IP_WHITELIST)
```

### Traefik Header Auth

HTTPS mit zusaetzlicher Header-Authentifizierung - ideal fuer API-Zugriffe:

```bash
docker compose -f docker-compose.traefik-header-auth.yml up -d
# Zugriff: https://${SERVICE_HOSTNAME}
# Header: X-BAUERGROUP-Auth: ${HEADER_AUTH_SECRET}
```

```bash
# Beispiel curl-Aufruf
curl -H "X-BAUERGROUP-Auth: your-secret" https://db.example.com/api/v2/...
```

### Development Mode

Fuer lokale Entwicklung mit Image-Builds und MinIO:

```bash
# Build und Start
docker compose -f docker-compose.development.yml up -d --build

# Mit Backup-Sidecar und MinIO
docker compose -f docker-compose.development.yml --profile backup up -d --build
```

**Features:**
- Lokale Image-Builds aus `src/` Verzeichnis
- MinIO als lokaler S3-Ersatz (Port 9001)
- Ideal fuer Testing von Backup-Funktionen

## Backup-Sidecar

Alle Compose-Files unterstuetzen einen optionalen Backup-Sidecar:

```bash
# Aktivieren mit --profile backup
docker compose -f docker-compose.traefik.yml --profile backup up -d
```

**Features:**
- Automatische PostgreSQL-Dumps (pg_dump)
- NocoDB API Export (Bases, Tables, Records, Attachments)
- S3-kompatibles Storage (AWS S3, MinIO, Wasabi, etc.)
- Cron oder Interval Scheduling
- Alerting (Email, Teams, Webhook)
- CLI fuer manuelle Backups und Restore

Siehe [docs/BACKUP.md](docs/BACKUP.md) fuer die vollstaendige Dokumentation.

## Konfiguration

### Basis-Konfiguration

| Variable | Beschreibung | Beispiel |
|----------|--------------|----------|
| `STACK_NAME` | Eindeutiger Stack-Name | `db_crm_app_domain_com` |
| `DATABASE_PASSWORD` | PostgreSQL Passwort | `openssl rand -base64 16` |
| `TIME_ZONE` | Zeitzone | `Europe/Berlin` |

### Traefik-Konfiguration

| Variable | Beschreibung | Beispiel |
|----------|--------------|----------|
| `SERVICE_HOSTNAME` | DNS-Hostname | `db.example.com` |
| `PROXY_NETWORK` | Traefik Netzwerk | `EDGEPROXY` |
| `IP_WHITELIST` | Erlaubte IP-Bereiche | `192.168.0.0/16,10.0.0.0/8` |
| `HEADER_AUTH_SECRET` | Auth-Header Secret | `uuidgen` |

### PostgreSQL Performance Tuning

Die Standardwerte sind für 8GB RAM und SSD/NVMe optimiert. Anpassung in `.env`:

```bash
# ┌─────────────────────────────────────────────────────────────────────────────┐
# │ MEMORY SETTINGS                                                             │
# ├─────────────────────────────────┬───────────┬───────────┬─────────┬─────────┤
# │ ENV Variable                    │ 4 GB RAM  │ 8 GB RAM  │ 16 GB   │ 32 GB   │
# ├─────────────────────────────────┼───────────┼───────────┼─────────┼─────────┤
# │ PG_SHARED_BUFFERS               │ 1GB       │ 2GB       │ 4GB     │ 8GB     │
# │ PG_EFFECTIVE_CACHE_SIZE         │ 3GB       │ 6GB       │ 12GB    │ 24GB    │
# │ PG_WORK_MEM                     │ 4MB       │ 8MB       │ 16MB    │ 32MB    │
# │ PG_MAINTENANCE_WORK_MEM         │ 128MB     │ 256MB     │ 512MB   │ 1GB     │
# └─────────────────────────────────┴───────────┴───────────┴─────────┴─────────┘
```

Für HDD-Systeme:
```bash
PG_RANDOM_PAGE_COST=4.0      # statt 1.1
PG_EFFECTIVE_IO_CONCURRENCY=2 # statt 200
```

### SMTP-Konfiguration

```bash
SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_TLS=true
SMTP_FROM=no-reply@example.com
SMTP_USER=
SMTP_PASSWORD=
```

### S3/MinIO Storage (optional)

Attachments können auf S3-kompatiblem Storage gespeichert werden:

```bash
NC_S3_BUCKET_NAME=nocodb-bucket
NC_S3_REGION=us-east-1
NC_S3_ENDPOINT=https://s3.example.com
NC_S3_ACCESS_KEY=
NC_S3_ACCESS_SECRET=
NC_S3_FORCE_PATH_STYLE=true
```

## Projektstruktur

```
NocoDB/
├── .env.example                          # Konfigurationsvorlage
├── .env                                  # Aktive Konfiguration (nicht im Git)
├── README.md                             # Diese Datei
│
├── docker-compose.local.yml              # Local Mode (Port-Binding)
├── docker-compose.traefik.yml            # Traefik HTTPS
├── docker-compose.traefik-local.yml      # Traefik HTTP + IP-Whitelist
├── docker-compose.traefik-header-auth.yml # Traefik HTTPS + Header-Auth
├── docker-compose.development.yml        # Development mit MinIO
│
├── src/
│   ├── nocodb/                           # NocoDB Base Image (Custom Build)
│   │   └── Dockerfile
│   │
│   ├── nocodb-init/                      # Init Container (DB-Wartung)
│   │   ├── Dockerfile
│   │   ├── main.py
│   │   └── tasks/
│   │       ├── 01_collation_check.py
│   │       └── 02_audit_cleanup.py
│   │
│   └── nocodb-backup/                    # Backup Sidecar Container
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── main.py                       # Entry Point
│       ├── cli.py                        # CLI fuer manuelle Operationen
│       ├── config.py                     # Konfiguration (Pydantic Settings)
│       ├── scheduler.py                  # Cron/Interval Scheduler
│       ├── backup/                       # Backup-Module
│       │   ├── pg_dump.py               # PostgreSQL Dump
│       │   ├── nocodb_exporter.py       # NocoDB API Export
│       │   └── file_backup.py           # NocoDB Data Files (tar.gz)
│       ├── storage/
│       │   └── s3_client.py             # S3-kompatibles Storage
│       ├── alerting/                     # Benachrichtigungen
│       │   ├── email_alerter.py
│       │   ├── teams_alerter.py
│       │   └── webhook_alerter.py
│       └── tests/                        # Unit Tests
│
├── docs/
│   ├── AUDIT_CLEANUP.md                  # Audit-Tabellen Bereinigung
│   ├── BACKUP.md                         # Backup & Recovery Dokumentation
│   └── PG_UPGRADE.md                     # PostgreSQL Upgrade Anleitung
│
└── tools/
    └── pg_upgrade_inplace.sh             # PostgreSQL Upgrade Script
```

## Wartung

### Logs anzeigen

```bash
# Alle Logs
docker compose -f docker-compose.traefik.yml logs -f

# Nur NocoDB
docker compose -f docker-compose.traefik.yml logs -f nocodb-server

# Nur PostgreSQL
docker compose -f docker-compose.traefik.yml logs -f database-server
```

### Automatisiertes Backup (empfohlen)

Mit aktiviertem Backup-Sidecar:

```bash
# Backup-Sidecar aktivieren
docker compose -f docker-compose.traefik.yml --profile backup up -d

# Sofort-Backup ausfuehren
docker exec ${STACK_NAME}_BACKUP python main.py --now

# Backups auflisten
docker exec ${STACK_NAME}_BACKUP python cli.py list

# Datenbank wiederherstellen
docker exec ${STACK_NAME}_BACKUP python cli.py restore-dump 2024-02-05_05-15-00

# Daten-Dateien wiederherstellen (nach restore-dump)
docker exec ${STACK_NAME}_BACKUP python cli.py restore-files 2024-02-05_05-15-00

# Tabellen-Schema auf neuem System wiederherstellen
docker exec ${STACK_NAME}_BACKUP python cli.py restore-schema 2024-02-05_05-15-00

# Records in bestehende Tabellen importieren
docker exec ${STACK_NAME}_BACKUP python cli.py restore-records 2024-02-05_05-15-00 --base "Meine_Base"
```

Siehe [docs/BACKUP.md](docs/BACKUP.md) fuer Details.

### Manuelles Backup

```bash
# Datenbank-Dump
docker exec ${STACK_NAME}_DATABASE pg_dump -U nocodb nocodb > backup_$(date +%Y%m%d).sql

# Volume-Backup
docker run --rm \
  -v ${STACK_NAME}-postgres:/data:ro \
  -v $(pwd):/backup \
  alpine tar czf /backup/postgres_$(date +%Y%m%d).tar.gz -C /data .
```

### Manuelles Backup wiederherstellen

```bash
# Aus SQL-Dump
cat backup_20250125.sql | docker exec -i ${STACK_NAME}_DATABASE psql -U nocodb nocodb
```

### PostgreSQL Upgrade

Major-Version Upgrade (z.B. 15 → 18):

```bash
# 1. Stack stoppen
docker compose down

# 2. Upgrade durchführen
sudo ./tools/pg_upgrade_inplace.sh --volume-name ${STACK_NAME}-postgres

# 3. Stack starten
docker compose up -d

# 4. Statistiken aktualisieren
docker exec ${STACK_NAME}_DATABASE vacuumdb -U nocodb --all --analyze-in-stages
```

Siehe [docs/PG_UPGRADE.md](docs/PG_UPGRADE.md) für Details.

### Audit-Tabellen bereinigen

Bei `NC_DISABLE_AUDIT=true` können alte Audit-Daten entfernt werden:

```bash
docker compose exec database-server psql -U nocodb -d nocodb -c "TRUNCATE TABLE nc_audit_v2;"
```

Siehe [docs/AUDIT_CLEANUP.md](docs/AUDIT_CLEANUP.md) für Details.

## Diagnose

### Health-Status prüfen

```bash
# Container-Status
docker compose ps

# NocoDB Health-Endpoint
curl -sf http://localhost:8080/api/v1/health

# PostgreSQL
docker exec ${STACK_NAME}_DATABASE pg_isready -U nocodb -d nocodb
```

### Datenbank-Verbindung testen

```bash
docker exec -it ${STACK_NAME}_DATABASE psql -U nocodb -d nocodb -c "SELECT version();"
```

### Performance-Diagnose

Bei hoher CPU-Last der Datenbank:

```bash
# Aktive Queries anzeigen
docker exec ${STACK_NAME}_DATABASE psql -U nocodb -d nocodb -c "
SELECT pid, usename, state, now() - query_start AS runtime, query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY runtime DESC;"
```

Siehe [docs/AUDIT_CLEANUP.md](docs/AUDIT_CLEANUP.md#diagnose-datenbank-100-cpu) für weitere Diagnose-Queries.

## NocoDB Einstellungen

Diese Einstellungen sind in allen Compose-Files vorkonfiguriert:

| Einstellung | Wert | Beschreibung |
|-------------|------|--------------|
| `NC_DISABLE_TELE` | `true` | Telemetrie deaktiviert |
| `NC_DISABLE_AUDIT` | `true` | Audit-Logging deaktiviert |
| `NC_INVITE_ONLY_SIGNUP` | `true` | Registrierung nur per Einladung |

### Optionale Einstellungen

In `.env` konfigurierbar:

```bash
# Attachment-Limits
NC_ATTACHMENT_FIELD_SIZE=262144000  # 256 MB
NC_MAX_ATTACHMENTS_ALLOWED=50

# Sichere Attachments (Pre-signed URLs)
NC_SECURE_ATTACHMENTS=true
NC_ATTACHMENT_EXPIRE_SECONDS=7200
```

## Sicherheit

### Best Practices

1. **Starkes Passwort** für `DATABASE_PASSWORD` generieren:
   ```bash
   openssl rand -base64 24
   ```

2. **Einzigartige Secrets** für Header-Auth:
   ```bash
   uuidgen
   ```

3. **IP-Whitelist** restriktiv halten

4. **Regelmäßige Updates** von NocoDB und PostgreSQL

5. **Backups** regelmäßig erstellen und testen

### Netzwerk-Isolation

Jeder Stack erhält ein eigenes isoliertes Bridge-Netzwerk mit IPv6-Unterstützung. Die Datenbank ist nur intern erreichbar (kein Port-Binding).

## Updates

### NocoDB Update

```bash
# 1. Neuestes Image pullen
docker compose pull

# 2. Container neu starten
docker compose up -d

# 3. Logs prüfen
docker compose logs -f nocodb-server
```

### Pinned Version

Für kontrollierte Updates kann eine feste Version gesetzt werden:

```bash
# In .env
NOCODB_VERSION=0.204.0
```

## Troubleshooting

### Container startet nicht

```bash
# Logs prüfen
docker compose logs nocodb-server

# Häufige Ursachen:
# - DATABASE_PASSWORD nicht gesetzt
# - Port bereits belegt
# - Datenbank nicht erreichbar
```

### Datenbank-Verbindungsfehler

```bash
# PostgreSQL-Status prüfen
docker exec ${STACK_NAME}_DATABASE pg_isready -U nocodb -d nocodb

# Verbindungstest
docker exec ${STACK_NAME}_DATABASE psql -U nocodb -d nocodb -c "SELECT 1;"
```

### Migrations-Fehler

Bei `nc_audit_v2_old does not exist`:

```bash
docker compose exec database-server psql -U nocodb -d nocodb -c "
CREATE TABLE IF NOT EXISTS nc_audit_v2_old (
    id VARCHAR(20) PRIMARY KEY,
    op_type VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);"
```

Siehe [docs/AUDIT_CLEANUP.md](docs/AUDIT_CLEANUP.md#fix-auditmigration-fehler-nc_audit_v2_old-does-not-exist).

## Referenzen

- [NocoDB Dokumentation](https://docs.nocodb.com/)
- [NocoDB GitHub](https://github.com/nocodb/nocodb)
- [NocoDB Environment Variables](https://docs.nocodb.com/getting-started/self-hosted/environment-variables/)
- [PostgreSQL Dokumentation](https://www.postgresql.org/docs/)
- [Traefik Dokumentation](https://doc.traefik.io/traefik/)

## Lizenz

Dieses Docker-Setup ist frei verwendbar. NocoDB selbst unterliegt der [AGPL-3.0 Lizenz](https://github.com/nocodb/nocodb/blob/develop/LICENSE).
