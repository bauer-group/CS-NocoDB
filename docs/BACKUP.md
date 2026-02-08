# NocoDB Backup & Recovery

Automatisierte Backup-Loesung fuer NocoDB mit PostgreSQL-Dumps, API-Exports und S3-Integration.

## Uebersicht

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ BACKUP-ARCHITEKTUR                                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  nocodb-backup Container                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                     │   │
│  │   Scheduler (Cron/Interval)                                         │   │
│  │         │                                                           │   │
│  │         ▼                                                           │   │
│  │   ┌─────────────┐     ┌─────────────────────┐                       │   │
│  │   │  pg_dump    │────►│  database.sql.gz    │                       │   │
│  │   └─────────────┘     └─────────────────────┘                       │   │
│  │         │                                                           │   │
│  │         ▼                                                           │   │
│  │   ┌─────────────┐     ┌─────────────────────┐                       │   │
│  │   │ NocoDB API  │────►│  bases/tables/json  │                       │   │
│  │   │  Export     │     │  + attachments      │                       │   │
│  │   └─────────────┘     └─────────────────────┘                       │   │
│  │         │                                                           │   │
│  │         ▼                                                           │   │
│  │   ┌─────────────┐     ┌─────────────────────┐                       │   │
│  │   │ S3 Upload   │────►│  s3://bucket/       │                       │   │
│  │   │ (optional)  │     │    prefix/backup/   │                       │   │
│  │   └─────────────┘     └─────────────────────┘                       │   │
│  │         │                                                           │   │
│  │         ▼                                                           │   │
│  │   ┌─────────────┐     ┌─────────────────────┐                       │   │
│  │   │  Alerting   │────►│  Email/Teams/       │                       │   │
│  │   │             │     │  Webhook            │                       │   │
│  │   └─────────────┘     └─────────────────────┘                       │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Backup-Methoden

### 1. PostgreSQL Database Dump (pg_dump)

Vollstaendiger Datenbank-Dump fuer Disaster Recovery:

- **Format:** Komprimiertes SQL (`database.sql.gz`)
- **Inhalt:** Komplette Datenbankstruktur und Daten
- **Wiederherstellung:** Mit `psql` oder dem CLI-Tool
- **Empfehlung:** Primaeres Backup fuer vollstaendige Wiederherstellung

### 2. NocoDB Data Files (tar.gz)

1:1 Archiv des NocoDB-Datenverzeichnisses:

- **Format:** Komprimiertes Tar-Archiv (`nocodb-data.tar.gz`)
- **Inhalt:** Alle Dateien aus dem NocoDB-Datenverzeichnis (Uploads, Attachments)
- **Wiederherstellung:** Direktes Entpacken in das NocoDB-Datenverzeichnis
- **Empfehlung:** Fuer Disaster Recovery zusammen mit `restore-dump`

Aktivierung: `NOCODB_BACKUP_INCLUDE_FILES=true` (Standard).
Deaktivieren wenn Attachments auf S3 liegen (`NC_S3_BUCKET_NAME`).

### 3. NocoDB API Export

Strukturierter Export ueber die NocoDB REST API:

- **Bases:** Metadaten aller Bases
- **Tables:** Schema und Struktur
- **Records:** Daten als JSON
- **Attachments:** Download ueber NocoDB API (unabhaengig ob lokal oder S3 gespeichert)

**Struktur:**
```
2024-02-05_05-15-00/
├── database.sql.gz           # PostgreSQL Dump
├── nocodb-data.tar.gz        # NocoDB Daten-Dateien (1:1 Archiv)
├── bases/
│   └── {base_name}/
│       ├── metadata.json     # Base Metadaten
│       └── tables/
│           └── {table_name}/
│               ├── schema.json      # Table Schema
│               ├── records.json.gz  # Alle Records (gzip-komprimiert)
│               └── attachments/     # Heruntergeladene Dateien
│                   └── {field}/{filename}
└── manifest.json             # Backup-Manifest
```

## Quick Start

### 1. Backup aktivieren

