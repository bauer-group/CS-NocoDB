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

**Single-Instance** (eine NocoDB-Instanz):

| Modus | Compose-File | Beschreibung | Anwendungsfall |
|-------|--------------|--------------|----------------|
| **Local** | `docker-compose.local.yml` | Direkter Port-Zugriff | Entwicklung, lokaler Test |
| **Traefik** | `docker-compose.traefik.yml` | HTTPS + Let's Encrypt | Production |
| **Traefik Local** | `docker-compose.traefik-local.yml` | HTTP + IP-Whitelist | Internes Netzwerk |
| **Traefik Header Auth** | `docker-compose.traefik-header-auth.yml` | HTTPS + Header-Auth | API-Zugriff, Reverse Proxy |
| **Development** | `docker-compose.development.yml` | Lokale Image-Builds + MinIO | Entwicklung, Testing |

**Cluster** (HAProxy + mehrere NocoDB-Instanzen + Redis):

| Modus | Compose-File | Beschreibung | Anwendungsfall |
|-------|--------------|--------------|----------------|
| **Cluster** | `docker-compose.cluster.yml` | HAProxy + 4/6/8 Instanzen + Redis, HTTPS | Hohe API-Last, viele parallele Zugriffe |
| **Cluster Development** | `docker-compose.cluster-development.yml` | HAProxy + 2 Instanzen + Redis, Builds + MinIO | Cluster-Verhalten lokal testen |

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

#### Cluster Mode

Für hohe API-Last, etwa viele parallele Schreibzugriffe aus Automatisierungen:

```bash
docker compose -f docker-compose.cluster.yml up -d
# Zugriff: https://${SERVICE_HOSTNAME}
```

**Warum ein Cluster:** NocoDB ist ein einzelner Node-Prozess und damit
single-threaded — eine Instanz nutzt genau **einen** CPU-Core, unabhängig davon,
wie viele der Host hat. Es gibt keinen Cluster-Mode im Prozess selbst. Mehr
Durchsatz gibt es ausschließlich über mehr Container.

Der Cluster-Stack bringt drei Dinge mit, die der Single-Instance-Stack nicht hat:

| Komponente | Aufgabe |
|------------|---------|
| **HAProxy** | Load Balancer *im* Stack — damit ist der Stack unabhängig vom Edge-Proxy (funktioniert genauso hinter nginx, Caddy, cloudflared oder an einem direkt gebundenen Port) |
| **Redis** | Gemeinsamer Metadaten-Cache, Job-Queue und socket.io-Backplane. **Zwingend** — ohne Redis sehen die Instanzen die Schemaänderungen der jeweils anderen nicht, und Live-Updates erreichen nur die eigene Instanz |
| **Migrations-Gate** | `nocodb-server-1` läuft als Erster, alle anderen warten per `depends_on` auf dessen Health |

**Die Concurrency-Bremse ist der eigentliche Gewinn.** Ein Node-Prozess lehnt
Überlast nicht ab — er nimmt alle Requests an und teilt eine CPU unter ihnen auf.
Bei 500 gleichzeitigen Requests bekommt jeder 1/500, alles läuft gemeinsam in den
Timeout, *inklusive Healthcheck*. Die Instanz flappt DOWN, ihr Traffic fällt auf
die übrigen, die daran ebenfalls ersticken. HAProxy begrenzt deshalb die
gleichzeitigen Requests je Instanz auf `NC_DB_POOL_MAX` und stellt den Rest in
eine Queue mit definiertem Timeout:

| Stufe | Grenze | Ergebnis |
|-------|--------|----------|
| Instanz ausgelastet | `maxconn` (= `NC_DB_POOL_MAX_CLUSTER`) | Queue, kein Fehler |
| Zu lange in der Queue | `timeout queue` (30s) | **503** |
| Instanz zu langsam | `timeout server` (60s) | **504** |
| WebSocket aktiv | `timeout tunnel` (24h) | überschreibt client+server |

Ohne diese Grenze hängt ein Request bis zu **10 Minuten** — so lange wartet
NocoDBs interner `acquireConnectionTimeout` auf eine freie DB-Verbindung, bevor
er aufgibt.

#### Was den Durchsatz begrenzt — und was NICHT

