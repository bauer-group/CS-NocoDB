<!-- markdownlint-disable MD024 MD033 MD060 -->

# NocoDB Docker Stack

> **Language / Sprache:** [Deutsch](#deutsch) | [English](#english)

---

<a id="deutsch"></a>

## Deutsch

Production-ready Docker Compose Setup für [NocoDB](https://nocodb.com/) mit PostgreSQL, optimiert für Performance und Sicherheit.

### Features

- **PostgreSQL 18** mit Production-Tuning (SSD/NVMe optimiert)
- **5 Deployment-Modi** für verschiedene Umgebungen
- **Automatisierte Backups** mit S3-Support und Alerting
- **Init Container** für Datenbank-Wartung (Collation Check/Auto-Fix)
- **IPv4 + IPv6** Dual-Stack Netzwerk
- **Healthchecks** für alle Services
- **Strukturierte Logs** mit Rotation

### Quick Start

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

### Deployment-Modi

| Modus | Compose-File | Beschreibung | Anwendungsfall |
|-------|--------------|--------------|----------------|
| **Local** | `docker-compose.local.yml` | Direkter Port-Zugriff | Entwicklung, lokaler Test |
| **Traefik** | `docker-compose.traefik.yml` | HTTPS + Let's Encrypt | Production |
| **Traefik Local** | `docker-compose.traefik-local.yml` | HTTP + IP-Whitelist | Internes Netzwerk |
| **Traefik Header Auth** | `docker-compose.traefik-header-auth.yml` | HTTPS + Header-Auth | API-Zugriff, Reverse Proxy |
| **Development** | `docker-compose.development.yml` | Lokale Image-Builds + MinIO | Entwicklung, Testing |

#### Local Mode

Direkter Zugriff über Port - ideal für Entwicklung:

```bash
docker compose -f docker-compose.local.yml up -d
# Zugriff: http://localhost:${EXPOSED_APP_PORT}
```

#### Traefik HTTPS (Production)

Vollständig abgesichert mit automatischen Let's Encrypt Zertifikaten:

```bash
docker compose -f docker-compose.traefik.yml up -d
# Zugriff: https://${SERVICE_HOSTNAME}
```

**Voraussetzungen:**
- Externes Traefik-Netzwerk (`PROXY_NETWORK`)
- DNS-Eintrag für `SERVICE_HOSTNAME`
- Traefik mit `letsencrypt` Certresolver

#### Traefik Local (IP-Whitelist)

HTTP-Zugriff nur von bestimmten IP-Bereichen - ideal für interne Netzwerke:

```bash
docker compose -f docker-compose.traefik-local.yml up -d
# Zugriff: http://${SERVICE_HOSTNAME} (nur von IPs in IP_WHITELIST)
```

#### Traefik Header Auth

HTTPS mit zusaetzlicher Header-Authentifizierung - ideal für API-Zugriffe:

```bash
docker compose -f docker-compose.traefik-header-auth.yml up -d
# Zugriff: https://${SERVICE_HOSTNAME}
# Header: X-BAUERGROUP-Auth: ${HEADER_AUTH_SECRET}
```

```bash
# Beispiel curl-Aufruf
curl -H "X-BAUERGROUP-Auth: your-secret" https://db.example.com/api/v2/...
```

#### Development Mode

Für lokale Entwicklung mit Image-Builds und MinIO:

```bash
# Build und Start
docker compose -f docker-compose.development.yml up -d --build

# Mit Backup-Sidecar und MinIO
docker compose -f docker-compose.development.yml --profile backup up -d --build
```

**Features:**
- Lokale Image-Builds aus `src/` Verzeichnis
- MinIO als lokaler S3-Ersatz (Port 9001)
- Ideal für Testing von Backup-Funktionen

### Backup-Sidecar

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
- CLI für manuelle Backups und Restore

Siehe [docs/BACKUP.md](docs/BACKUP.md) für die vollstaendige Dokumentation.

### Konfiguration

#### Basis-Konfiguration

| Variable | Beschreibung | Beispiel |
|----------|--------------|----------|
| `STACK_NAME` | Eindeutiger Stack-Name | `db_crm_app_domain_com` |
| `DATABASE_PASSWORD` | PostgreSQL Passwort | `openssl rand -base64 16` |
| `TIME_ZONE` | Zeitzone | `Europe/Berlin` |

#### Traefik-Konfiguration

| Variable | Beschreibung | Beispiel |
|----------|--------------|----------|
| `SERVICE_HOSTNAME` | DNS-Hostname | `db.example.com` |
| `PROXY_NETWORK` | Traefik Netzwerk | `EDGEPROXY` |
| `IP_WHITELIST` | Erlaubte IP-Bereiche | `192.168.0.0/16,10.0.0.0/8` |
| `HEADER_AUTH_SECRET` | Auth-Header Secret | `uuidgen` |

#### PostgreSQL Performance Tuning

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

#### SMTP-Konfiguration

```bash
SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_TLS=true
SMTP_FROM=no-reply@example.com
SMTP_USER=
SMTP_PASSWORD=
```

#### S3/MinIO Storage (optional)

Attachments können auf S3-kompatiblem Storage gespeichert werden:

```bash
NC_S3_BUCKET_NAME=nocodb-bucket
NC_S3_REGION=us-east-1
NC_S3_ENDPOINT=https://s3.example.com
NC_S3_ACCESS_KEY=
NC_S3_ACCESS_SECRET=
NC_S3_FORCE_PATH_STYLE=true
```

### Projektstruktur

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
│       ├── cli.py                        # CLI für manuelle Operationen
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

### Wartung

#### Logs anzeigen

```bash
# Alle Logs
docker compose -f docker-compose.traefik.yml logs -f

# Nur NocoDB
docker compose -f docker-compose.traefik.yml logs -f nocodb-server

# Nur PostgreSQL
docker compose -f docker-compose.traefik.yml logs -f database-server
```

#### Automatisiertes Backup (empfohlen)

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

Siehe [docs/BACKUP.md](docs/BACKUP.md) für Details.

#### Manuelles Backup

```bash
# Datenbank-Dump
docker exec ${STACK_NAME}_DATABASE pg_dump -U nocodb nocodb > backup_$(date +%Y%m%d).sql

# Volume-Backup
docker run --rm \
  -v ${STACK_NAME}-postgres:/data:ro \
  -v $(pwd):/backup \
  alpine tar czf /backup/postgres_$(date +%Y%m%d).tar.gz -C /data .
```

#### Manuelles Backup wiederherstellen

```bash
# Aus SQL-Dump
cat backup_20250125.sql | docker exec -i ${STACK_NAME}_DATABASE psql -U nocodb nocodb
```

#### PostgreSQL Upgrade

Major-Version Upgrade (z.B. 15 -> 18):

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

#### Audit-Tabellen bereinigen

Bei `NC_DISABLE_AUDIT=true` können alte Audit-Daten entfernt werden:

```bash
docker compose exec database-server psql -U nocodb -d nocodb -c "TRUNCATE TABLE nc_audit_v2;"
```

Siehe [docs/AUDIT_CLEANUP.md](docs/AUDIT_CLEANUP.md) für Details.

### Diagnose

#### Health-Status prüfen

```bash
# Container-Status
docker compose ps

# NocoDB Health-Endpoint
curl -sf http://localhost:8080/api/v1/health

# PostgreSQL
docker exec ${STACK_NAME}_DATABASE pg_isready -U nocodb -d nocodb
```

#### Datenbank-Verbindung testen

```bash
docker exec -it ${STACK_NAME}_DATABASE psql -U nocodb -d nocodb -c "SELECT version();"
```

#### Performance-Diagnose

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

### NocoDB Einstellungen

Diese Einstellungen sind in allen Compose-Files vorkonfiguriert:

| Einstellung | Wert | Beschreibung |
|-------------|------|--------------|
| `NC_DISABLE_TELE` | `true` | Telemetrie deaktiviert |
| `NC_DISABLE_AUDIT` | `true` | Audit-Logging deaktiviert |
| `NC_INVITE_ONLY_SIGNUP` | `true` | Registrierung nur per Einladung |

#### Optionale Einstellungen

In `.env` konfigurierbar:

```bash
# Attachment-Limits
NC_ATTACHMENT_FIELD_SIZE=262144000  # 256 MB
NC_MAX_ATTACHMENTS_ALLOWED=50

# Sichere Attachments (Pre-signed URLs)
NC_SECURE_ATTACHMENTS=true
NC_ATTACHMENT_EXPIRE_SECONDS=7200
```

### Sicherheit

#### Best Practices

1. **Starkes Passwort** für `DATABASE_PASSWORD` generieren:
   ```bash
   openssl rand -base64 24
   ```

2. **Einzigartige Secrets** für Header-Auth:
   ```bash
   uuidgen
   ```

3. **IP-Whitelist** restriktiv halten

4. **Regelmässige Updates** von NocoDB und PostgreSQL

5. **Backups** regelmässig erstellen und testen

#### Netzwerk-Isolation

Jeder Stack erhält ein eigenes isoliertes Bridge-Netzwerk mit IPv6-Unterstützung. Die Datenbank ist nur intern erreichbar (kein Port-Binding).

### Updates

#### NocoDB Update

```bash
# 1. Neuestes Image pullen
docker compose pull

# 2. Container neu starten
docker compose up -d

# 3. Logs prüfen
docker compose logs -f nocodb-server
```

#### Pinned Version

Für kontrollierte Updates kann eine feste Version gesetzt werden:

```bash
# In .env
NOCODB_VERSION=0.204.0
```

### Troubleshooting

#### Container startet nicht

```bash
# Logs prüfen
docker compose logs nocodb-server

# Häufige Ursachen:
# - DATABASE_PASSWORD nicht gesetzt
# - Port bereits belegt
# - Datenbank nicht erreichbar
```

#### Datenbank-Verbindungsfehler

```bash
# PostgreSQL-Status prüfen
docker exec ${STACK_NAME}_DATABASE pg_isready -U nocodb -d nocodb

# Verbindungstest
docker exec ${STACK_NAME}_DATABASE psql -U nocodb -d nocodb -c "SELECT 1;"
```

#### Migrations-Fehler

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

### Referenzen

- [NocoDB Dokumentation](https://docs.nocodb.com/)
- [NocoDB GitHub](https://github.com/nocodb/nocodb)
- [NocoDB Environment Variables](https://docs.nocodb.com/getting-started/self-hosted/environment-variables/)
- [PostgreSQL Dokumentation](https://www.postgresql.org/docs/)
- [Traefik Dokumentation](https://doc.traefik.io/traefik/)

### Lizenz

Dieses Docker-Setup ist frei verwendbar. NocoDB selbst unterliegt der [AGPL-3.0 Lizenz](https://github.com/nocodb/nocodb/blob/develop/LICENSE).

---

<a id="english"></a>

## English

Production-ready Docker Compose setup for [NocoDB](https://nocodb.com/) with PostgreSQL, optimized for performance and security.

### Features

- **PostgreSQL 18** with production tuning (SSD/NVMe optimized)
- **5 deployment modes** for different environments
- **Automated backups** with S3 support and alerting
- **Init container** for database maintenance (collation check/auto-fix)
- **IPv4 + IPv6** dual-stack networking
- **Health checks** for all services
- **Structured logs** with rotation

### Quick Start

```bash
# 1. Clone repository / copy files
cd /opt/stacks/nocodb

# 2. Create configuration
cp .env.example .env

# 3. Edit .env (at minimum change DATABASE_PASSWORD!)
nano .env

# 4. Start stack
docker compose -f docker-compose.local.yml up -d

# 5. Open browser
open http://localhost:8080
```

### Deployment Modes

| Mode | Compose File | Description | Use Case |
|------|-------------|-------------|----------|
| **Local** | `docker-compose.local.yml` | Direct port access | Development, local testing |
| **Traefik** | `docker-compose.traefik.yml` | HTTPS + Let's Encrypt | Production |
| **Traefik Local** | `docker-compose.traefik-local.yml` | HTTP + IP whitelist | Internal network |
| **Traefik Header Auth** | `docker-compose.traefik-header-auth.yml` | HTTPS + header auth | API access, reverse proxy |
| **Development** | `docker-compose.development.yml` | Local image builds + MinIO | Development, testing |

#### Local Mode

Direct port access - ideal for development:

```bash
docker compose -f docker-compose.local.yml up -d
# Access: http://localhost:${EXPOSED_APP_PORT}
```

#### Traefik HTTPS (Production)

Fully secured with automatic Let's Encrypt certificates:

```bash
docker compose -f docker-compose.traefik.yml up -d
# Access: https://${SERVICE_HOSTNAME}
```

**Prerequisites:**
- External Traefik network (`PROXY_NETWORK`)
- DNS record for `SERVICE_HOSTNAME`
- Traefik with `letsencrypt` cert resolver

#### Traefik Local (IP Whitelist)

HTTP access only from specific IP ranges - ideal for internal networks:

```bash
docker compose -f docker-compose.traefik-local.yml up -d
# Access: http://${SERVICE_HOSTNAME} (only from IPs in IP_WHITELIST)
```

#### Traefik Header Auth

HTTPS with additional header authentication - ideal for API access:

```bash
docker compose -f docker-compose.traefik-header-auth.yml up -d
# Access: https://${SERVICE_HOSTNAME}
# Header: X-BAUERGROUP-Auth: ${HEADER_AUTH_SECRET}
```

```bash
# Example curl request
curl -H "X-BAUERGROUP-Auth: your-secret" https://db.example.com/api/v2/...
```

#### Development Mode

For local development with image builds and MinIO:

```bash
# Build and start
docker compose -f docker-compose.development.yml up -d --build

# With backup sidecar and MinIO
docker compose -f docker-compose.development.yml --profile backup up -d --build
```

**Features:**

- Local image builds from `src/` directory
- MinIO as local S3 replacement (port 9001)
- Ideal for testing backup functionality

### Backup Sidecar

All compose files support an optional backup sidecar:

```bash
# Enable with --profile backup
docker compose -f docker-compose.traefik.yml --profile backup up -d
```

**Features:**

- Automatic PostgreSQL dumps (pg_dump)
- NocoDB API export (bases, tables, records, attachments)
- S3-compatible storage (AWS S3, MinIO, Wasabi, etc.)
- Cron or interval scheduling
- Alerting (email, Teams, webhook)
- CLI for manual backups and restore

See [docs/BACKUP.md](docs/BACKUP.md) for full documentation.

### Configuration

#### Basic Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `STACK_NAME` | Unique stack name | `db_crm_app_domain_com` |
| `DATABASE_PASSWORD` | PostgreSQL password | `openssl rand -base64 16` |
| `TIME_ZONE` | Timezone | `Europe/Berlin` |

#### Traefik Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `SERVICE_HOSTNAME` | DNS hostname | `db.example.com` |
| `PROXY_NETWORK` | Traefik network | `EDGEPROXY` |
| `IP_WHITELIST` | Allowed IP ranges | `192.168.0.0/16,10.0.0.0/8` |
| `HEADER_AUTH_SECRET` | Auth header secret | `uuidgen` |

#### PostgreSQL Performance Tuning

Defaults are optimized for 8GB RAM and SSD/NVMe. Adjust in `.env`:

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

For HDD systems:
```bash
PG_RANDOM_PAGE_COST=4.0      # instead of 1.1
PG_EFFECTIVE_IO_CONCURRENCY=2 # instead of 200
```

#### SMTP Configuration

```bash
SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_TLS=true
SMTP_FROM=no-reply@example.com
SMTP_USER=
SMTP_PASSWORD=
```

#### S3/MinIO Storage (optional)

Attachments can be stored on S3-compatible storage:

```bash
NC_S3_BUCKET_NAME=nocodb-bucket
NC_S3_REGION=us-east-1
NC_S3_ENDPOINT=https://s3.example.com
NC_S3_ACCESS_KEY=
NC_S3_ACCESS_SECRET=
NC_S3_FORCE_PATH_STYLE=true
```

### Project Structure

```
NocoDB/
├── .env.example                          # Configuration template
├── .env                                  # Active configuration (not in git)
├── README.md                             # This file
│
├── docker-compose.local.yml              # Local mode (port binding)
├── docker-compose.traefik.yml            # Traefik HTTPS
├── docker-compose.traefik-local.yml      # Traefik HTTP + IP whitelist
├── docker-compose.traefik-header-auth.yml # Traefik HTTPS + header auth
├── docker-compose.development.yml        # Development with MinIO
│
├── src/
│   ├── nocodb/                           # NocoDB base image (custom build)
│   │   └── Dockerfile
│   │
│   ├── nocodb-init/                      # Init container (DB maintenance)
│   │   ├── Dockerfile
│   │   ├── main.py
│   │   └── tasks/
│   │       ├── 01_collation_check.py
│   │       └── 02_audit_cleanup.py
│   │
│   └── nocodb-backup/                    # Backup sidecar container
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── main.py                       # Entry point
│       ├── cli.py                        # CLI for manual operations
│       ├── config.py                     # Configuration (Pydantic Settings)
│       ├── scheduler.py                  # Cron/interval scheduler
│       ├── backup/                       # Backup modules
│       │   ├── pg_dump.py               # PostgreSQL dump
│       │   ├── nocodb_exporter.py       # NocoDB API export
│       │   └── file_backup.py           # NocoDB data files (tar.gz)
│       ├── storage/
│       │   └── s3_client.py             # S3-compatible storage
│       ├── alerting/                     # Notifications
│       │   ├── email_alerter.py
│       │   ├── teams_alerter.py
│       │   └── webhook_alerter.py
│       └── tests/                        # Unit tests
│
├── docs/
│   ├── AUDIT_CLEANUP.md                  # Audit table cleanup
│   ├── BACKUP.md                         # Backup & recovery documentation
│   └── PG_UPGRADE.md                     # PostgreSQL upgrade guide
│
└── tools/
    └── pg_upgrade_inplace.sh             # PostgreSQL upgrade script
```

### Maintenance

#### View Logs

```bash
# All logs
docker compose -f docker-compose.traefik.yml logs -f

# NocoDB only
docker compose -f docker-compose.traefik.yml logs -f nocodb-server

# PostgreSQL only
docker compose -f docker-compose.traefik.yml logs -f database-server
```

#### Automated Backup (recommended)

With the backup sidecar enabled:

```bash
# Enable backup sidecar
docker compose -f docker-compose.traefik.yml --profile backup up -d

# Run immediate backup
docker exec ${STACK_NAME}_BACKUP python main.py --now

# List backups
docker exec ${STACK_NAME}_BACKUP python cli.py list

# Restore database
docker exec ${STACK_NAME}_BACKUP python cli.py restore-dump 2024-02-05_05-15-00

# Restore data files (after restore-dump)
docker exec ${STACK_NAME}_BACKUP python cli.py restore-files 2024-02-05_05-15-00

# Restore table schema on a new system
docker exec ${STACK_NAME}_BACKUP python cli.py restore-schema 2024-02-05_05-15-00

# Import records into existing tables
docker exec ${STACK_NAME}_BACKUP python cli.py restore-records 2024-02-05_05-15-00 --base "My_Base"
```

See [docs/BACKUP.md](docs/BACKUP.md) for details.

#### Manual Backup

```bash
# Database dump
docker exec ${STACK_NAME}_DATABASE pg_dump -U nocodb nocodb > backup_$(date +%Y%m%d).sql

# Volume backup
docker run --rm \
  -v ${STACK_NAME}-postgres:/data:ro \
  -v $(pwd):/backup \
  alpine tar czf /backup/postgres_$(date +%Y%m%d).tar.gz -C /data .
```

#### Restore Manual Backup

```bash
# From SQL dump
cat backup_20250125.sql | docker exec -i ${STACK_NAME}_DATABASE psql -U nocodb nocodb
```

#### PostgreSQL Upgrade

Major version upgrade (e.g. 15 -> 18):

```bash
# 1. Stop stack
docker compose down

# 2. Run upgrade
sudo ./tools/pg_upgrade_inplace.sh --volume-name ${STACK_NAME}-postgres

# 3. Start stack
docker compose up -d

# 4. Update statistics
docker exec ${STACK_NAME}_DATABASE vacuumdb -U nocodb --all --analyze-in-stages
```

See [docs/PG_UPGRADE.md](docs/PG_UPGRADE.md) for details.

#### Clean Up Audit Tables

When `NC_DISABLE_AUDIT=true`, old audit data can be removed:

```bash
docker compose exec database-server psql -U nocodb -d nocodb -c "TRUNCATE TABLE nc_audit_v2;"
```

See [docs/AUDIT_CLEANUP.md](docs/AUDIT_CLEANUP.md) for details.

### Diagnostics

#### Check Health Status

```bash
# Container status
docker compose ps

# NocoDB health endpoint
curl -sf http://localhost:8080/api/v1/health

# PostgreSQL
docker exec ${STACK_NAME}_DATABASE pg_isready -U nocodb -d nocodb
```

#### Test Database Connection

```bash
docker exec -it ${STACK_NAME}_DATABASE psql -U nocodb -d nocodb -c "SELECT version();"
```

#### Performance Diagnostics

When database CPU is high:

```bash
# Show active queries
docker exec ${STACK_NAME}_DATABASE psql -U nocodb -d nocodb -c "
SELECT pid, usename, state, now() - query_start AS runtime, query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY runtime DESC;"
```

See [docs/AUDIT_CLEANUP.md](docs/AUDIT_CLEANUP.md#diagnose-datenbank-100-cpu) for more diagnostic queries.

### NocoDB Settings

These settings are preconfigured in all compose files:

| Setting | Value | Description |
|---------|-------|-------------|
| `NC_DISABLE_TELE` | `true` | Telemetry disabled |
| `NC_DISABLE_AUDIT` | `true` | Audit logging disabled |
| `NC_INVITE_ONLY_SIGNUP` | `true` | Invite-only registration |

#### Optional Settings

Configurable in `.env`:

```bash
# Attachment limits
NC_ATTACHMENT_FIELD_SIZE=262144000  # 256 MB
NC_MAX_ATTACHMENTS_ALLOWED=50

# Secure attachments (pre-signed URLs)
NC_SECURE_ATTACHMENTS=true
NC_ATTACHMENT_EXPIRE_SECONDS=7200
```

### Security

#### Best Practices

1. **Strong password** for `DATABASE_PASSWORD`:
   ```bash
   openssl rand -base64 24
   ```

2. **Unique secrets** for header auth:
   ```bash
   uuidgen
   ```

3. Keep **IP whitelist** restrictive

4. **Regular updates** for NocoDB and PostgreSQL

5. **Create and test backups** regularly

#### Network Isolation

Each stack gets its own isolated bridge network with IPv6 support. The database is only accessible internally (no port binding).

### Updates

#### NocoDB Update

```bash
# 1. Pull latest image
docker compose pull

# 2. Restart containers
docker compose up -d

# 3. Check logs
docker compose logs -f nocodb-server
```

#### Pinned Version

For controlled updates, a fixed version can be set:

```bash
# In .env
NOCODB_VERSION=0.204.0
```

### Troubleshooting

#### Container Won't Start

```bash
# Check logs
docker compose logs nocodb-server

# Common causes:
# - DATABASE_PASSWORD not set
# - Port already in use
# - Database unreachable
```

#### Database Connection Errors

```bash
# Check PostgreSQL status
docker exec ${STACK_NAME}_DATABASE pg_isready -U nocodb -d nocodb

# Connection test
docker exec ${STACK_NAME}_DATABASE psql -U nocodb -d nocodb -c "SELECT 1;"
```

#### Migration Errors

For `nc_audit_v2_old does not exist`:

```bash
docker compose exec database-server psql -U nocodb -d nocodb -c "
CREATE TABLE IF NOT EXISTS nc_audit_v2_old (
    id VARCHAR(20) PRIMARY KEY,
    op_type VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);"
```

See [docs/AUDIT_CLEANUP.md](docs/AUDIT_CLEANUP.md#fix-auditmigration-fehler-nc_audit_v2_old-does-not-exist).

### References

- [NocoDB Documentation](https://docs.nocodb.com/)
- [NocoDB GitHub](https://github.com/nocodb/nocodb)
- [NocoDB Environment Variables](https://docs.nocodb.com/getting-started/self-hosted/environment-variables/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Traefik Documentation](https://doc.traefik.io/traefik/)

### License

This Docker setup is free to use. NocoDB itself is licensed under the [AGPL-3.0 License](https://github.com/nocodb/nocodb/blob/develop/LICENSE).