```bash
# Production mit Backup-Sidecar
docker compose -f docker-compose.traefik.yml --profile backup up -d

# Oder fuer Development mit MinIO
docker compose -f docker-compose.development.yml --profile backup up -d
```

### 2. API Token erstellen

Fuer API-basierte Backups wird ein NocoDB API Token benoetigt:

1. NocoDB oeffnen
2. **Account Settings** > **Tokens**
3. **Add new token** > Token-Namen eingeben
4. Token kopieren und in `.env` eintragen:

```bash
NOCODB_API_TOKEN=nc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3. Konfiguration anpassen

```bash
# .env
NOCODB_BACKUP_SCHEDULE_HOUR=5
NOCODB_BACKUP_SCHEDULE_MINUTE=15
NOCODB_BACKUP_RETENTION_COUNT=30
```

## Konfiguration

### Basis-Einstellungen

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `NOCODB_BACKUP_SCHEDULE_ENABLED` | `true` | Backup-Scheduler aktivieren |
| `NOCODB_BACKUP_SCHEDULE_MODE` | `cron` | `cron` oder `interval` |
| `NOCODB_BACKUP_RETENTION_COUNT` | `30` | Anzahl aufzubewahrender Backups |

### Schedule-Modi

#### Cron-Mode (taegliches Backup zu fester Uhrzeit)

```bash
NOCODB_BACKUP_SCHEDULE_MODE=cron
NOCODB_BACKUP_SCHEDULE_HOUR=5
NOCODB_BACKUP_SCHEDULE_MINUTE=15
NOCODB_BACKUP_SCHEDULE_DAY_OF_WEEK=*  # * = taeglich, 0-6 = bestimmte Tage
```

#### Interval-Mode (alle N Stunden)

```bash
NOCODB_BACKUP_SCHEDULE_MODE=interval
NOCODB_BACKUP_SCHEDULE_INTERVAL_HOURS=24
```

### Backup-Komponenten

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `NOCODB_BACKUP_DATABASE_DUMP` | `true` | PostgreSQL pg_dump ausfuehren |
| `NOCODB_BACKUP_DATABASE_DUMP_TIMEOUT` | `1800` | Timeout in Sekunden (30 min) |
| `NOCODB_BACKUP_INCLUDE_FILES` | `true` | NocoDB Daten-Dateien als tar.gz sichern |
| `NOCODB_BACKUP_API_EXPORT` | `true` | NocoDB API Export ausfuehren |
| `NOCODB_BACKUP_INCLUDE_RECORDS` | `true` | Tabellen-Records exportieren |
| `NOCODB_BACKUP_INCLUDE_ATTACHMENTS` | `true` | Attachments herunterladen (API Export) |

### S3 Storage

```bash
# S3-kompatibles Storage (AWS S3, MinIO, Wasabi, etc.)
NOCODB_BACKUP_S3_ENDPOINT_URL=https://s3.eu-central-1.amazonaws.com
NOCODB_BACKUP_S3_BUCKET=nocodb-backups
NOCODB_BACKUP_S3_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE
NOCODB_BACKUP_S3_SECRET_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
NOCODB_BACKUP_S3_REGION=eu-central-1
NOCODB_BACKUP_S3_PREFIX=nocodb-backup

# Lokales Backup nach S3-Upload loeschen
NOCODB_BACKUP_DELETE_LOCAL_AFTER_S3=false
```

### Alerting

```bash
# Alerting aktivieren
NOCODB_BACKUP_ALERT_ENABLED=true
NOCODB_BACKUP_ALERT_LEVEL=warnings  # errors, warnings, all
NOCODB_BACKUP_ALERT_CHANNELS=email,teams  # Komma-getrennt

# Email (benoetigt SMTP-Konfiguration)
NOCODB_BACKUP_ALERT_EMAIL=admin@example.com

# Microsoft Teams
NOCODB_BACKUP_TEAMS_WEBHOOK=https://outlook.office.com/webhook/...

