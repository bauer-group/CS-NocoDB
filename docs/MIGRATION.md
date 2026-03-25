<!-- markdownlint-disable MD024 MD033 MD060 -->

# NocoDB Server-Migration (manuell)

> Manueller Migrations-Workflow mit PostgreSQL-Bordmitteln (`pg_dump` / `psql`).
> Fuer den Umzug von einem Altserver auf einen neuen Server — auch bei
> PostgreSQL-Versionswechsel (z.B. PG 15 → PG 18).
>
> **Voraussetzung:** Nur SSH + Docker-Zugriff auf den Altserver. Kein CS-NocoDB-Stack
> oder `.env` auf dem Altserver noetig.

---

## Uebersicht

```text
SERVER A (alt)                              SERVER B (neu)
┌─────────────────────────┐                 ┌─────────────────────────┐
│  NocoDB + PG 15         │                 │  CS-NocoDB Stack + PG 18│
│  (beliebiges Setup)     │                 │                         │
│                         │                 │  3. Stack deployen      │
│  1. Container finden    │                 │     (nur DB + Init)     │
│  2. pg_dump ausfuehren  │                 │                         │
│     + Volumes sichern   │──── SCP ───────►│  4. psql restore        │
│                         │                 │  5. Volumes restore     │
│                         │                 │  6. NocoDB starten      │
│                         │                 │  7. Verifizierung       │
└─────────────────────────┘                 └─────────────────────────┘
```

### Voraussetzungen

| Anforderung | Beschreibung |
|-------------|--------------|
| Server A | SSH + Docker-Zugriff (nur `docker exec` noetig) |
| Server B | Docker + Docker Compose, CS-NocoDB Repository geklont, `.env` konfiguriert |
| Transfer | SCP/rsync zwischen den Servern (oder USB, NFS, etc.) |
| Wartungsfenster | NocoDB auf Server A muss waehrend des Dumps gestoppt sein |

### PostgreSQL-Versionskompatibilitaet

pg_dump erzeugt reines SQL (`--format plain`). Dieses SQL ist vorwaertskompatibel:

| Quelle (Server A) | Ziel (Server B) | Kompatibel |
|--------------------|-----------------|:----------:|
| PG 14 → | PG 18 | Ja |
| PG 15 → | PG 18 | Ja |
| PG 16 → | PG 18 | Ja |
| PG 18 → | PG 15 | Nein (Downgrade) |

> **Hinweis:** pg_dump wird innerhalb des laufenden PostgreSQL-Containers auf Server A
> ausgefuehrt. Die pg_dump-Version entspricht der installierten PG-Version (z.B. v15).
> Fuer plain-SQL-Format ist das unproblematisch — PG 18 kann das SQL einlesen.

---

## Migrationsschritte

### Schritt 1: PostgreSQL-Container auf Server A identifizieren

```bash
ssh user@server-a

# Laufende PostgreSQL-Container anzeigen
docker ps --filter "ancestor=postgres" --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"

# Falls der Image-Name anders ist (z.B. custom image):
docker ps --format "table {{.Names}}\t{{.Image}}" | grep -i postgres
```

**Ergebnis notieren:**

```bash
# Beispiel-Ausgabe:
# NAMES                        IMAGE            STATUS
# db_crm_example_com_DATABASE  postgres:15      Up 45 days

PG_CONTAINER="db_crm_example_com_DATABASE"   # <- anpassen
```

**Datenbank-Credentials ermitteln:**

```bash
# Umgebungsvariablen des Containers anzeigen
docker exec $PG_CONTAINER env | grep -E "POSTGRES_USER|POSTGRES_DB|POSTGRES_PASSWORD"

# Falls nichts gefunden: Container-Inspect pruefen
docker inspect $PG_CONTAINER --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -i postgres
```

**Ergebnis notieren:**

```bash
DB_USER="nocodb"      # POSTGRES_USER (Standard: nocodb oder postgres)
DB_NAME="nocodb"      # POSTGRES_DB (Standard: nocodb)
DB_PASS="..."         # POSTGRES_PASSWORD
```

> **Tipp:** Falls die Credentials nicht ueber Umgebungsvariablen gesetzt sind,
> in der docker-compose.yml oder .env des Altservers nachschauen.

### Schritt 2: NocoDB stoppen (Altserver)