> Diese Werte stammen aus einem Lasttest (Docker Desktop, 8 Kerne, viele kleine
> Einzel-Inserts über die Record-API). Die absoluten Zahlen übertragen sich
> nicht 1:1 auf einen 24-Core-Server, die **Verhältnisse** aber schon.

Unter Last steht **NocoDB bei ~105 % CPU** (ein Kern voll ausgelastet),
**PostgreSQL bei ~11 %**. Der Engpass ist der einzelne JavaScript-Thread, der
jeden Request parst, authentifiziert, validiert und serialisiert — nicht die
Datenbank und nicht der Connection-Pool.

Daraus folgt, was messbar hilft und was nicht:

| Maßnahme | Gemessener Effekt |
|----------|-------------------|
| `NC_DB_POOL_MAX` 10 → 80 (Single-Instance) | **+9 %** — der Pool war nie der Engpass |
| PostgreSQL `synchronous_commit=off` / `commit_delay` | **0 % / negativ** — die DB ist nicht der Engpass |
| **Mehr Instanzen** (mehr JS-Threads) | **der eigentliche Hebel** — der einzige Weg, mehr Kerne zu nutzen |
| **Bulk-Inserts** (Arrays statt Einzelsätze) | **~11×** — falls der API-Client sie senden kann |

**Konsequenz:** Der Pool-Fix und PG-Tuning lösen ein Durchsatzproblem durch
viele kleine Einzel-Requests **nicht**. Wirksam sind nur zwei Dinge — mehr
Instanzen (dieser Cluster) und, wo der Client es erlaubt, das Bündeln vieler
Datensätze in einen Request (`POST /api/v2/tables/{tableId}/records` mit einem
Array). Der HAProxy-`maxconn` löst ein **anderes** Problem: nicht den Durchsatz,
sondern die Überlast-Lawine (das ursprüngliche 504-Symptom).

Für insert-lastige Workloads kann ein höherer `NC_DB_POOL_MAX_CLUSTER`
(z. B. 20–25) mehr Durchsatz bringen, weil mehr Sätze gleichzeitig in Bearbeitung
sind — **an der eigenen Last messen**, der JS-Thread bleibt die harte Grenze.

**Voraussetzungen:**

- Alles aus dem Traefik-Modus (externes Netz, DNS, Certresolver)
- Host-Ressourcen passend zur gewählten Skalierungsstufe (siehe Tabelle unten):
  **16 GB / 16 Cores** für Stufe S bis **32 GB / 24 Cores** für Stufe L
- `NC_AUTH_JWT_SECRET` gesetzt und auf **allen** Instanzen identisch — sonst
  akzeptiert Instanz B die von Instanz A ausgestellten Tokens nicht

> **`NC_CONNECTION_ENCRYPT_KEY` ist bewusst nicht gesetzt.** Die Zugangsdaten
> externer Datenquellen bleiben damit unverschlüsselt in der Datenbank — so wie
> bisher auch. Das Aktivieren ist **irreversibel** und darf nur mit *genau einer*
> laufenden Instanz erfolgen, weil parallel startende Instanzen die Credentials
> durch Doppelverschlüsselung zerstören. Anleitung dazu in `.env.example`.

**Skalierungsstufen.** Die Instanzzahl wird über Compose-Profile gesteuert —
entweder in der `.env` (`COMPOSE_PROFILES=`) oder per `--profile` auf der
Kommandozeile. Der gesamte Stack ist dabei auf ein Ressourcenbudget begrenzt;
alle Container haben Limits, nicht nur die NocoDB-Instanzen:

| Stufe | `COMPOSE_PROFILES` | Instanzen | Budget | Summe der Limits |
|-------|--------------------|-----------|--------|------------------|
| **S** | *(leer)* | 4 | 16 GB / 16 Cores | 15,0 Cores / 15,21 GB |
| **M** | `scale6` | 6 | 24 GB / 20 Cores | 20,0 Cores / 21,00 GB |
| **L** | `scale8` | 8 | 32 GB / 24 Cores | 23,0 Cores / 30,00 GB |

**Wichtig:** Das Profil ändert nur die *Anzahl* der Instanzen. Die zugehörigen
Limits für PostgreSQL, Redis und HAProxy müssen zur Stufe passen — `.env.example`
enthält je Stufe einen vollständigen, kopierbaren Block sowie eine Tabelle,
welche Werte beim Ändern zwingend zusammen angepasst werden müssen.