# Generischer Webhook
NOCODB_BACKUP_WEBHOOK_URL=https://your-webhook.example.com
```

## CLI-Befehle

Der Backup-Container bietet ein CLI fuer manuelle Operationen:

### Sofort-Backup ausfuehren

```bash
# Vollstaendiges Backup (DB + API)
docker exec ${STACK_NAME}_BACKUP python main.py --now

# Nur Datenbank-Dump
docker exec ${STACK_NAME}_BACKUP python main.py --now --db-only
```

### Backups auflisten

```bash
docker exec ${STACK_NAME}_BACKUP python cli.py list
```

**Ausgabe:**
```
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━┳━━━━━━━━━━━┓
┃ #  ┃ Backup ID           ┃ Local ┃ S3  ┃ Size      ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━╇━━━━━━━━━━━┩
│ 1  │ 2024-02-05_05-15-00 │ +     │ +   │ 125.3 MB  │
│ 2  │ 2024-02-04_05-15-00 │ +     │ +   │ 124.8 MB  │
│ 3  │ 2024-02-03_05-15-00 │ -     │ +   │ 123.5 MB  │
└────┴─────────────────────┴───────┴─────┴───────────┘
```

### Backup-Details anzeigen

```bash
docker exec ${STACK_NAME}_BACKUP python cli.py show 2024-02-05_05-15-00
```

### Backup loeschen

```bash
# Lokal und S3
docker exec ${STACK_NAME}_BACKUP python cli.py delete 2024-02-05_05-15-00

# Nur lokal
docker exec ${STACK_NAME}_BACKUP python cli.py delete 2024-02-05_05-15-00 --local-only

# Ohne Bestaetigung
docker exec ${STACK_NAME}_BACKUP python cli.py delete 2024-02-05_05-15-00 --force
```

### Backup von S3 herunterladen

```bash
docker exec ${STACK_NAME}_BACKUP python cli.py download 2024-02-05_05-15-00
```

### Backup inspizieren

```bash
docker exec ${STACK_NAME}_BACKUP python cli.py inspect 2024-02-05_05-15-00
```

**Ausgabe:**

```
2024-02-05_05-15-00
├── database.sql.gz (45.2 MB)
├── manifest.json
└── bases/
    └── Meine_Base/
        ├── metadata.json
        ├── Kunden/ (1250 records, 1.2 MB)
        │   └── attachments/ (34 files, 89.5 MB)
        └── Projekte/ (480 records, 0.3 MB)
```

### Datenbank wiederherstellen

```bash
docker exec ${STACK_NAME}_BACKUP python cli.py restore-dump 2024-02-05_05-15-00
```

**WARNUNG:** Dies ueberschreibt die gesamte Datenbank!

### Daten-Dateien wiederherstellen (nach restore-dump)

```bash
docker exec ${STACK_NAME}_BACKUP python cli.py restore-files 2024-02-05_05-15-00
```

Stellt die NocoDB-Dateien (Uploads, Attachments) aus dem `nocodb-data.tar.gz` Archiv
direkt in das NocoDB-Datenverzeichnis wieder her. Die Dateien landen 1:1 an ihren
Original-Pfaden, passend zu den Referenzen in der wiederhergestellten Datenbank.

**Wichtig:**

- NocoDB muss waehrend der Wiederherstellung gestoppt sein
- Verwenden nach `restore-dump` fuer eine vollstaendige Disaster Recovery
- Nur relevant fuer lokale Attachments (nicht bei S3-Storage)

### Tabellen-Schema wiederherstellen (neues System)

```bash
# Alle Bases und Tabellen aus Backup erstellen
docker exec ${STACK_NAME}_BACKUP python cli.py restore-schema 2024-02-05_05-15-00

# Nur eine bestimmte Base wiederherstellen
docker exec ${STACK_NAME}_BACKUP python cli.py restore-schema 2024-02-05_05-15-00 --base "Meine_Base"

# Nur eine bestimmte Tabelle wiederherstellen
docker exec ${STACK_NAME}_BACKUP python cli.py restore-schema 2024-02-05_05-15-00 --base "Meine_Base" --table "Kunden"