```bash
# NocoDB-Container stoppen (NICHT den Datenbank-Container!)
# Container-Name ermitteln:
docker ps --format "{{.Names}}" | grep -i nocodb

# NocoDB stoppen
NOCODB_CONTAINER="db_crm_example_com_NOCODB"   # <- anpassen
docker stop $NOCODB_CONTAINER
```

> **Warum?** Verhindert Schreiboperationen waehrend des Dumps.
> Die Datenbank bleibt laufen — pg_dump erstellt einen konsistenten Snapshot.

### Schritt 3: Datenbank-Dump erstellen (Altserver)

```bash
# pg_dump direkt im PostgreSQL-Container ausfuehren
docker exec $PG_CONTAINER pg_dump \
    -U $DB_USER \
    -d $DB_NAME \
    --format=plain \
    --no-owner \
    --no-acl \
    --verbose \
    | gzip > nocodb_dump.sql.gz
```

**Parameter erklaert:**

| Parameter | Zweck |
|-----------|-------|
| `--format=plain` | SQL-Textformat, versionsuebergreifend kompatibel |
| `--no-owner` | Keine `ALTER OWNER`-Befehle — Rollen muessen nicht uebereinstimmen |
| `--no-acl` | Keine `GRANT`/`REVOKE`-Befehle — Berechtigungen werden vom neuen Stack gesetzt |
| `--verbose` | Fortschritt auf stderr ausgeben |
| `\| gzip` | Komprimierung auf dem Host (spart Speicher + Transferzeit) |

**Dump pruefen:**

```bash
# Dateigroesse pruefen (sollte > 0 sein)
ls -lh nocodb_dump.sql.gz

# Inhalt stichprobenartig pruefen (erste 20 Zeilen)
gunzip -c nocodb_dump.sql.gz | head -20
# Erwartung: SQL-Header mit "-- PostgreSQL database dump" und Version
```

### Schritt 4: NocoDB-Datenverzeichnis sichern (Altserver)

Das NocoDB-Datenverzeichnis enthaelt Uploads und lokal gespeicherte Attachments.

```bash
# NocoDB-Container Volume ermitteln
docker inspect $NOCODB_CONTAINER --format '{{range .Mounts}}{{if eq .Destination "/usr/app/data"}}{{.Source}}{{end}}{{end}}'

# Oder: alle Mounts anzeigen
docker inspect $NOCODB_CONTAINER --format '{{json .Mounts}}' | python3 -m json.tool
```

**Datenverzeichnis archivieren:**

```bash
# Pfad zum Volume (Beispiel — an tatsaechlichen Pfad anpassen!)
NOCODB_DATA="/var/lib/docker/volumes/db_crm_example_com_nocodb-data/_data"

# Archiv erstellen
sudo tar -czf nocodb-data.tar.gz -C "$NOCODB_DATA" .

# Groesse pruefen
ls -lh nocodb-data.tar.gz
```

> **Ueberspringen wenn:**
>
> - Attachments auf S3 gespeichert werden (NocoDB mit `NC_S3_BUCKET_NAME` konfiguriert)
> - Keine Datei-Uploads in NocoDB verwendet werden

### Schritt 5: Dateien auf Server B uebertragen

```bash
# Von Server A nach Server B kopieren
scp nocodb_dump.sql.gz user@server-b:/tmp/migration/
scp nocodb-data.tar.gz user@server-b:/tmp/migration/   # falls vorhanden
```

**Alternativ mit rsync (fuer grosse Dateien, resumable):**

```bash
rsync -avP nocodb_dump.sql.gz user@server-b:/tmp/migration/
rsync -avP nocodb-data.tar.gz user@server-b:/tmp/migration/
```

### Schritt 6: Stack auf Server B deployen (nur Datenbank)

```bash
ssh user@server-b
cd /path/to/CS-NocoDB

# .env konfigurieren (siehe .env.example)
cp .env.example .env
# Bearbeiten: STACK_NAME, DATABASE_PASSWORD, POSTGRES_VERSION=18, etc.

# Nur Datenbank + Init starten (NICHT NocoDB!)
docker compose -f docker-compose.traefik.yml up -d database-server

# Warten bis Datenbank bereit
docker compose -f docker-compose.traefik.yml logs -f database-server
# Meldung abwarten: "database system is ready to accept connections"
# Dann Ctrl+C

# Init-Container ausfuehren (erstellt Datenbank + Rolle)
docker compose -f docker-compose.traefik.yml up nocodb-init
```

### Schritt 7: Datenbank wiederherstellen (Server B)

