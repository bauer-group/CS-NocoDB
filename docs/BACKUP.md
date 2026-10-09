<!-- markdownlint-disable MD024 MD033 MD060 -->

# NocoDB Backup & Recovery

> **Language / Sprache:** [Deutsch](#deutsch) | [English](#english)
>
> **Engine:** The backup sidecar runs on the central **BackupHelper** engine
> (`ghcr.io/bauer-group/cs-backuphelper`) plus the NocoDB extension plugin. The
> CLI is `backuphelper`; NocoDB-specific restores live under `backuphelper nocodb
> restore-schema|restore-records|restore-attachments`, the DB dump and data-file
> restores under `backuphelper restore <id> --only database|nocodb-data`.

---

<a id="deutsch"></a>

## Deutsch

Automatisierte Backup-Loesung für NocoDB mit PostgreSQL-Dumps, API-Exports und S3-Integration.

### Uebersicht

```text
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
│  │   │  pg_dump    │────►│  database.dump      │                       │   │
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

### Backup-Methoden

#### 1. PostgreSQL Database Dump (pg_dump)

Vollstaendiger Datenbank-Dump für Disaster Recovery:

- **Format:** PostgreSQL Custom-Format (`database.dump`, komprimiert)
- **Inhalt:** Komplette Datenbankstruktur und Daten
- **Wiederherstellung:** Mit dem CLI-Tool (`pg_restore --clean --if-exists`), auch in eine laufende Datenbank
- **Empfehlung:** Primaeres Backup für vollstaendige Wiederherstellung

#### 2. NocoDB Data Files (tar.gz)

1:1 Archiv des NocoDB-Datenverzeichnisses:

- **Format:** Komprimiertes Tar-Archiv (`nocodb-data.tar.gz`)
- **Inhalt:** Alle Dateien aus dem NocoDB-Datenverzeichnis (Uploads, Attachments)
- **Wiederherstellung:** Direktes Entpacken in das NocoDB-Datenverzeichnis
- **Empfehlung:** Für Disaster Recovery zusammen mit `restore-dump`

Aktivierung: `NOCODB_BACKUP_INCLUDE_FILES=true` (Standard).
Deaktivieren wenn Attachments auf S3 liegen (`NC_S3_BUCKET_NAME`).

#### 3. NocoDB API Export

Strukturierter Export ueber die NocoDB REST API:

- **Bases:** Metadaten aller Bases
- **Tables:** Schema und Struktur
- **Records:** Daten als JSON
- **Attachments:** Download ueber NocoDB API (unabhaengig ob lokal oder S3 gespeichert)

**Struktur:**

```text
/data/
├── 2024-02-05_05-15-00.tar.gz          # Snapshot (sha256 im Manifest)
│   ├── manifest.json
│   ├── database.dump                   # PostgreSQL Dump (Custom-Format)
│   ├── nocodb-data.tar.gz              # NocoDB Daten-Dateien (1:1 Archiv)
│   └── nocodb.tar.gz                   # REST-API-Export
│       ├── manifest.json
│       └── bases/{base_name}/
│           ├── metadata.json           # Base Metadaten
│           └── tables/{table_name}/
│               ├── schema.json         # Table Schema
│               ├── records.json.gz     # Alle Records (gzip-komprimiert)
│               ├── attachments.json    # Welche Datei zu welchem Attachment gehoert
│               └── attachments/{field}/{filename}
└── 2024-02-05_05-15-00.manifest.json   # Manifest: Komponenten, Groessen, sha256
```

Die Dateien heissen wie der Titel des Attachments. Gleiche Titel in einem Feld (zwei
Records mit je einer `invoice.pdf`) bekommen eigene Dateien (`invoice.pdf`,
`invoice (2).pdf`), und `attachments.json` haelt je Feld fest, welche gespeicherte Datei
(`path` bzw. `url` in NocoDB) in welcher Datei liegt. Eine Datei, auf die mehrere Zellen
verweisen, wird einmal gesichert. In aelteren Exporten ohne `attachments.json`
ueberschrieben sich gleichnamige Attachments eines Feldes: Dort ist nur das zuletzt
gesicherte erhalten, und `restore-attachments` verknuepft es mit allen Attachments
dieses Titels.

Snapshots von vor dem Wechsel auf das Custom-Format enthalten stattdessen
`database.sql.gz` (Plain-SQL) - siehe [Datenbank wiederherstellen](#datenbank-wiederherstellen).

### Quick Start

#### 1. Backup aktivieren

```bash
# Production mit Backup-Sidecar
docker compose -f docker-compose.traefik.yml --profile backup up -d

# Oder für Development mit MinIO
docker compose -f docker-compose.development.yml --profile backup up -d
```

#### 2. API Token erstellen

Für API-basierte Backups wird ein NocoDB API Token benoetigt:

1. NocoDB oeffnen
2. **Account Settings** > **Tokens**
3. **Add new token** > Token-Namen eingeben
4. Token kopieren und in `.env` eintragen:

```bash
NOCODB_API_TOKEN=nc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

#### 3. Konfiguration anpassen

```bash
# .env
NOCODB_BACKUP_SCHEDULE_HOUR=5
NOCODB_BACKUP_SCHEDULE_MINUTE=15
NOCODB_BACKUP_RETENTION_COUNT=30
```

### Konfiguration

#### Basis-Einstellungen

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `NOCODB_BACKUP_SCHEDULE_ENABLED` | `true` | Backup-Scheduler aktivieren |
| `NOCODB_BACKUP_SCHEDULE_MODE` | `cron` | `cron` oder `interval` |
| `NOCODB_BACKUP_RETENTION_COUNT` | `30` | Anzahl aufzubewahrender Backups |

#### Schedule-Modi

**Cron-Mode** (taegliches Backup zu fester Uhrzeit):

```bash
NOCODB_BACKUP_SCHEDULE_MODE=cron
NOCODB_BACKUP_SCHEDULE_HOUR=5
NOCODB_BACKUP_SCHEDULE_MINUTE=15
NOCODB_BACKUP_SCHEDULE_DAY_OF_WEEK=*  # * = taeglich, 0-6 = bestimmte Tage
```

**Interval-Mode** (alle N Stunden):

```bash
NOCODB_BACKUP_SCHEDULE_MODE=interval
NOCODB_BACKUP_SCHEDULE_INTERVAL_HOURS=24
```

**Seltener als taeglich:** Der [Healthcheck](#healthcheck) des Backup-Containers erwartet
mindestens alle 26 Stunden einen Lauf (`BACKUP_HEALTHCHECK_MAX_AGE_HOURS`, Default des
Images; die Compose-Dateien reichen ihn nicht durch). Liegen die Laeufe weiter auseinander
(einzelne Wochentage, ein Intervall ueber 26 Stunden), ist der Container 26 Stunden nach
jedem Lauf bis zum naechsten `unhealthy`.

#### Backup-Komponenten

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `NOCODB_BACKUP_DATABASE_DUMP` | `true` | PostgreSQL pg_dump ausfuehren |
| `NOCODB_BACKUP_DATABASE_DUMP_TIMEOUT` | `1800` | Timeout in Sekunden (30 min) |
| `NOCODB_BACKUP_INCLUDE_FILES` | `true` | NocoDB Daten-Dateien als tar.gz sichern |
| `NOCODB_BACKUP_API_EXPORT` | `true` | NocoDB API Export ausfuehren |
| `NOCODB_BACKUP_INCLUDE_RECORDS` | `true` | Tabellen-Records exportieren |
| `NOCODB_BACKUP_INCLUDE_ATTACHMENTS` | `true` | Attachments herunterladen (API Export) |

#### S3 Storage

```bash
# S3-kompatibles Storage (AWS S3, MinIO, Wasabi, etc.)
NOCODB_BACKUP_S3_ENDPOINT_URL=https://s3.eu-central-1.amazonaws.com
NOCODB_BACKUP_S3_BUCKET=nocodb-backups
NOCODB_BACKUP_S3_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE
NOCODB_BACKUP_S3_SECRET_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
NOCODB_BACKUP_S3_REGION=eu-central-1
NOCODB_BACKUP_S3_PREFIX=nocodb-backup

# Lokale Kopie nach erfolgreichem S3-Upload behalten. false = loeschen, sobald S3
# den Snapshot gespeichert hat; ohne S3-Kopie bleibt sie, und der Lauf endet in warning.
NOCODB_BACKUP_KEEP_LOCAL_ARCHIVE=true
```

#### Alerting

```bash
# Alerting aktivieren
NOCODB_BACKUP_ALERT_ENABLED=true
NOCODB_BACKUP_ALERT_LEVEL=warnings  # errors, warnings, all
NOCODB_BACKUP_ALERT_CHANNELS=email,teams  # Komma-getrennt

# Email (nutzt SMTP_HOST, SMTP_USER, SMTP_PASSWORD und SMTP_FROM)
NOCODB_BACKUP_ALERT_EMAIL=admin@example.com
# Versand per STARTTLS auf einem Submission-Port. Die Engine spricht kein
# implizites TLS (Port 465) - SMTP_PORT/SMTP_TLS gelten nur fuer NocoDB.
NOCODB_BACKUP_SMTP_PORT=587
NOCODB_BACKUP_SMTP_STARTTLS=true    # false nur fuer ein Relay ohne TLS (Port 25)

# Microsoft Teams
NOCODB_BACKUP_TEAMS_WEBHOOK=https://outlook.office.com/webhook/...

# Generischer Webhook
NOCODB_BACKUP_WEBHOOK_URL=https://your-webhook.example.com
```

Jeder Lauf endet in einem von drei Status. Der Status bestimmt Exit-Code, Alert und
[Healthcheck](#healthcheck):

| Status | Wann | `--now` | Alert bei Level |
|--------|------|---------|-----------------|
| `success` | Alle Komponenten gesichert, Snapshot gespeichert | Exit 0 | `all` |
| `warning` | Alle Komponenten gesichert, aber etwas Nicht-Fatales schlug fehl, z. B. der S3-Upload bei vorhandener lokaler Kopie oder einzelne Tabellen, Seiten oder Attachments im REST-Export | Exit 0 | `warnings` (Default), `all` |
| `error` | Eine Komponente schlug komplett fehl (z. B. `pg_dump` oder ein von NocoDB abgelehntes `NOCODB_API_TOKEN`), der Snapshot landete auf keinem Ziel, oder der Lauf brach ab | Exit 1 | `errors`, `warnings`, `all` |

Bis BackupHelper 1.7.6 endete ein Lauf mit fehlgeschlagener Komponente nur in `warning`
(Exit 0), solange eine andere Komponente gelang. Abgeschaltete Komponenten (`NOCODB_BACKUP_DATABASE_DUMP`,
`NOCODB_BACKUP_INCLUDE_FILES` oder `NOCODB_BACKUP_API_EXPORT` auf `false`) und ein leeres
`NOCODB_API_TOKEN` erzeugen keine Komponente und beeinflussen den Status nicht.

### CLI-Befehle

Der Backup-Container bietet ein CLI für manuelle Operationen:

#### Sofort-Backup ausfuehren

```bash
# Vollstaendiges Backup (DB + API)
docker exec ${STACK_NAME}_BACKUP backuphelper --now

# Nur Datenbank-Dump
docker exec ${STACK_NAME}_BACKUP backuphelper --now  # scope via NOCODB_BACKUP_API_EXPORT/INCLUDE_FILES=false
```

#### Backups auflisten

```bash
docker exec ${STACK_NAME}_BACKUP backuphelper list
```

**Ausgabe:**

```text
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━┳━━━━━━━━━━━┓
┃ #  ┃ Backup ID           ┃ Local ┃ S3  ┃ Size      ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━╇━━━━━━━━━━━┩
│ 1  │ 2024-02-05_05-15-00 │ +     │ +   │ 125.3 MB  │
│ 2  │ 2024-02-04_05-15-00 │ +     │ +   │ 124.8 MB  │
│ 3  │ 2024-02-03_05-15-00 │ -     │ +   │ 123.5 MB  │
└────┴─────────────────────┴───────┴─────┴───────────┘
```

#### Backup-Details anzeigen

```bash
docker exec ${STACK_NAME}_BACKUP backuphelper show 2024-02-05_05-15-00
```

#### Backups aufraeumen (Retention / prune)

Die Engine wendet die Retention (`NOCODB_BACKUP_RETENTION_COUNT`) nach jedem Lauf
automatisch an, lokal **und** im S3-Ziel. Manuell:

```bash
# Retention sofort anwenden (behaelt N neueste)
docker exec ${STACK_NAME}_BACKUP backuphelper prune --keep 10

# Nur anzeigen, was entfernt wuerde
docker exec ${STACK_NAME}_BACKUP backuphelper prune --keep 10 --dry-run
```

Einen einzelnen Snapshot gezielt entfernen (kein delete-by-id in der Engine):
`<id>.tar.gz` + `<id>.manifest.json` aus dem `/data`-Volume bzw. dem S3-Prefix
loeschen.

#### Backup von S3 herunterladen

```bash
docker exec ${STACK_NAME}_BACKUP backuphelper download 2024-02-05_05-15-00 /data/export  # exports archive+manifest; restore/verify auto-hydrate from S3
```

#### Backup inspizieren

```bash
docker exec ${STACK_NAME}_BACKUP backuphelper show 2024-02-05_05-15-00
```

`show` gibt das Manifest als JSON aus: je Komponente (`database`, `nocodb-data`,
`nocodb`) Name, Art, Groesse, sha256 und einen eventuellen Fehler. `verify <id>`
prueft die Pruefsumme des Archivs (`OK <id>`).

Ab BackupHelper 1.7.7 enthaelt das Manifest zusaetzlich `status` (`success`, `warning`
oder `error`) fuer den Inhalt des Snapshots. Ein Snapshot mit fehlgeschlagener Komponente
wird trotzdem gespeichert: Die Komponente steht mit Groesse 0 und ihrem Fehler im
Manifest, die uebrigen lassen sich mit `restore <id> --only <name>` wiederherstellen.

#### Datenbank wiederherstellen

```bash
docker compose stop nocodb-server
docker exec ${STACK_NAME}_BACKUP backuphelper restore 2024-02-05_05-15-00 --only database
docker compose start nocodb-server
```

**WARNUNG:** Dies ueberschreibt die gesamte Datenbank!

Der Dump liegt im Custom-Format vor (`database.dump`); die Engine spielt ihn mit
`pg_restore --clean --if-exists --single-transaction` ein, ersetzt also alle
Objekte aus dem Backup auch in einer laufenden Datenbank. NocoDB vorher stoppen,
damit keine offenen Verbindungen den Restore blockieren.

**Aeltere Snapshots** (vor dem Wechsel auf das Custom-Format) enthalten
`database.sql.gz`. Den spielt die Engine mit `psql` ein, und das gelingt nur in
eine **leere** Datenbank - in einer bestehenden bricht er beim ersten bereits
vorhandenen Objekt ab. Vorher die Datenbank neu anlegen:

```bash
docker compose stop nocodb-server
docker exec ${STACK_NAME}_DATABASE psql -U nocodb -d postgres \
    -c 'DROP DATABASE nocodb WITH (FORCE)' -c 'CREATE DATABASE nocodb OWNER nocodb'
docker exec ${STACK_NAME}_BACKUP backuphelper restore 2024-02-05_05-15-00 --only database
```

#### Daten-Dateien wiederherstellen (nach restore-dump)

```bash
docker exec ${STACK_NAME}_BACKUP backuphelper restore 2024-02-05_05-15-00 --only nocodb-data
```

Stellt die NocoDB-Dateien (Uploads, Attachments) aus dem `nocodb-data.tar.gz` Archiv
direkt in das NocoDB-Datenverzeichnis wieder her. Die Dateien landen 1:1 an ihren
Original-Pfaden, passend zu den Referenzen in der wiederhergestellten Datenbank.

**Wichtig:**

- NocoDB muss waehrend der Wiederherstellung gestoppt sein
- Verwenden nach `restore-dump` für eine vollstaendige Disaster Recovery
- Nur relevant für lokale Attachments (nicht bei S3-Storage)
- Der Backup-Sidecar laeuft als root (`user: "0:0"` in den Compose-Dateien, mit
  auf `DAC_OVERRIDE` und `FOWNER` reduzierten Capabilities). nocodb-server laeuft
  als root und legt seine Dateien root-eigen an; mit der uid 1000 der Engine
  liesse sich das Volume zwar sichern, ein Restore scheiterte aber mit
  `Permission denied`

#### Tabellen-Schema wiederherstellen (neues System)

```bash
# Alle Bases und Tabellen aus Backup erstellen
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-schema 2024-02-05_05-15-00

# Nur eine bestimmte Base wiederherstellen
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-schema 2024-02-05_05-15-00 --base "Meine_Base"

# Nur eine bestimmte Tabelle wiederherstellen
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-schema 2024-02-05_05-15-00 --base "Meine_Base" --table "Kunden"

# Bereits existierende Tabellen ueberspringen
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-schema 2024-02-05_05-15-00 --skip-existing
```

**Hinweise:**

- Erstellt Bases automatisch, falls sie noch nicht existieren
- Systemspalten (Id, CreatedAt, UpdatedAt) werden von NocoDB automatisch angelegt
- Virtuelle Spalten (Links, Lookup, Rollup, Formula) werden uebersprungen und
  muessen manuell in der NocoDB-Oberflaeche nachgebaut werden
- Das Schema stammt aus den `schema.json` Dateien im API-Export (vollstaendige Spaltendefinitionen)
- Nach `restore-schema` koennen Records mit `restore-records` importiert werden

#### Records wiederherstellen (einzelne Tabellen/Bases)

```bash
# Alle Tabellen aller Bases wiederherstellen
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-records 2024-02-05_05-15-00

# Nur eine bestimmte Base wiederherstellen
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-records 2024-02-05_05-15-00 --base "Meine_Base"

# Nur eine bestimmte Tabelle wiederherstellen
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-records 2024-02-05_05-15-00 --base "Meine_Base" --table "Kunden"

# Records MIT Attachments wiederherstellen
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-records 2024-02-05_05-15-00 \
    --base "Meine_Base" --with-attachments

# Ohne Bestaetigung
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-records 2024-02-05_05-15-00 --base "Meine_Base" --force
```

**Hinweis:** Tabellen muessen in NocoDB bereits mit kompatiblem Schema existieren.
Records werden via API eingefuegt - bestehende Daten bleiben erhalten (keine Deduplizierung).

#### Attachments wiederherstellen (nach restore-dump)

```bash
# Alle Attachments wiederherstellen
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-attachments 2024-02-05_05-15-00

# Nur Attachments einer bestimmten Base
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-attachments 2024-02-05_05-15-00 --base "Meine_Base"

# Nur Attachments einer bestimmten Tabelle
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-attachments 2024-02-05_05-15-00 \
    --base "Meine_Base" --table "Kunden"
```

**Hinweis:** Dieser Befehl ist für die Verwendung nach `restore-dump` gedacht.
Die Records existieren bereits in der Datenbank mit ihren Original-IDs.
Attachments werden via NocoDB Storage API hochgeladen und mit den bestehenden Records verknuepft.
Jedes Attachment bekommt die Datei, die der Export fuer genau dieses Attachment gesichert
hat (`attachments.json`), mit seinem urspruenglichen Titel - auch wenn sich Titel wiederholen.
Das gilt ebenso fuer `restore-records --with-attachments`.

### Wiederherstellung

#### Szenario 1: Vollstaendige Wiederherstellung (Disaster Recovery)

Bei komplettem Datenverlust (Datenbank + Anwendung):

```bash
# 1. Frischen Stack deployen (nur DB + Init)
docker compose -f docker-compose.traefik.yml up -d database-server
docker compose -f docker-compose.traefik.yml up -d nocodb-init

# 2. Backup-Container starten (NocoDB NICHT starten - ohne --no-deps wuerde
#    depends_on den nocodb-server mitstarten)
docker compose -f docker-compose.traefik.yml --profile backup up -d --no-deps nocodb-backup

# 3. Backup herunterladen (falls nur auf S3)
docker exec ${STACK_NAME}_BACKUP backuphelper download 2024-02-05_05-15-00 /data/export  # exports archive+manifest; restore/verify auto-hydrate from S3

# 4. Datenbank wiederherstellen
docker exec ${STACK_NAME}_BACKUP backuphelper restore 2024-02-05_05-15-00 --only database

# 5. Daten-Dateien wiederherstellen (Uploads/Attachments)
docker exec ${STACK_NAME}_BACKUP backuphelper restore 2024-02-05_05-15-00 --only nocodb-data

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

#### Szenario 2: Tabellen auf neuem System anlegen (Migration/Klon)

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
docker exec ${STACK_NAME}_BACKUP backuphelper download 2024-02-05_05-15-00 /data/export  # exports archive+manifest; restore/verify auto-hydrate from S3

# 6. Tabellen-Schema wiederherstellen (erstellt Bases + Tabellen)
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-schema 2024-02-05_05-15-00

# 7. Records importieren (optional)
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-records 2024-02-05_05-15-00 --with-attachments

# 8. Virtuelle Spalten manuell nachbauen (Links, Lookups, Rollups, Formulas)
```

**Wichtig:**

- Das Schema enthaelt alle physischen Spalten mit Typen, Optionen und Einstellungen
- Virtuelle Spalten (Verknuepfungen, Lookups, Rollups, Formulas) muessen manuell
  in der NocoDB-Oberflaeche nachgebaut werden
- Ideal für: Staging-Umgebung, System-Migration, Tabellenstruktur klonen

#### Szenario 3: Einzelne Base oder Tabelle wiederherstellen

Wenn nur bestimmte Daten verloren gegangen sind (z.B. versehentlich geloeschte Records):

```bash
# 1. Backup inspizieren um Inhalt zu pruefen
docker exec ${STACK_NAME}_BACKUP backuphelper show 2024-02-05_05-15-00

# 2. Backup ggf. von S3 herunterladen
docker exec ${STACK_NAME}_BACKUP backuphelper download 2024-02-05_05-15-00 /data/export  # exports archive+manifest; restore/verify auto-hydrate from S3

# 3a. Bestimmte Tabelle MIT Attachments wiederherstellen
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-records 2024-02-05_05-15-00 \
    --base "Meine_Base" --table "Kunden" --with-attachments

# 3b. Oder gesamte Base ohne Attachments (schneller)
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-records 2024-02-05_05-15-00 \
    --base "Meine_Base"
```

**Wichtig:**

- Die Ziel-Tabelle muss in NocoDB bereits existieren (gleiches Schema)
- Records werden als neue Eintraege eingefuegt (keine Deduplizierung)
- Systemfelder (Id, CreatedAt, UpdatedAt) werden beim Import ignoriert
- Bei grossen Tabellen erfolgt der Import in 100er-Batches
- `--with-attachments` laedt Dateien via NocoDB Storage API hoch und verknuepft sie

#### Szenario 4: Manuelle SQL-Wiederherstellung

Für fortgeschrittene Benutzer, die direkt mit PostgreSQL arbeiten:

```bash
# Dump aus dem Snapshot-Archiv holen
mkdir -p /tmp/restore
tar -xzf /path/to/2024-02-05_05-15-00.tar.gz -C /tmp/restore database.dump

# In die Datenbank einspielen (NocoDB vorher stoppen)
docker compose stop nocodb-server
docker exec -i ${STACK_NAME}_DATABASE pg_restore --clean --if-exists --no-owner --no-acl \
    --single-transaction -U nocodb -d nocodb < /tmp/restore/database.dump

# Danach Attachments wiederherstellen (falls im Backup enthalten)
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-attachments 2024-02-05_05-15-00
```

### Development mit MinIO

Für lokale Entwicklung und Tests steht MinIO als S3-kompatibler Storage bereit.

#### MinIO starten

```bash
# Development-Stack mit MinIO
docker compose -f docker-compose.development.yml --profile minio up -d

# Oder vollstaendig mit Backup-Sidecar
docker compose -f docker-compose.development.yml --profile backup up -d
```

#### MinIO Zugang

- **Console:** `http://localhost:9001`
- **API:** `http://localhost:9000`
- **User:** minioadmin (oder `MINIO_ROOT_USER`)
- **Password:** minioadmin (oder `MINIO_ROOT_PASSWORD`)

#### MinIO-Init Container

Der `minio-init` Container erstellt automatisch:

1. **Bucket:** `nocodb-backups` (konfigurierbar)
2. **Service User:** Dedizierter Benutzer für nocodb-backup
3. **IAM Policy:** Eingeschraenkte Rechte nur für den Backup-Bucket

### Init Container

Der `nocodb-init` Container fuehrt vor dem Start von NocoDB Wartungsaufgaben aus:

#### Collation Check

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

#### Task-Konfiguration

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `INIT_COLLATION_CHECK` | `true` | Collation-Mismatch pruefen |
| `INIT_COLLATION_AUTO_FIX` | `false` | Automatisch reparieren |

### Monitoring

#### Backup-Status pruefen

```bash
# Container-Status
docker ps -f name=BACKUP

# Letzte Logs
docker logs ${STACK_NAME}_BACKUP --tail 100

# Laufenden Job beobachten
docker logs -f ${STACK_NAME}_BACKUP
```

#### Healthcheck

Der Healthcheck des Backup-Containers (`backuphelper healthcheck` aus der
BackupHelper-Engine) meldet, ob Backups funktionieren, nicht nur, ob der Prozess laeuft.
Ab BackupHelper 1.7.7 ist der Container `unhealthy`, wenn

- `/data` fuer den Container nicht beschreibbar ist,
- der letzte Lauf in `error` endete oder sein Snapshot eine fehlgeschlagene Komponente
  hat - bis ein neuerer Lauf mit `success` oder `warning` endet,
- der letzte Lauf vor mehr als 26 Stunden startete (siehe [Schedule-Modi](#schedule-modi)),
  oder
- noch kein Backup gelaufen ist und der Container vor mehr als 26 Stunden startete.

```bash
# Backup-Container Health
docker inspect ${STACK_NAME}_BACKUP --format='{{.State.Health.Status}}'

# Urteil und Grund
docker exec ${STACK_NAME}_BACKUP backuphelper healthcheck
# unhealthy: the last backup failed: snapshot 2026-07-05_05-15-00 (job main) at 2026-07-05T05:15:00+00:00: failed component(s): nocodb
```

- **Nach dem Upgrade auf 1.7.7** ist ein Deployment, dessen neuester Snapshot schon eine
  fehlgeschlagene Komponente hat, sofort `unhealthy`, bis ein vollstaendiger Snapshot
  existiert. Die Quelle reparieren (z. B. ein abgelaufenes `NOCODB_API_TOKEN`) oder
  abschalten (siehe [Alerting](#alerting)).
- **`NOCODB_BACKUP_KEEP_LOCAL_ARCHIVE=false`** wird ebenfalls ueberwacht: Der Container
  protokolliert jeden Lauf unter `/data/.state/`, ein Job, der nicht mehr laeuft, wird
  also auch ohne lokalen Snapshot nach 26 Stunden `unhealthy`.
- **`NOCODB_BACKUP_ON_STARTUP=true`:** Schlaegt das Backup beim Start fehl, ist der
  Container gleich danach `unhealthy`, und ein noch wartendes `docker compose up --wait`
  schlaegt fehl.

Alle Regeln:
[BackupHelper-Deployment-Doku](https://github.com/bauer-group/CS-BackupHelper/blob/main/docs/deployment.md#the-functional-healthcheck).

### Troubleshooting

#### Backup startet nicht

```bash
# Logs pruefen
docker logs ${STACK_NAME}_BACKUP

# Haeufige Ursachen:
# - DATABASE_PASSWORD nicht gesetzt
# - Datenbank nicht erreichbar
# - NOCODB_API_TOKEN fehlt oder ungueltig
```

#### S3-Upload schlaegt fehl

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

#### API-Export fehlerhaft

```bash
# Token pruefen
curl -H "xc-token: ${NOCODB_API_TOKEN}" http://localhost:8080/api/v2/meta/bases

# Haeufige Ursachen:
# - Token abgelaufen oder ungueltig
# - Falsche NOCODB_API_URL
# - NocoDB nicht erreichbar
```

### Round-Trip-Test in CI

Jedes Release haengt an einem echten Backup und Restore dieses Stacks. Der Job
`🧪 Backup Round Trip` in [docker-release.yml](../.github/workflows/docker-release.yml)
ruft das wiederverwendbare
[`modules-backup-roundtrip-test.yml`](https://github.com/bauer-group/automation-templates/blob/main/docs/workflows/modules-backup-roundtrip-test.md)
auf und laeuft vor dem Release-Job, der seinen Erfolg voraussetzt. Er laeuft auch, wenn
der Base-Image-Monitor nach einem neuen BackupHelper- oder NocoDB-Image ein Release
ausloest - ein Engine-Update geht also erst raus, nachdem es NocoDB-Daten
wiederhergestellt hat.

| Phase | Was passiert |
|-------|--------------|
| Build | `src/nocodb`, `src/nocodb-init` und `src/nocodb-backup` werden aus dem Commit gebaut, mit frischen Base-Images |
| Start | `docker-compose.local.yml` mit dem Profil `backup`, CI-Speichergrenzen fuer PostgreSQL, generiertes `DATABASE_PASSWORD` und `NC_AUTH_JWT_SECRET` |
| Seed | Ueber die NocoDB-API: erster Benutzer, ein API-Token (per `.env` an den Sidecar uebergeben), eine Base mit Tabelle, ein Datensatz mit dem Marker des Laufs und zwei Text-Attachments mit gleichem Namen und verschiedenem Inhalt im Daten-Volume |
| Backup | `create`, danach muss `show` `database`, `nocodb-data` und `nocodb` ohne Fehler und Warnungen listen, `verify` muss `OK` melden |
| Loeschen | Der Datensatz ueber die API, die Attachment-Dateien im Volume |
| Restore | `nocodb-server` wird gestoppt, `restore <id> --force` laeuft, der Stack startet wieder |
| Pruefung | Datensatz ueber die API, beide Dateien mit exaktem Inhalt im Volume, NocoDB liefert beide Attachments aus, der REST-Export im Snapshot enthaelt den Datensatz und fuer jedes Attachment eine eigene Datei mit dessen Inhalt (ueber `attachments.json`, wie bei `restore-attachments`) |

Die Skripte liegen in [`tests/backup-roundtrip/`](../tests/backup-roundtrip/). Die Pruefung
laeuft dreimal - vor dem Backup (Daten vorhanden), nach dem Loeschen (Daten weg) und nach
dem Restore (Daten vorhanden) -, ein Restore, der nichts schreibt, kann also nicht
bestehen. Den REST-Export (`nocodb`) spielt der volle Restore bewusst nicht ein (das
geschieht gezielt mit `backuphelper nocodb restore-*`); geprueft wird, dass der Snapshot
den Datensatz und die Bytes jedes Attachments enthaelt. Die beiden Attachments haben
denselben Titel: Ein Export, der Dateien nur nach dem Titel benennt, behielte eines davon.

Ein Lauf dauert gemessen 2 min 35 s: etwa 1 min fuer den Bau der drei Images, 40 s bis der
Stack laeuft, der Rest fuer Seed, Backup, Restore und Neustart. Er startet bei Pushes auf
`main` (reine Doku-Pushes ausgenommen), bei jedem `workflow_dispatch` und bei Pull
Requests, die `src/`, eine Compose-Datei, `.env.example`, die Round-Trip-Skripte oder den
Release-Workflow aendern. Schlaegt er fehl, nennt die Zusammenfassung des Laufs die
fehlgeschlagene Phase, und das Artefakt `backup-roundtrip-diagnostics` enthaelt die Logs
aller Services, `docker compose ps`, die Snapshot-Liste und das Manifest.

### Referenzen

- [NocoDB API Dokumentation](https://meta-apis-v2.nocodb.com/)
- [PostgreSQL pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html)
- [MinIO Dokumentation](https://min.io/docs/minio/linux/index.html)
- [AWS S3 CLI](https://docs.aws.amazon.com/cli/latest/reference/s3/)
- [Backup-Round-Trip-Modul](https://github.com/bauer-group/automation-templates/blob/main/docs/workflows/modules-backup-roundtrip-test.md)

---

<a id="english"></a>

## English

Automated backup solution for NocoDB with PostgreSQL dumps, API exports, and S3 integration.

### Overview

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ BACKUP ARCHITECTURE                                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  nocodb-backup Container                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                     │   │
│  │   Scheduler (Cron/Interval)                                         │   │
│  │         │                                                           │   │
│  │         ▼                                                           │   │
│  │   ┌─────────────┐     ┌─────────────────────┐                       │   │
│  │   │  pg_dump    │────►│  database.dump      │                       │   │
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

### Backup Methods

#### 1. PostgreSQL Database Dump (pg_dump)

Full database dump for disaster recovery:

- **Format:** PostgreSQL custom format (`database.dump`, compressed)
- **Contents:** Complete database structure and data
- **Restore:** Using the CLI tool (`pg_restore --clean --if-exists`), also into a running database
- **Recommendation:** Primary backup for full recovery

#### 2. NocoDB Data Files (tar.gz)

1:1 archive of the NocoDB data directory:

- **Format:** Compressed tar archive (`nocodb-data.tar.gz`)
- **Contents:** All files from the NocoDB data directory (uploads, attachments)
- **Restore:** Direct extraction to the NocoDB data directory
- **Recommendation:** For disaster recovery together with `restore-dump`

Enable: `NOCODB_BACKUP_INCLUDE_FILES=true` (default).
Disable when attachments are stored on S3 (`NC_S3_BUCKET_NAME`).

#### 3. NocoDB API Export

Structured export via the NocoDB REST API:

- **Bases:** Metadata of all bases
- **Tables:** Schema and structure
- **Records:** Data as JSON
- **Attachments:** Downloaded via NocoDB API (regardless of local or S3 storage)

**Structure:**

```text
/data/
├── 2024-02-05_05-15-00.tar.gz          # Snapshot (sha256 in the manifest)
│   ├── manifest.json
│   ├── database.dump                   # PostgreSQL dump (custom format)
│   ├── nocodb-data.tar.gz              # NocoDB data files (1:1 archive)
│   └── nocodb.tar.gz                   # REST API export
│       ├── manifest.json
│       └── bases/{base_name}/
│           ├── metadata.json           # Base metadata
│           └── tables/{table_name}/
│               ├── schema.json         # Table schema
│               ├── records.json.gz     # All records (gzip compressed)
│               ├── attachments.json    # Which file belongs to which attachment
│               └── attachments/{field}/{filename}
└── 2024-02-05_05-15-00.manifest.json   # Manifest: components, sizes, sha256
```

Files are named after the attachment's title. Equal titles in one field (two records
with an `invoice.pdf` each) get files of their own (`invoice.pdf`, `invoice (2).pdf`),
and `attachments.json` records per field which stored file (`path` or `url` in NocoDB)
went into which file. A file that several cells reference is backed up once. In older
exports without `attachments.json`, attachments of one field with the same title
overwrote each other: only the one saved last is there, and `restore-attachments` links
it to every attachment with that title.

Snapshots taken before the switch to the custom format hold `database.sql.gz`
(plain SQL) instead - see [Restore Database](#restore-database).

### Quick Start

#### 1. Enable Backup

```bash
# Production with backup sidecar
docker compose -f docker-compose.traefik.yml --profile backup up -d

# Or for development with MinIO
docker compose -f docker-compose.development.yml --profile backup up -d
```

#### 2. Create API Token

An API token is required for API-based backups:

1. Open NocoDB
2. **Account Settings** > **Tokens**
3. **Add new token** > Enter token name
4. Copy token and add to `.env`:

```bash
NOCODB_API_TOKEN=nc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

#### 3. Adjust Configuration

```bash
# .env
NOCODB_BACKUP_SCHEDULE_HOUR=5
NOCODB_BACKUP_SCHEDULE_MINUTE=15
NOCODB_BACKUP_RETENTION_COUNT=30
```

### Configuration

#### Basic Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `NOCODB_BACKUP_SCHEDULE_ENABLED` | `true` | Enable backup scheduler |
| `NOCODB_BACKUP_SCHEDULE_MODE` | `cron` | `cron` or `interval` |
| `NOCODB_BACKUP_RETENTION_COUNT` | `30` | Number of backups to retain |

#### Schedule Modes

**Cron mode** (daily backup at fixed time):

```bash
NOCODB_BACKUP_SCHEDULE_MODE=cron
NOCODB_BACKUP_SCHEDULE_HOUR=5
NOCODB_BACKUP_SCHEDULE_MINUTE=15
NOCODB_BACKUP_SCHEDULE_DAY_OF_WEEK=*  # * = daily, 0-6 = specific days
```

**Interval mode** (every N hours):

```bash
NOCODB_BACKUP_SCHEDULE_MODE=interval
NOCODB_BACKUP_SCHEDULE_INTERVAL_HOURS=24
```

**Less often than daily:** the backup container's [health check](#health-check) expects a
run at least every 26 hours (`BACKUP_HEALTHCHECK_MAX_AGE_HOURS`, the image default; the
compose files do not pass it through). With runs further apart (single weekdays, an
interval above 26 hours) the container is `unhealthy` from 26 hours after each run until
the next one.

#### Backup Components

| Variable | Default | Description |
|----------|---------|-------------|
| `NOCODB_BACKUP_DATABASE_DUMP` | `true` | Run PostgreSQL pg_dump |
| `NOCODB_BACKUP_DATABASE_DUMP_TIMEOUT` | `1800` | Timeout in seconds (30 min) |
| `NOCODB_BACKUP_INCLUDE_FILES` | `true` | Archive NocoDB data files as tar.gz |
| `NOCODB_BACKUP_API_EXPORT` | `true` | Run NocoDB API export |
| `NOCODB_BACKUP_INCLUDE_RECORDS` | `true` | Export table records |
| `NOCODB_BACKUP_INCLUDE_ATTACHMENTS` | `true` | Download attachments (API export) |

#### S3 Storage

```bash
# S3-compatible storage (AWS S3, MinIO, Wasabi, etc.)
NOCODB_BACKUP_S3_ENDPOINT_URL=https://s3.eu-central-1.amazonaws.com
NOCODB_BACKUP_S3_BUCKET=nocodb-backups
NOCODB_BACKUP_S3_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE
NOCODB_BACKUP_S3_SECRET_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
NOCODB_BACKUP_S3_REGION=eu-central-1
NOCODB_BACKUP_S3_PREFIX=nocodb-backup

# Keep the local copy after a successful S3 upload. false = delete it once S3
# stored the snapshot; without an S3 copy it stays, and the run ends in warning.
NOCODB_BACKUP_KEEP_LOCAL_ARCHIVE=true
```

#### Alerting

```bash
# Enable alerting
NOCODB_BACKUP_ALERT_ENABLED=true
NOCODB_BACKUP_ALERT_LEVEL=warnings  # errors, warnings, all
NOCODB_BACKUP_ALERT_CHANNELS=email,teams  # comma-separated

# Email (uses SMTP_HOST, SMTP_USER, SMTP_PASSWORD and SMTP_FROM)
NOCODB_BACKUP_ALERT_EMAIL=admin@example.com
# Sent with STARTTLS on a submission port. The engine has no implicit TLS
# (port 465) - SMTP_PORT/SMTP_TLS apply to NocoDB only.
NOCODB_BACKUP_SMTP_PORT=587
NOCODB_BACKUP_SMTP_STARTTLS=true    # false only for a relay without TLS (port 25)

# Microsoft Teams
NOCODB_BACKUP_TEAMS_WEBHOOK=https://outlook.office.com/webhook/...

# Generic webhook
NOCODB_BACKUP_WEBHOOK_URL=https://your-webhook.example.com
```

Every run ends in one of three statuses. The status decides the exit code, the alert and
the [health check](#health-check):

| Status | When | `--now` | Alert at level |
|--------|------|---------|----------------|
| `success` | Every component backed up, snapshot stored | exit 0 | `all` |
| `warning` | Every component backed up, but something non-fatal went wrong, e.g. the S3 upload while the local copy exists, or single tables, pages or attachments of the REST export | exit 0 | `warnings` (default), `all` |
| `error` | A component failed completely (e.g. `pg_dump`, or a `NOCODB_API_TOKEN` that NocoDB rejects), the snapshot reached no destination, or the run aborted | exit 1 | `errors`, `warnings`, `all` |

Up to BackupHelper 1.7.6 a run with a failed component only ended in `warning` (exit 0)
as long as another component succeeded. Switched-off components (`NOCODB_BACKUP_DATABASE_DUMP`, `NOCODB_BACKUP_INCLUDE_FILES` or
`NOCODB_BACKUP_API_EXPORT` set to `false`) and an empty `NOCODB_API_TOKEN` produce no
component and do not affect the status.

### CLI Commands

The backup container provides a CLI for manual operations:

#### Run Immediate Backup

```bash
# Full backup (DB + API)
docker exec ${STACK_NAME}_BACKUP backuphelper --now

# Database dump only
docker exec ${STACK_NAME}_BACKUP backuphelper --now  # scope via NOCODB_BACKUP_API_EXPORT/INCLUDE_FILES=false
```

#### List Backups

```bash
docker exec ${STACK_NAME}_BACKUP backuphelper list
```

**Output:**

```text
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━┳━━━━━━━━━━━┓
┃ #  ┃ Backup ID           ┃ Local ┃ S3  ┃ Size      ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━╇━━━━━━━━━━━┩
│ 1  │ 2024-02-05_05-15-00 │ +     │ +   │ 125.3 MB  │
│ 2  │ 2024-02-04_05-15-00 │ +     │ +   │ 124.8 MB  │
│ 3  │ 2024-02-03_05-15-00 │ -     │ +   │ 123.5 MB  │
└────┴─────────────────────┴───────┴─────┴───────────┘
```

#### Show Backup Details

```bash
docker exec ${STACK_NAME}_BACKUP backuphelper show 2024-02-05_05-15-00
```

#### Prune Backups (retention)

Retention (`NOCODB_BACKUP_RETENTION_COUNT`) is applied automatically after each
run, both locally and in the S3 target. Manually:

```bash
# Apply retention now (keep the N newest)
docker exec ${STACK_NAME}_BACKUP backuphelper prune --keep 10

# Preview only
docker exec ${STACK_NAME}_BACKUP backuphelper prune --keep 10 --dry-run
```

There is no delete-by-id; to remove a single snapshot, delete its `<id>.tar.gz`
and `<id>.manifest.json` from the `/data` volume (and the S3 prefix).

#### Download Backup from S3

```bash
docker exec ${STACK_NAME}_BACKUP backuphelper download 2024-02-05_05-15-00 /data/export  # exports archive+manifest; restore/verify auto-hydrate from S3
```

#### Inspect Backup

```bash
docker exec ${STACK_NAME}_BACKUP backuphelper show 2024-02-05_05-15-00
```

`show` prints the manifest as JSON: per component (`database`, `nocodb-data`,
`nocodb`) its name, kind, size, sha256 and an error, if any. `verify <id>` checks
the archive checksum (`OK <id>`).

Since BackupHelper 1.7.7 the manifest also holds `status` (`success`, `warning` or
`error`) for the snapshot's content. A snapshot with a failed component is still stored:
the component is listed with size 0 and its error, and the other components can be
restored with `restore <id> --only <name>`.

#### Restore Database

```bash
docker compose stop nocodb-server
docker exec ${STACK_NAME}_BACKUP backuphelper restore 2024-02-05_05-15-00 --only database
docker compose start nocodb-server
```

**WARNING:** This overwrites the entire database!

The dump is in the custom format (`database.dump`); the engine restores it with
`pg_restore --clean --if-exists --single-transaction`, so it replaces every object
of the backup, also in a running database. Stop NocoDB first so that no open
connection blocks the restore.

**Older snapshots** (taken before the switch to the custom format) hold
`database.sql.gz`. The engine replays it with `psql`, which only works into an
**empty** database - in an existing one it stops at the first object that
already exists. Recreate the database first:

```bash
docker compose stop nocodb-server
docker exec ${STACK_NAME}_DATABASE psql -U nocodb -d postgres \
    -c 'DROP DATABASE nocodb WITH (FORCE)' -c 'CREATE DATABASE nocodb OWNER nocodb'
docker exec ${STACK_NAME}_BACKUP backuphelper restore 2024-02-05_05-15-00 --only database
```

#### Restore Data Files (after restore-dump)

```bash
docker exec ${STACK_NAME}_BACKUP backuphelper restore 2024-02-05_05-15-00 --only nocodb-data
```

Restores NocoDB files (uploads, attachments) from the `nocodb-data.tar.gz` archive
directly to the NocoDB data directory. Files are placed 1:1 at their original paths,
matching the references in the restored database.

**Important:**

- NocoDB must be stopped during restoration
- Use after `restore-dump` for a complete disaster recovery
- Only relevant for local attachments (not for S3 storage)
- The backup sidecar runs as root (`user: "0:0"` in the compose files, with
  capabilities cut down to `DAC_OVERRIDE` and `FOWNER`). nocodb-server runs as
  root and creates its files root-owned; with the engine's uid 1000 the volume
  could be backed up, but a restore failed with `Permission denied`

#### Restore Table Schema (new system)

```bash
# Create all bases and tables from backup
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-schema 2024-02-05_05-15-00

# Restore only a specific base
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-schema 2024-02-05_05-15-00 --base "My_Base"

# Restore only a specific table
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-schema 2024-02-05_05-15-00 --base "My_Base" --table "Customers"

# Skip already existing tables
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-schema 2024-02-05_05-15-00 --skip-existing
```

**Notes:**

- Creates bases automatically if they don't exist yet
- System columns (Id, CreatedAt, UpdatedAt) are created automatically by NocoDB
- Virtual columns (Links, Lookup, Rollup, Formula) are skipped and
  must be recreated manually in the NocoDB UI
- Schema comes from `schema.json` files in the API export (complete column definitions)
- After `restore-schema`, records can be imported with `restore-records`

#### Restore Records (individual tables/bases)

```bash
# Restore all tables of all bases
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-records 2024-02-05_05-15-00

# Restore only a specific base
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-records 2024-02-05_05-15-00 --base "My_Base"

# Restore only a specific table
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-records 2024-02-05_05-15-00 --base "My_Base" --table "Customers"

# Restore records WITH attachments
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-records 2024-02-05_05-15-00 \
    --base "My_Base" --with-attachments

# Without confirmation
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-records 2024-02-05_05-15-00 --base "My_Base" --force
```

**Note:** Tables must already exist in NocoDB with a compatible schema.
Records are inserted via API - existing data is preserved (no deduplication).

#### Restore Attachments (after restore-dump)

```bash
# Restore all attachments
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-attachments 2024-02-05_05-15-00

# Only attachments of a specific base
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-attachments 2024-02-05_05-15-00 --base "My_Base"

# Only attachments of a specific table
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-attachments 2024-02-05_05-15-00 \
    --base "My_Base" --table "Customers"
```

**Note:** This command is intended for use after `restore-dump`.
Records already exist in the database with their original IDs.
Attachments are uploaded via the NocoDB Storage API and linked to existing records.
Every attachment gets the file the export saved for exactly that attachment
(`attachments.json`), with its original title - also where titles repeat. The same
applies to `restore-records --with-attachments`.

### Recovery Scenarios

#### Scenario 1: Full Recovery (Disaster Recovery)

For complete data loss (database + application):

```bash
# 1. Deploy fresh stack (DB + init only)
docker compose -f docker-compose.traefik.yml up -d database-server
docker compose -f docker-compose.traefik.yml up -d nocodb-init

# 2. Start backup container (do NOT start NocoDB - without --no-deps,
#    depends_on would start nocodb-server as well)
docker compose -f docker-compose.traefik.yml --profile backup up -d --no-deps nocodb-backup

# 3. Download backup (if only on S3)
docker exec ${STACK_NAME}_BACKUP backuphelper download 2024-02-05_05-15-00 /data/export  # exports archive+manifest; restore/verify auto-hydrate from S3

# 4. Restore database
docker exec ${STACK_NAME}_BACKUP backuphelper restore 2024-02-05_05-15-00 --only database

# 5. Restore data files (uploads/attachments)
docker exec ${STACK_NAME}_BACKUP backuphelper restore 2024-02-05_05-15-00 --only nocodb-data

# 6. Start NocoDB
docker compose -f docker-compose.traefik.yml up -d nocodb-server

# 7. Check logs
docker compose logs -f nocodb-server
```

**Note on attachments during disaster recovery:**

- **Attachments local (default):** `restore-files` restores all files 1:1 at their
  original paths. Database references match immediately.
- **Attachments on S3 (NC_S3_BUCKET_NAME):** No action needed - files remain
  on S3. Set `NOCODB_BACKUP_INCLUDE_FILES=false`.
- **No file backup available:** As fallback, `restore-attachments` can re-upload files
  via NocoDB API (requires running NocoDB server).

#### Scenario 2: Create Tables on New System (Migration/Clone)

When NocoDB is set up on a new system and the table structure
should be imported from a backup (without the full DB dump):

```bash
# 1. Deploy fresh stack
docker compose -f docker-compose.traefik.yml up -d

# 2. Open NocoDB and create admin account
# Browser: https://${SERVICE_HOSTNAME}

# 3. Create API token (Account Settings > Tokens)
# Add token to .env: NOCODB_API_TOKEN=...

# 4. Start backup container
docker compose -f docker-compose.traefik.yml --profile backup up -d nocodb-backup

# 5. Download backup (if only on S3)
docker exec ${STACK_NAME}_BACKUP backuphelper download 2024-02-05_05-15-00 /data/export  # exports archive+manifest; restore/verify auto-hydrate from S3

# 6. Restore table schema (creates bases + tables)
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-schema 2024-02-05_05-15-00

# 7. Import records (optional)
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-records 2024-02-05_05-15-00 --with-attachments

# 8. Manually recreate virtual columns (Links, Lookups, Rollups, Formulas)
```

**Important:**

- Schema contains all physical columns with types, options, and settings
- Virtual columns (links, lookups, rollups, formulas) must be recreated
  manually in the NocoDB UI
- Ideal for: staging environments, system migration, cloning table structures

#### Scenario 3: Restore Individual Base or Table

When only specific data has been lost (e.g. accidentally deleted records):

```bash
# 1. Inspect backup to check contents
docker exec ${STACK_NAME}_BACKUP backuphelper show 2024-02-05_05-15-00

# 2. Download backup from S3 if needed
docker exec ${STACK_NAME}_BACKUP backuphelper download 2024-02-05_05-15-00 /data/export  # exports archive+manifest; restore/verify auto-hydrate from S3

# 3a. Restore specific table WITH attachments
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-records 2024-02-05_05-15-00 \
    --base "My_Base" --table "Customers" --with-attachments

# 3b. Or restore entire base without attachments (faster)
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-records 2024-02-05_05-15-00 \
    --base "My_Base"
```

**Important:**

- Target table must already exist in NocoDB (same schema)
- Records are inserted as new entries (no deduplication)
- System fields (Id, CreatedAt, UpdatedAt) are ignored during import
- Large tables are imported in batches of 100
- `--with-attachments` uploads files via NocoDB Storage API and links them

#### Scenario 4: Manual SQL Recovery

For advanced users working directly with PostgreSQL:

```bash
# Take the dump out of the snapshot archive
mkdir -p /tmp/restore
tar -xzf /path/to/2024-02-05_05-15-00.tar.gz -C /tmp/restore database.dump

# Restore into the database (stop NocoDB first)
docker compose stop nocodb-server
docker exec -i ${STACK_NAME}_DATABASE pg_restore --clean --if-exists --no-owner --no-acl \
    --single-transaction -U nocodb -d nocodb < /tmp/restore/database.dump

# Then restore attachments (if included in backup)
docker exec ${STACK_NAME}_BACKUP backuphelper nocodb restore-attachments 2024-02-05_05-15-00
```

### Development with MinIO

MinIO is available as S3-compatible storage for local development and testing.

#### Start MinIO

```bash
# Development stack with MinIO
docker compose -f docker-compose.development.yml --profile minio up -d

# Or complete with backup sidecar
docker compose -f docker-compose.development.yml --profile backup up -d
```

#### MinIO Access

- **Console:** `http://localhost:9001`
- **API:** `http://localhost:9000`
- **User:** minioadmin (or `MINIO_ROOT_USER`)
- **Password:** minioadmin (or `MINIO_ROOT_PASSWORD`)

#### MinIO Init Container

The `minio-init` container automatically creates:

1. **Bucket:** `nocodb-backups` (configurable)
2. **Service user:** Dedicated user for nocodb-backup
3. **IAM policy:** Restricted permissions for the backup bucket only

### Init Container

The `nocodb-init` container runs maintenance tasks before NocoDB starts:

#### Collation Check

Checks for PostgreSQL collation mismatches after OS/libc updates:

```bash
# Check only (default)
INIT_COLLATION_CHECK=true
INIT_COLLATION_AUTO_FIX=false

# Auto-repair
INIT_COLLATION_CHECK=true
INIT_COLLATION_AUTO_FIX=true
```

**Note:** Auto-fix runs `REINDEX DATABASE CONCURRENTLY` (PostgreSQL 12+).

#### Task Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `INIT_COLLATION_CHECK` | `true` | Check collation mismatches |
| `INIT_COLLATION_AUTO_FIX` | `false` | Auto-repair mismatches |

### Monitoring

#### Check Backup Status

```bash
# Container status
docker ps -f name=BACKUP

# Recent logs
docker logs ${STACK_NAME}_BACKUP --tail 100

# Watch running job
docker logs -f ${STACK_NAME}_BACKUP
```

#### Health Check

The backup container's health check (`backuphelper healthcheck`, from the BackupHelper
engine) reports whether backups work, not only whether the process runs. Since
BackupHelper 1.7.7 the container is `unhealthy` when

- `/data` is not writable by the container,
- the most recent run ended in `error` or its snapshot has a failed component - until a
  newer run ends in `success` or `warning`,
- the most recent run started more than 26 hours ago (see [Schedule Modes](#schedule-modes)),
  or
- no backup has run yet and the container started more than 26 hours ago.

```bash
# Backup container health
docker inspect ${STACK_NAME}_BACKUP --format='{{.State.Health.Status}}'

# Verdict and reason
docker exec ${STACK_NAME}_BACKUP backuphelper healthcheck
# unhealthy: the last backup failed: snapshot 2026-07-05_05-15-00 (job main) at 2026-07-05T05:15:00+00:00: failed component(s): nocodb
```

- **After the upgrade to 1.7.7** a deployment whose newest snapshot already has a failed
  component is `unhealthy` right away, until a complete snapshot exists. Repair the source
  (e.g. an expired `NOCODB_API_TOKEN`) or switch it off (see [Alerting](#alerting-1)).
- **`NOCODB_BACKUP_KEEP_LOCAL_ARCHIVE=false`** is monitored as well: the container records
  every run under `/data/.state/`, so a job that stops running turns `unhealthy` after
  26 hours even without a local snapshot.
- **`NOCODB_BACKUP_ON_STARTUP=true`:** if the backup at start fails, the container is
  `unhealthy` right after it, and a `docker compose up --wait` that is still waiting
  fails.

All rules:
[BackupHelper deployment guide](https://github.com/bauer-group/CS-BackupHelper/blob/main/docs/deployment.md#the-functional-healthcheck).

### Troubleshooting

#### Backup Won't Start

```bash
# Check logs
docker logs ${STACK_NAME}_BACKUP

# Common causes:
# - DATABASE_PASSWORD not set
# - Database unreachable
# - NOCODB_API_TOKEN missing or invalid
```

#### S3 Upload Fails

```bash
# Test S3 connection
docker exec ${STACK_NAME}_BACKUP python -c "
from storage.s3_client import S3Storage
from config import Settings
s3 = S3Storage(Settings())
print(s3.list_backups())
"

# Common causes:
# - Wrong credentials
# - Bucket does not exist
# - Network/firewall issue
```

#### API Export Errors

```bash
# Check token
curl -H "xc-token: ${NOCODB_API_TOKEN}" http://localhost:8080/api/v2/meta/bases

# Common causes:
# - Token expired or invalid
# - Wrong NOCODB_API_URL
# - NocoDB unreachable
```

### Round-Trip Test in CI

Every release is gated on a real backup and restore of this stack. The job
`🧪 Backup Round Trip` in [docker-release.yml](../.github/workflows/docker-release.yml)
calls the reusable
[`modules-backup-roundtrip-test.yml`](https://github.com/bauer-group/automation-templates/blob/main/docs/workflows/modules-backup-roundtrip-test.md)
and runs before the release job, which needs it to pass. It also runs when the base
image monitor dispatches a release after a new BackupHelper or NocoDB image, so an
engine update ships only after it restored NocoDB data.

| Phase | What happens |
|-------|--------------|
| Build | `src/nocodb`, `src/nocodb-init` and `src/nocodb-backup` are built from the commit, with fresh base images |
| Start | `docker-compose.local.yml` with the `backup` profile, CI-sized PostgreSQL memory, a generated `DATABASE_PASSWORD` and `NC_AUTH_JWT_SECRET` |
| Seed | Through the NocoDB API: the first user, an API token (handed to the sidecar through the `.env`), a base with a table, a record carrying the run's marker and two text attachments with the same name and different content on the data volume |
| Back up | `create`, then `show` must list `database`, `nocodb-data` and `nocodb` without errors or warnings, `verify` must report `OK` |
| Delete | The record through the API, the attachment files on the volume |
| Restore | `nocodb-server` is stopped, `restore <id> --force` runs, the stack is started again |
| Check | The record through the API, both files with their exact content on the volume, NocoDB serving both attachments, and the snapshot's REST export holding the record and, for each attachment, a file of its own with its content (through `attachments.json`, as `restore-attachments` reads it) |

The scripts live in [`tests/backup-roundtrip/`](../tests/backup-roundtrip/). The check
runs three times - before the backup (data present), after the deletion (data absent)
and after the restore (data present) - so a restore that writes nothing cannot pass. The
full restore leaves the REST export (`nocodb`) alone on purpose (it is restored on demand
with `backuphelper nocodb restore-*`); the check proves that the snapshot holds the record
and the bytes of each attachment. The two attachments share their title: an export that
names files by title alone would keep one of them.

A run took 2 min 35 s as measured: about 1 min to build the three images, 40 s until the
stack is up, the rest for seeding, backup, restore and restart. It starts on pushes to
`main` (documentation-only pushes excluded), on every `workflow_dispatch`, and on pull
requests that touch `src/`, a compose file, `.env.example`, the round-trip scripts or the
release workflow. When it fails, the run's summary names the failed phase, and the
`backup-roundtrip-diagnostics` artifact holds every service's log, `docker compose ps`,
the snapshot list and the manifest.

### References

- [NocoDB API Documentation](https://meta-apis-v2.nocodb.com/)
- [PostgreSQL pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html)
- [MinIO Documentation](https://min.io/docs/minio/linux/index.html)
- [AWS S3 CLI](https://docs.aws.amazon.com/cli/latest/reference/s3/)
- [Backup round-trip module](https://github.com/bauer-group/automation-templates/blob/main/docs/workflows/modules-backup-roundtrip-test.md)