# Bereits existierende Tabellen ueberspringen
docker exec ${STACK_NAME}_BACKUP python cli.py restore-schema 2024-02-05_05-15-00 --skip-existing
```

**Hinweise:**

- Erstellt Bases automatisch, falls sie noch nicht existieren
- Systemspalten (Id, CreatedAt, UpdatedAt) werden von NocoDB automatisch angelegt
- Virtuelle Spalten (Links, Lookup, Rollup, Formula) werden uebersprungen und
  muessen manuell in der NocoDB-Oberflaeche nachgebaut werden
- Das Schema stammt aus den `schema.json` Dateien im API-Export (vollstaendige Spaltendefinitionen)
- Nach `restore-schema` koennen Records mit `restore-records` importiert werden

### Records wiederherstellen (einzelne Tabellen/Bases)

```bash
# Alle Tabellen aller Bases wiederherstellen
docker exec ${STACK_NAME}_BACKUP python cli.py restore-records 2024-02-05_05-15-00

# Nur eine bestimmte Base wiederherstellen
docker exec ${STACK_NAME}_BACKUP python cli.py restore-records 2024-02-05_05-15-00 --base "Meine_Base"

# Nur eine bestimmte Tabelle wiederherstellen
docker exec ${STACK_NAME}_BACKUP python cli.py restore-records 2024-02-05_05-15-00 --base "Meine_Base" --table "Kunden"

# Records MIT Attachments wiederherstellen
docker exec ${STACK_NAME}_BACKUP python cli.py restore-records 2024-02-05_05-15-00 \
    --base "Meine_Base" --with-attachments

# Ohne Bestaetigung
docker exec ${STACK_NAME}_BACKUP python cli.py restore-records 2024-02-05_05-15-00 --base "Meine_Base" --force
```

**Hinweis:** Tabellen muessen in NocoDB bereits mit kompatiblem Schema existieren.
Records werden via API eingefuegt - bestehende Daten bleiben erhalten (keine Deduplizierung).

### Attachments wiederherstellen (nach restore-dump)

```bash
# Alle Attachments wiederherstellen
docker exec ${STACK_NAME}_BACKUP python cli.py restore-attachments 2024-02-05_05-15-00

# Nur Attachments einer bestimmten Base
docker exec ${STACK_NAME}_BACKUP python cli.py restore-attachments 2024-02-05_05-15-00 --base "Meine_Base"

# Nur Attachments einer bestimmten Tabelle
docker exec ${STACK_NAME}_BACKUP python cli.py restore-attachments 2024-02-05_05-15-00 \
    --base "Meine_Base" --table "Kunden"
```

**Hinweis:** Dieser Befehl ist fuer die Verwendung nach `restore-dump` gedacht.
Die Records existieren bereits in der Datenbank mit ihren Original-IDs.
Attachments werden via NocoDB Storage API hochgeladen und mit den bestehenden Records verknuepft.

## Wiederherstellung

### Szenario 1: Vollstaendige Wiederherstellung (Disaster Recovery)

Bei komplettem Datenverlust (Datenbank + Anwendung):

```bash
# 1. Frischen Stack deployen (nur DB + Init)
docker compose -f docker-compose.traefik.yml up -d database-server
docker compose -f docker-compose.traefik.yml up -d nocodb-init

# 2. Backup-Container starten (NocoDB NICHT starten!)
docker compose -f docker-compose.traefik.yml --profile backup up -d nocodb-backup

# 3. Backup herunterladen (falls nur auf S3)
docker exec ${STACK_NAME}_BACKUP python cli.py download 2024-02-05_05-15-00

# 4. Datenbank wiederherstellen
docker exec ${STACK_NAME}_BACKUP python cli.py restore-dump 2024-02-05_05-15-00

# 5. Daten-Dateien wiederherstellen (Uploads/Attachments)
docker exec ${STACK_NAME}_BACKUP python cli.py restore-files 2024-02-05_05-15-00

# 6. NocoDB starten
docker compose -f docker-compose.traefik.yml up -d nocodb-server