Nachrechnen:

```bash
docker compose -f docker-compose.cluster.yml config | grep -E "cpus:|memory:"
```

Warum nicht mehr Instanzen: PostgreSQL degradiert jenseits von etwa 2–4× CPU-Cores
an *aktiven* Verbindungen. Bei 24 Cores liegt das Optimum bei 50–100 — das
erreichen bereits 8 Instanzen × Pool 10. Ein größerer Pool je Instanz macht die
Datenbank langsamer, nicht schneller.

**Lokal testen:**

```bash
docker compose -f docker-compose.cluster-development.yml up -d --build
# Zugriff: http://localhost:${EXPOSED_APP_PORT}
```

Zwei Instanzen reichen aus, um alles zu prüfen, was am Cluster-Betrieb anders
ist: Migrations-Gate, Cache-Kohärenz über Redis, socket.io-Fan-out und Sticky
Sessions.

**HAProxy-Statusseite** (nur innerhalb des Containers erreichbar, bewusst nicht
aus dem Docker-Netz):

```bash
docker exec -it ${STACK_NAME}_LB wget -qO- http://127.0.0.1:8404/stats
```

Unter Last sind `qcur`/`qmax` > 0 dort **kein Warnsignal**, sondern der Beleg,
dass die Queue arbeitet und die Überlast vor der Datenbank abgefangen wird.

### Backup-Sidecar

Alle Compose-Files unterstuetzen einen optionalen Backup-Sidecar:

```bash
# Aktivieren mit --profile backup
docker compose -f docker-compose.traefik.yml --profile backup up -d
```

**Dauerhaft aktivieren ueber `COMPOSE_PROFILES`:** Docker Compose liest die
Standardvariable `COMPOSE_PROFILES` aus der `.env`. Damit muss `--profile backup`
nicht mehr bei jedem `up` angegeben werden:

```bash
# in .env
COMPOSE_PROFILES=backup
```

Danach reicht `docker compose up -d` — der Backup-Sidecar startet automatisch mit.
Mehrere Profile sind komma-separiert (`COMPOSE_PROFILES=backup,minio`). Zum
temporaeren Deaktivieren leer lassen (`COMPOSE_PROFILES=`) oder Zeile entfernen.

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
├── docker-compose.cluster.yml            # Cluster: HAProxy + 4/6/8 Instanzen + Redis
├── docker-compose.cluster-development.yml # Cluster lokal: 2 Instanzen + MinIO
├── haproxy/
│   └── haproxy.cfg                       # Load-Balancer-Config (beide Cluster-Modi)
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
| `NC_DISABLE_ERR_REPORTS` | `true` | Error-Reporting deaktiviert (eigener Schalter, **nicht** von `NC_DISABLE_TELE` abgedeckt) |
| `NC_DISABLE_SUPPORT_CHAT` | `true` | Drittanbieter-Chat-Widget deaktiviert |
| `NC_DISABLE_AUDIT` | `true` | Audit-Logging deaktiviert |

> **Registrierung nur per Einladung ist keine Umgebungsvariable.**
> Frühere Versionen dieses Stacks setzten `NC_INVITE_ONLY_SIGNUP=true`. Diese
> Variable existiert in NocoDB nicht und wurde nirgends gelesen — die
> Registrierung stand trotz der Einstellung **offen**.
>
> Der reale Schalter ist das Flag `invite_only_signup` in der Tabelle
> `nc_store`, Default `false`. Es ist ausschließlich über die
> **Super-Admin-UI** (Account Settings) oder die App-Settings-API setzbar.
> Nach jeder Neuinstallation aktiv prüfen.

#### Optionale Einstellungen

In `.env` konfigurierbar:

```bash
# Query & Bulk Operation Limits
DB_QUERY_LIMIT_MAX=1000              # Max Records pro GET-Request (default: 100)
NC_DATA_PAYLOAD_LIMIT=100000         # Max Entities pro Bulk-Request (default: 100)
NC_REQUEST_BODY_SIZE=268435456       # 256 MB - Max Request-Body

# Attachment-Limits
NC_ATTACHMENT_FIELD_SIZE=268435456   # 256 MB
NC_NON_ATTACHMENT_FIELD_SIZE=268435456  # 256 MB
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

**Single-instance** (one NocoDB instance):

| Mode | Compose File | Description | Use Case |
|------|-------------|-------------|----------|
| **Local** | `docker-compose.local.yml` | Direct port access | Development, local testing |
| **Traefik** | `docker-compose.traefik.yml` | HTTPS + Let's Encrypt | Production |
| **Traefik Local** | `docker-compose.traefik-local.yml` | HTTP + IP whitelist | Internal network |
| **Traefik Header Auth** | `docker-compose.traefik-header-auth.yml` | HTTPS + header auth | API access, reverse proxy |
| **Development** | `docker-compose.development.yml` | Local image builds + MinIO | Development, testing |

**Cluster** (HAProxy + multiple NocoDB instances + Redis):

| Mode | Compose File | Description | Use Case |
|------|-------------|-------------|----------|
| **Cluster** | `docker-compose.cluster.yml` | HAProxy + 4/6/8 instances + Redis, HTTPS | High API load, many parallel requests |
| **Cluster Development** | `docker-compose.cluster-development.yml` | HAProxy + 2 instances + Redis, builds + MinIO | Testing cluster behaviour locally |

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

#### Cluster Mode

For high API load, e.g. many parallel writes from automation:

```bash
docker compose -f docker-compose.cluster.yml up -d
# Access: https://${SERVICE_HOSTNAME}
```

**Why a cluster:** NocoDB is a single Node process and therefore
single-threaded — one instance uses exactly **one** CPU core, no matter how many
the host has. There is no in-process cluster mode. More throughput is only
available through more containers.

The cluster stack adds three things the single-instance stack does not have:

| Component | Purpose |
|-----------|---------|
| **HAProxy** | Load balancer *inside* the stack — makes the stack independent of the edge proxy (works equally behind nginx, Caddy, cloudflared, or a directly bound port) |
| **Redis** | Shared metadata cache, job queue and socket.io backplane. **Mandatory** — without it, instances do not see each other's schema changes and live updates only reach the emitting instance |
| **Migration gate** | `nocodb-server-1` starts first; all others wait on its health via `depends_on` |

**The concurrency limit is the actual win.** A Node process does not reject
overload — it accepts every request and splits one CPU among them. At 500
concurrent requests each gets 1/500, everything times out together *including
the health check*. The instance flaps DOWN, its traffic lands on the others,
which choke on it too. HAProxy therefore caps concurrent requests per instance
at `NC_DB_POOL_MAX` and queues the rest with a defined timeout:

| Stage | Limit | Result |
|-------|-------|--------|
| Instance saturated | `maxconn` (= `NC_DB_POOL_MAX_CLUSTER`) | queued, no error |
| Queued too long | `timeout queue` (30s) | **503** |
| Instance too slow | `timeout server` (60s) | **504** |
| WebSocket active | `timeout tunnel` (24h) | overrides client+server |

Without that limit a request hangs for up to **10 minutes** — that is how long
NocoDB's internal `acquireConnectionTimeout` waits for a free DB connection
before giving up.

#### What limits throughput — and what does NOT

> These figures come from a load test (Docker Desktop, 8 cores, many small
> single-record inserts via the record API). The absolute numbers do not carry
> over 1:1 to a 24-core server, but the **ratios** do.

Under load, **NocoDB sits at ~105 % CPU** (one core fully saturated),
**PostgreSQL at ~11 %**. The bottleneck is the single JavaScript thread that
parses, authenticates, validates and serializes every request — not the database
and not the connection pool.

What that means for what actually helps:

| Measure | Measured effect |
|---------|-----------------|
| `NC_DB_POOL_MAX` 10 → 80 (single instance) | **+9 %** — the pool was never the bottleneck |
| PostgreSQL `synchronous_commit=off` / `commit_delay` | **0 % / negative** — the DB is not the bottleneck |
| **More instances** (more JS threads) | **the real lever** — the only way to use more cores |
| **Bulk inserts** (arrays instead of single records) | **~11×** — if the API client can send them |

**Consequence:** the pool fix and PG tuning do **not** solve a throughput problem
caused by many small single requests. Only two things help — more instances (this
cluster) and, where the client allows it, batching many records into one request
(`POST /api/v2/tables/{tableId}/records` with an array). The HAProxy `maxconn`
solves a *different* problem: not throughput, but the overload avalanche (the
original 504 symptom).

For insert-heavy workloads a higher `NC_DB_POOL_MAX_CLUSTER` (e.g. 20–25) can
raise throughput by keeping more records in flight — **measure against your own
load**; the JS thread stays the hard ceiling.

**Prerequisites:**

- Everything from Traefik mode (external network, DNS, cert resolver)
- Host resources matching the chosen scaling tier (see table below):
  **16 GB / 16 cores** for tier S up to **32 GB / 24 cores** for tier L
- `NC_AUTH_JWT_SECRET` set and identical across **all** instances — otherwise
  instance B rejects tokens issued by instance A

> **`NC_CONNECTION_ENCRYPT_KEY` is deliberately left unset.** External data
> source credentials therefore stay unencrypted in the database — same as
> before. Enabling it is **irreversible** and must be done with *exactly one*
> running instance, because instances starting in parallel destroy the
> credentials through double encryption. See `.env.example` for the procedure.

**Scaling tiers.** Instance count is controlled by Compose profiles — either in
`.env` (`COMPOSE_PROFILES=`) or via `--profile` on the command line. The whole
stack is capped by a resource budget; every container has limits, not just the
NocoDB instances:

| Tier | `COMPOSE_PROFILES` | Instances | Budget | Sum of limits |
|------|--------------------|-----------|--------|---------------|
| **S** | *(empty)* | 4 | 16 GB / 16 cores | 15.0 cores / 15.21 GB |
| **M** | `scale6` | 6 | 24 GB / 20 cores | 20.0 cores / 21.00 GB |
| **L** | `scale8` | 8 | 32 GB / 24 cores | 23.0 cores / 30.00 GB |

**Important:** the profile only changes the *number* of instances. The matching
limits for PostgreSQL, Redis and HAProxy have to fit the tier — `.env.example`
carries a complete, copy-pasteable block per tier plus a table of which values
must be changed together.

Verify:

```bash
docker compose -f docker-compose.cluster.yml config | grep -E "cpus:|memory:"
```

Why not more instances: PostgreSQL degrades beyond roughly 2–4× CPU cores of
*active* connections. At 24 cores the sweet spot is 50–100 — already reached by
8 instances × pool 10. A larger pool per instance makes the database slower, not
faster.

**Testing locally:**

```bash
docker compose -f docker-compose.cluster-development.yml up -d --build
# Access: http://localhost:${EXPOSED_APP_PORT}
```

Two instances are enough to exercise everything that differs in cluster
operation: migration gate, Redis cache coherence, socket.io fan-out and sticky
sessions.

**HAProxy stats page** (reachable only inside the container, deliberately not
from the Docker network):

```bash
docker exec -it ${STACK_NAME}_LB wget -qO- http://127.0.0.1:8404/stats
```

Under load, `qcur`/`qmax` > 0 there is **not** a warning sign but the proof that
the queue is working and overload is being absorbed in front of the database.

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
| `NC_DISABLE_ERR_REPORTS` | `true` | Error reporting disabled (separate switch, **not** covered by `NC_DISABLE_TELE`) |
| `NC_DISABLE_SUPPORT_CHAT` | `true` | Third-party chat widget disabled |
| `NC_DISABLE_AUDIT` | `true` | Audit logging disabled |

> **Invite-only registration is not an environment variable.**
> Earlier versions of this stack set `NC_INVITE_ONLY_SIGNUP=true`. That variable
> does not exist in NocoDB and was never read — registration was **open**
> despite the setting.
>
> The actual switch is the `invite_only_signup` flag in the `nc_store` table,
> defaulting to `false`. It can only be set through the **super-admin UI**
> (Account Settings) or the app-settings API. Verify it after every fresh
> installation.

#### Optional Settings

Configurable in `.env`:

```bash
# Query & bulk operation limits
DB_QUERY_LIMIT_MAX=1000              # Max records per GET request (default: 100)
NC_DATA_PAYLOAD_LIMIT=100000         # Max entities per bulk request (default: 100)
NC_REQUEST_BODY_SIZE=268435456       # 256 MB - Max request body

# Attachment limits
NC_ATTACHMENT_FIELD_SIZE=268435456   # 256 MB
NC_NON_ATTACHMENT_FIELD_SIZE=268435456  # 256 MB
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