```bash
# Source STACK_NAME aus .env
source .env

# Dump in die neue PG 18-Datenbank einspielen
gunzip -c /tmp/migration/nocodb_dump.sql.gz | \
    docker exec -i ${STACK_NAME}_DATABASE psql -U nocodb -d nocodb --quiet
```

> **Was passiert hier?**
>
> 1. `gunzip -c` entpackt den Dump in eine Pipe (ohne Datei auf Disk)
> 2. `docker exec -i` leitet stdin in den Container weiter
> 3. `psql` fuehrt das SQL in der neuen PG 18-Datenbank aus
> 4. PostgreSQL 18 interpretiert das von PG 15 erzeugte SQL problemlos

**Moegliche Warnungen (unbedenklich):**

```text
# Tabellen/Sequenzen existieren schon (vom Init-Container) — werden ueberschrieben
ERROR:  relation "..." already exists
# → Normal bei clean install, pg_dump verwendet CREATE OR REPLACE wo moeglich
```

**Erfolg pruefen:**

```bash
# NocoDB-Metatabellen muessen vorhanden sein
docker exec ${STACK_NAME}_DATABASE psql -U nocodb -d nocodb -c \
    "SELECT count(*) AS tables FROM information_schema.tables WHERE table_schema = 'public';"

# Stichprobe: Bases zaehlen
docker exec ${STACK_NAME}_DATABASE psql -U nocodb -d nocodb -c \
    "SELECT count(*) AS bases FROM nc_bases_v2;"
```

### Schritt 8: Daten-Dateien wiederherstellen (Server B)

```bash
# NocoDB-Data-Volume ermitteln
NOCODB_VOLUME=$(docker volume inspect ${STACK_NAME}_nocodb-data --format '{{.Mountpoint}}')

# Oder falls der Volume-Name anders ist:
docker volume ls | grep nocodb

# Archiv in das Volume entpacken
sudo tar -xzf /tmp/migration/nocodb-data.tar.gz -C "$NOCODB_VOLUME"

# Berechtigungen setzen (NocoDB laeuft als uid 1000)
sudo chown -R 1000:1000 "$NOCODB_VOLUME"
```

> **Ueberspringen wenn** Attachments auf S3 liegen oder keine Datei-Uploads existieren.

### Schritt 9: NocoDB starten (Server B)

```bash
# NocoDB-Server starten
docker compose -f docker-compose.traefik.yml up -d nocodb-server

# Logs beobachten
docker compose -f docker-compose.traefik.yml logs -f nocodb-server
# Erwartung: "NocoDB is running at ..."
```

### Schritt 10: Verifizierung

#### 10a. Daten pruefen

- [ ] NocoDB im Browser oeffnen
- [ ] Einloggen mit bestehendem Admin-Account (Credentials aus alter Datenbank)
- [ ] Bases und Tabellen vorhanden
- [ ] Stichprobe: Records in einer Tabelle pruefen
- [ ] Stichprobe: Attachments/Uploads oeffnen
- [ ] Benutzerkonten und Berechtigungen pruefen

#### 10b. Collation-Fix (bei PG-Versionswechsel)

Bei einem Wechsel von PG 15 auf PG 18 aendert sich die Collation-Version.
Dies fuehrt zu Warnungen, die behoben werden muessen:

```bash
# Option A: Init-Container mit Auto-Fix
# In .env setzen: INIT_COLLATION_AUTO_FIX=true
docker compose -f docker-compose.traefik.yml up nocodb-init

# Option B: Manuell
docker exec ${STACK_NAME}_DATABASE psql -U nocodb -d nocodb -c \
    "ALTER DATABASE nocodb REFRESH COLLATION VERSION;"
```

#### 10c. Statistiken aktualisieren

```bash
# ANALYZE fuer optimale Query-Performance nach Import
docker exec ${STACK_NAME}_DATABASE vacuumdb -U nocodb --all --analyze-in-stages
```

### Schritt 11: Backup-Schedule aktivieren (Server B)

```bash
# API-Token in NocoDB erstellen:
# Browser → Account Settings → Tokens → Add new token
# Token in .env eintragen: NOCODB_API_TOKEN=nc_...

# Backup-Container starten
docker compose -f docker-compose.traefik.yml --profile backup up -d nocodb-backup

# Test-Backup ausfuehren
docker exec ${STACK_NAME}_BACKUP python main.py --now
```

---

## DNS-Umschaltung

Wenn der Hostname gleich bleibt (`SERVICE_HOSTNAME`):