# 7. Logs pruefen
docker compose logs -f nocodb-server
```

**Hinweis zu Attachments bei Disaster Recovery:**

- **Attachments lokal (Standard):** `restore-files` stellt alle Dateien 1:1 an den
  Original-Pfaden wieder her. Die Referenzen in der Datenbank stimmen sofort.
- **Attachments auf S3 (NC_S3_BUCKET_NAME):** Keine Aktion noetig - Dateien liegen
  weiterhin auf S3. `NOCODB_BACKUP_INCLUDE_FILES=false` setzen.
- **Kein File-Backup vorhanden:** Als Fallback kann `restore-attachments` Dateien
  via NocoDB API neu hochladen (erfordert laufenden NocoDB-Server).

### Szenario 2: Tabellen auf neuem System anlegen (Migration/Klon)

Wenn NocoDB auf einem neuen System aufgesetzt wird und die Tabellenstruktur
aus einem Backup uebernommen werden soll (ohne den kompletten DB-Dump):

```bash
# 1. Frischen Stack deployen
docker compose -f docker-compose.traefik.yml up -d

# 2. NocoDB oeffnen und Admin-Account erstellen
# Browser: https://${SERVICE_HOSTNAME}

# 3. API Token erstellen (Account Settings > Tokens)
# Token in .env eintragen: NOCODB_API_TOKEN=...

# 4. Backup-Container starten
docker compose -f docker-compose.traefik.yml --profile backup up -d nocodb-backup

# 5. Backup herunterladen (falls nur auf S3)
docker exec ${STACK_NAME}_BACKUP python cli.py download 2024-02-05_05-15-00

# 6. Tabellen-Schema wiederherstellen (erstellt Bases + Tabellen)
docker exec ${STACK_NAME}_BACKUP python cli.py restore-schema 2024-02-05_05-15-00

# 7. Records importieren (optional)
docker exec ${STACK_NAME}_BACKUP python cli.py restore-records 2024-02-05_05-15-00 --with-attachments

# 8. Virtuelle Spalten manuell nachbauen (Links, Lookups, Rollups, Formulas)
```

**Wichtig:**

- Das Schema enthaelt alle physischen Spalten mit Typen, Optionen und Einstellungen
- Virtuelle Spalten (Verknuepfungen, Lookups, Rollups, Formulas) muessen manuell
  in der NocoDB-Oberflaeche nachgebaut werden
- Ideal fuer: Staging-Umgebung, System-Migration, Tabellenstruktur klonen

### Szenario 3: Einzelne Base oder Tabelle wiederherstellen

Wenn nur bestimmte Daten verloren gegangen sind (z.B. versehentlich geloeschte Records):

```bash
# 1. Backup inspizieren um Inhalt zu pruefen
docker exec ${STACK_NAME}_BACKUP python cli.py inspect 2024-02-05_05-15-00

# 2. Backup ggf. von S3 herunterladen
docker exec ${STACK_NAME}_BACKUP python cli.py download 2024-02-05_05-15-00

# 3a. Bestimmte Tabelle MIT Attachments wiederherstellen
docker exec ${STACK_NAME}_BACKUP python cli.py restore-records 2024-02-05_05-15-00 \
    --base "Meine_Base" --table "Kunden" --with-attachments

# 3b. Oder gesamte Base ohne Attachments (schneller)
docker exec ${STACK_NAME}_BACKUP python cli.py restore-records 2024-02-05_05-15-00 \
    --base "Meine_Base"
```

**Wichtig:**

- Die Ziel-Tabelle muss in NocoDB bereits existieren (gleiches Schema)
- Records werden als neue Eintraege eingefuegt (keine Deduplizierung)
- Systemfelder (Id, CreatedAt, UpdatedAt) werden beim Import ignoriert
- Bei grossen Tabellen erfolgt der Import in 100er-Batches
- `--with-attachments` laedt Dateien via NocoDB Storage API hoch und verknuepft sie

### Szenario 4: Manuelle SQL-Wiederherstellung

Fuer fortgeschrittene Benutzer, die direkt mit PostgreSQL arbeiten:

```bash
# Dump entpacken
gunzip -k /path/to/backup/database.sql.gz

# In Datenbank einspielen
cat /path/to/backup/database.sql | docker exec -i ${STACK_NAME}_DATABASE psql -U nocodb -d nocodb

# Danach Attachments wiederherstellen (falls im Backup enthalten)
docker exec ${STACK_NAME}_BACKUP python cli.py restore-attachments 2024-02-05_05-15-00
```

## Development mit MinIO

Fuer lokale Entwicklung und Tests steht MinIO als S3-kompatibler Storage bereit.

### MinIO starten

```bash
# Development-Stack mit MinIO
docker compose -f docker-compose.development.yml --profile minio up -d

# Oder vollstaendig mit Backup-Sidecar
docker compose -f docker-compose.development.yml --profile backup up -d
```

### MinIO Zugang

- **Console:** http://localhost:9001
- **API:** http://localhost:9000
- **User:** minioadmin (oder `MINIO_ROOT_USER`)
- **Password:** minioadmin (oder `MINIO_ROOT_PASSWORD`)

### MinIO-Init Container

Der `minio-init` Container erstellt automatisch:

1. **Bucket:** `nocodb-backups` (konfigurierbar)
2. **Service User:** Dedizierter Benutzer fuer nocodb-backup
3. **IAM Policy:** Eingeschraenkte Rechte nur fuer den Backup-Bucket

## Init Container

Der `nocodb-init` Container fuehrt vor dem Start von NocoDB Wartungsaufgaben aus:

### Collation Check

Prueft auf PostgreSQL Collation-Mismatches nach OS/libc-Updates:

```bash
# Nur pruefen (Standard)
INIT_COLLATION_CHECK=true
INIT_COLLATION_AUTO_FIX=false

# Automatisch reparieren
INIT_COLLATION_CHECK=true
INIT_COLLATION_AUTO_FIX=true
```

**Hinweis:** Auto-Fix fuehrt `REINDEX DATABASE CONCURRENTLY` aus (PostgreSQL 12+).

### Task-Konfiguration

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `INIT_COLLATION_CHECK` | `true` | Collation-Mismatch pruefen |
| `INIT_COLLATION_AUTO_FIX` | `false` | Automatisch reparieren |

## Monitoring

### Backup-Status pruefen

```bash
# Container-Status
docker ps -f name=BACKUP

# Letzte Logs
docker logs ${STACK_NAME}_BACKUP --tail 100

# Laufenden Job beobachten
docker logs -f ${STACK_NAME}_BACKUP
```

### Healthcheck

```bash
# Backup-Container Health
docker inspect ${STACK_NAME}_BACKUP --format='{{.State.Health.Status}}'
```

## Troubleshooting

### Backup startet nicht

```bash
# Logs pruefen
docker logs ${STACK_NAME}_BACKUP

# Haeufige Ursachen:
# - DATABASE_PASSWORD nicht gesetzt
# - Datenbank nicht erreichbar
# - NOCODB_API_TOKEN fehlt oder ungueltig
```

### S3-Upload schlaegt fehl

```bash
# S3-Verbindung testen
docker exec ${STACK_NAME}_BACKUP python -c "
from storage.s3_client import S3Storage
from config import Settings
s3 = S3Storage(Settings())
print(s3.list_backups())
"

# Haeufige Ursachen:
# - Credentials falsch
# - Bucket existiert nicht
# - Netzwerk/Firewall-Problem
```

### API-Export fehlerhaft

```bash
# Token pruefen
curl -H "xc-token: ${NOCODB_API_TOKEN}" http://localhost:8080/api/v2/meta/bases

# Haeufige Ursachen:
# - Token abgelaufen oder ungueltig
# - Falsche NOCODB_API_URL
# - NocoDB nicht erreichbar
```

## Referenzen

- [NocoDB API Dokumentation](https://meta-apis-v2.nocodb.com/)
- [PostgreSQL pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html)
- [MinIO Dokumentation](https://min.io/docs/minio/linux/index.html)
- [AWS S3 CLI](https://docs.aws.amazon.com/cli/latest/reference/s3/)