1. **TTL vorher reduzieren** (z.B. 300s, einige Stunden vor Migration)
2. DNS-Record auf neue Server-IP aendern
3. Warten bis Propagierung abgeschlossen
4. Alten Server A herunterfahren (erst nach vollstaendiger Verifikation!)

---

## Rollback-Plan

Falls die Migration fehlschlaegt:

```bash
# Auf Server B: Stack stoppen
docker compose -f docker-compose.traefik.yml down

# DNS zurueck auf Server A (falls bereits umgeschaltet)

# Auf Server A: NocoDB wieder starten
ssh user@server-a
docker start $NOCODB_CONTAINER
```

> **Wichtig:** Server A erst herunterfahren wenn die Migration vollstaendig verifiziert ist!
> Den Dump auf Server A aufbewahren bis der neue Server stabil laeuft.

---

## Checkliste

```text
Migration: Server A → Server B
Datum: ____________    Durchfuehrung: ____________

Vorbereitung:
  [ ] Server B bereit (Docker, Compose, CS-NocoDB Repository)
  [ ] .env auf Server B konfiguriert
  [ ] DNS-TTL reduziert (falls Hostname gleich bleibt)
  [ ] Wartungsfenster kommuniziert

Server A - Backup:
  [ ] PostgreSQL-Container identifiziert: ____________________
  [ ] NocoDB-Container gestoppt
  [ ] pg_dump erfolgreich: nocodb_dump.sql.gz (Groesse: ________)
  [ ] nocodb-data.tar.gz erstellt (Groesse: ________) oder N/A (S3)
  [ ] Dateien auf Server B uebertragen

Server B - Wiederherstellung:
  [ ] Datenbank gestartet und bereit
  [ ] Init-Container ausgefuehrt
  [ ] psql restore erfolgreich
  [ ] Daten-Dateien entpackt (oder N/A bei S3)
  [ ] NocoDB gestartet

Verifizierung:
  [ ] Login erfolgreich
  [ ] Bases und Tabellen vorhanden
  [ ] Records stichprobenartig geprueft
  [ ] Attachments erreichbar
  [ ] Collation-Fix durchgefuehrt
  [ ] ANALYZE ausgefuehrt

Nacharbeiten:
  [ ] API-Token erstellt
  [ ] Backup-Schedule aktiviert
  [ ] Test-Backup erfolgreich
  [ ] DNS umgeschaltet
  [ ] Server A heruntergefahren
```

---

## Fehlerbehebung

### pg_dump: "connection refused" auf Server A

Der PostgreSQL-Container laeuft nicht oder ist nicht erreichbar:

```bash
# Container-Status pruefen
docker ps -a | grep postgres

# Container-Logs pruefen
docker logs $PG_CONTAINER --tail 20
```

### "role nocodb does not exist" bei psql restore

Die Rolle wurde noch nicht erstellt. Sicherstellen dass der Init-Container gelaufen ist:

```bash
docker compose -f docker-compose.traefik.yml up nocodb-init

# Oder manuell pruefen:
docker exec ${STACK_NAME}_DATABASE psql -U nocodb -l
```

### Collation-Mismatch Warnings

Normal bei PostgreSQL-Versionswechsel. Beheben:

```bash
docker exec ${STACK_NAME}_DATABASE psql -U nocodb -d nocodb -c \
    "ALTER DATABASE nocodb REFRESH COLLATION VERSION;"
```

Oder automatisch: `INIT_COLLATION_AUTO_FIX=true` in `.env` und Init-Container ausfuehren.

### Attachments fehlen nach Migration

1. **Lokaler Storage:** `nocodb-data.tar.gz` vergessen? In das Volume entpacken (Schritt 8).
2. **S3-Storage:** `NC_S3_BUCKET_NAME` und S3-Credentials in `.env` pruefen.
3. **Berechtigungen:** Volume-Owner muss `1000:1000` sein.

### Langsame Queries nach Migration

```bash
docker exec ${STACK_NAME}_DATABASE vacuumdb -U nocodb --all --analyze-in-stages
```

### "ERROR: relation already exists" waehrend psql restore

Unbedenklich. Der Init-Container hat bereits eine leere Datenbank angelegt.
Die Daten werden trotzdem korrekt importiert. Alternativ vor dem Restore
die Datenbank leeren:

```bash
# ACHTUNG: Loescht alle Daten in der Datenbank!
docker exec ${STACK_NAME}_DATABASE psql -U nocodb -d nocodb -c \
    "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
```
