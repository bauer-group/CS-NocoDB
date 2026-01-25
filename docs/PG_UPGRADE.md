# PostgreSQL In-Place Major Version Upgrade

## Übersicht

Das Script `tools/pg_upgrade_inplace.sh` führt ein In-Place Upgrade von PostgreSQL durch, ohne die Daten zu kopieren. Es nutzt Hardlinks, wodurch kein zusätzlicher Speicherplatz benötigt wird.

**Unterstützte Upgrades:** PostgreSQL 14 → 15 → 16 → 17 → 18

## Voraussetzungen

| Anforderung | Beschreibung |
|-------------|--------------|
| Docker | Muss installiert und lauffähig sein |
| Root-Rechte | `sudo` für Dateisystem-Operationen |
| Gestoppte Container | Alle Container mit dem Volume müssen gestoppt sein |
| Speicherplatz | Minimal (nur für Logs, ~100MB) |

## Schnellstart

```bash
# 1. Stack stoppen
docker compose down

# 2. Upgrade durchführen (Standard: 15 → 18)
sudo ./tools/pg_upgrade_inplace.sh --volume-name ${STACK_NAME}-postgres

# 3. Stack starten
docker compose up -d

# 4. Statistiken aktualisieren
docker exec ${STACK_NAME}_DATABASE vacuumdb -U nocodb --all --analyze-in-stages
```

## Nutzung

### Syntax

```bash
./pg_upgrade_inplace.sh [OPTIONEN] <VOLUME_PFAD>
./pg_upgrade_inplace.sh [OPTIONEN] --volume-name <DOCKER_VOLUME_NAME>
```

### Optionen

| Option | Beschreibung | Standard |
|--------|--------------|----------|
| `--from <VERSION>` | Quell-PostgreSQL-Version | 15 |
| `--to <VERSION>` | Ziel-PostgreSQL-Version | 18 |
| `--volume-name <NAME>` | Docker Volume Name (Alternative zu Pfad) | - |
| `--dry-run` | Nur prüfen, keine Änderungen | false |
| `--force` | Keine Bestätigung abfragen | false |
| `--help` | Hilfe anzeigen | - |

### Beispiele

```bash
# Standard-Upgrade mit Volume-Pfad
sudo ./pg_upgrade_inplace.sh /var/lib/docker/volumes/db_crm_app-postgres

# Mit Docker Volume Name (empfohlen)
sudo ./pg_upgrade_inplace.sh --volume-name db_crm_app-postgres

# Andere Versionen (z.B. 14 → 17)
sudo ./pg_upgrade_inplace.sh --from 14 --to 17 --volume-name mystack-postgres

# Dry-Run: Nur prüfen, nichts ändern
sudo ./pg_upgrade_inplace.sh --dry-run --volume-name db_crm_app-postgres

# Für Scripting ohne Bestätigung
sudo ./pg_upgrade_inplace.sh --force --volume-name db_crm_app-postgres

# Mit Umgebungsvariablen für UID/GID
sudo PG_UID=1000 PG_GID=1000 ./pg_upgrade_inplace.sh --volume-name mystack-postgres
```

## Ablauf

Das Script führt folgende Schritte durch:

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         PRE-FLIGHT CHECKS                           │
├─────────────────────────────────────────────────────────────────────┤
│  ✓ Docker verfügbar                                                 │
│  ✓ Volume-Pfad existiert                                            │
│  ✓ PG_VERSION passt zur Quell-Version                               │
│  ✓ Keine laufenden Container mit diesem Volume                      │
│  ✓ Ausreichend Speicherplatz                                        │
│  ✓ Helper-Image verfügbar (wird ggf. heruntergeladen)               │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          UPGRADE-PROZESS                            │
├─────────────────────────────────────────────────────────────────────┤
│  1. Verschiebe _data → v15 (Backup des alten Clusters)              │
│  2. Erstelle neues leeres _data Verzeichnis                         │
│  3. Starte pg_upgrade im Docker Container                           │
│  4. Verifiziere neuen Cluster (PG_VERSION)                          │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
            ┌───────────────┐           ┌───────────────┐
            │    ERFOLG     │           │    FEHLER     │
            ├───────────────┤           ├───────────────┤
            │ Neuer Cluster │           │ Automatischer │
            │ in _data      │           │ Rollback      │
            │               │           │               │
            │ Backup in v15 │           │ Alter Cluster │
            │ (kann später  │           │ wiederher-    │
            │ gelöscht      │           │ gestellt      │
            │ werden)       │           │               │
            └───────────────┘           └───────────────┘
```

## Verzeichnisstruktur

### Vor dem Upgrade

```text
/var/lib/docker/volumes/mystack-postgres/
└── _data/                    ← Aktiver PostgreSQL 15 Cluster
    ├── PG_VERSION            (Inhalt: "15")
    ├── base/
    ├── global/
    ├── pg_wal/
    └── ...
```

### Nach dem Upgrade

```text
/var/lib/docker/volumes/mystack-postgres/
├── _data/                    ← Aktiver PostgreSQL 18 Cluster (NEU)
│   ├── PG_VERSION            (Inhalt: "18")
│   ├── base/
│   ├── global/
│   ├── pg_wal/
│   └── ...
│
└── v15/                      ← Backup des alten Clusters
    ├── PG_VERSION            (Inhalt: "15")
    ├── base/
    └── ...
```

## Nach dem Upgrade

### 1. Container starten

```bash
docker compose up -d
```

### 2. Statistiken aktualisieren (wichtig!)

Nach einem Major-Upgrade sollten die Optimizer-Statistiken neu erstellt werden:

```bash
# Empfohlen: Stufenweise Analyse (schneller, weniger Last)
docker exec ${STACK_NAME}_DATABASE vacuumdb -U nocodb --all --analyze-in-stages

# Alternativ: Vollständige Analyse
docker exec ${STACK_NAME}_DATABASE vacuumdb -U nocodb --all --analyze
```

### 3. Extensions aktualisieren (falls genutzt)

```bash
docker exec ${STACK_NAME}_DATABASE psql -U nocodb -d nocodb -c "
SELECT extname, extversion FROM pg_extension WHERE extname != 'plpgsql';
"

# Falls Extensions vorhanden, aktualisieren:
docker exec ${STACK_NAME}_DATABASE psql -U nocodb -d nocodb -c "
ALTER EXTENSION <extension_name> UPDATE;
"
```

### 4. Backup löschen (optional)

Nach erfolgreicher Prüfung kann das Backup gelöscht werden:

```bash
# Prüfen ob alles funktioniert
docker exec ${STACK_NAME}_DATABASE psql -U nocodb -d nocodb -c "SELECT version();"

# Backup löschen
sudo rm -rf /var/lib/docker/volumes/${STACK_NAME}-postgres/v15
```

## Rollback

### Automatischer Rollback

Bei Fehlern während des Upgrades führt das Script automatisch einen Rollback durch:

1. Neues `_data` Verzeichnis wird gelöscht
2. Backup `v15` wird zurück nach `_data` verschoben
3. Alter Cluster ist wieder aktiv

### Manueller Rollback

Falls der automatische Rollback fehlschlägt oder nach dem Upgrade Probleme auftreten:

```bash
# 1. Container stoppen
docker compose down

# 2. Neuen Cluster löschen
sudo rm -rf /var/lib/docker/volumes/${STACK_NAME}-postgres/_data

# 3. Alten Cluster wiederherstellen
sudo mv /var/lib/docker/volumes/${STACK_NAME}-postgres/v15 \
        /var/lib/docker/volumes/${STACK_NAME}-postgres/_data

# 4. docker-compose.yml anpassen: POSTGRES_VERSION auf alte Version setzen
# In .env: POSTGRES_VERSION=15

# 5. Container starten
docker compose up -d
```

## Logs & Diagnose

### Log-Dateien

Alle Upgrade-Logs werden gespeichert unter:

```text
/var/lib/docker/pg-upgrade-<volume-name>/
├── logs/
│   └── pg_upgrade_15_to_18_20250125_143022.log
└── markers/
    └── upgraded_15_to_18.ok
```

### Log-Datei anzeigen

```bash
# Neuestes Log anzeigen
cat /var/lib/docker/pg-upgrade-${STACK_NAME}-postgres/logs/*.log

# Bei Fehlern: Detaillierte pg_upgrade Ausgabe
grep -i error /var/lib/docker/pg-upgrade-${STACK_NAME}-postgres/logs/*.log
```

## Fehlerbehebung

### Fehler: "Container nutzen dieses Volume"

```text
[pg-upgrade][ERROR] Folgende Container nutzen dieses Volume: mystack_DATABASE
```

**Lösung:** Alle Container mit diesem Volume stoppen:

```bash
docker compose down
# oder
docker stop ${STACK_NAME}_DATABASE
```

### Fehler: "PG_VERSION ist X, erwartet Y"

```text
[pg-upgrade][ERROR] PG_VERSION ist 14, erwartet 15.x
```

**Lösung:** Die `--from` Option anpassen:

```bash
sudo ./pg_upgrade_inplace.sh --from 14 --to 18 --volume-name mystack-postgres
```

### Fehler: "Verzeichnis v15 existiert bereits"

```text
[pg-upgrade][ERROR] Verzeichnis /var/.../v15 existiert bereits
```

**Ursache:** Ein früheres Upgrade wurde durchgeführt oder abgebrochen.

**Lösung:**
```bash
# Prüfen ob _data die aktuelle Version enthält
cat /var/lib/docker/volumes/${STACK_NAME}-postgres/_data/PG_VERSION

# Falls _data bereits aktuell ist, altes Backup löschen:
sudo rm -rf /var/lib/docker/volumes/${STACK_NAME}-postgres/v15

# Falls Rollback nötig, siehe Abschnitt "Manueller Rollback"
```

### Fehler: "Konnte Image nicht herunterladen"

```text
[pg-upgrade][ERROR] Konnte Image nicht herunterladen: tianon/postgres-upgrade:15-to-18
```

**Mögliche Ursachen:**
- Keine Internetverbindung
- Docker Hub Rate Limit erreicht
- Image existiert nicht für diese Versionskombination

**Lösung:**
```bash
# Manuell prüfen welche Images verfügbar sind
docker search tianon/postgres-upgrade

# Alternativ: Image manuell pullen
docker pull tianon/postgres-upgrade:15-to-18
```

### Fehler: pg_upgrade schlägt fehl

Typische Ursachen und Lösungen:

| Fehler | Ursache | Lösung |
|--------|---------|--------|
| `lc_collate mismatch` | Unterschiedliche Locale | Container mit gleicher Locale starten |
| `extension ... not available` | Extension fehlt in neuer Version | Extension vor Upgrade deinstallieren |
| `could not access directory` | Berechtigungsproblem | `chown` auf Volume ausführen |

## Umgebungsvariablen

| Variable | Beschreibung | Standard |
|----------|--------------|----------|
| `PG_UID` | User-ID für PostgreSQL-Dateien | 999 |
| `PG_GID` | Group-ID für PostgreSQL-Dateien | 999 |
| `MAJOR_OLD` | Quell-Version (Alternative zu --from) | 15 |
| `MAJOR_NEW` | Ziel-Version (Alternative zu --to) | 18 |

Beispiel:
```bash
sudo PG_UID=1000 PG_GID=1000 MAJOR_OLD=14 MAJOR_NEW=17 \
    ./pg_upgrade_inplace.sh --volume-name mystack-postgres
```

## Technische Details

### Warum Hardlinks?

Das Script nutzt `pg_upgrade --link`, welches Hardlinks statt Kopien erstellt:

- **Vorteil:** Kein zusätzlicher Speicherplatz benötigt
- **Vorteil:** Upgrade dauert nur Sekunden statt Stunden
- **Nachteil:** Nach dem ersten Start des neuen Clusters ist kein Rollback mehr möglich (Dateien werden modifiziert)

### Helper-Image

Das Script nutzt das offizielle `tianon/postgres-upgrade` Image:

- Enthält beide PostgreSQL-Versionen
- Führt `pg_upgrade` sicher aus
- Unterstützt alle gängigen Upgrade-Pfade

### Sicherheitsfeatures

| Feature | Beschreibung |
|---------|--------------|
| Pre-Flight Checks | Prüft alle Voraussetzungen vor dem Start |
| Read-Only Mount | Alter Cluster wird nur lesend gemountet |
| Automatischer Rollback | Bei Fehler wird alter Cluster wiederhergestellt |
| Signal-Handling | CTRL+C zeigt Rollback-Anleitung |
| Logging | Vollständige Protokollierung aller Schritte |

## Best Practices

1. **Backup erstellen** - Auch wenn das Script ein lokales Backup anlegt, sollte ein externes Backup existieren
2. **Dry-Run zuerst** - `--dry-run` zeigt alle Checks ohne Änderungen
3. **Außerhalb der Geschäftszeiten** - Upgrade erfordert kurze Downtime
4. **Statistiken aktualisieren** - `vacuumdb --analyze-in-stages` nach dem Upgrade
5. **Backup behalten** - v15-Ordner erst nach erfolgreicher Prüfung löschen

## Referenzen

- [PostgreSQL pg_upgrade Dokumentation](https://www.postgresql.org/docs/current/pgupgrade.html)
- [tianon/postgres-upgrade auf Docker Hub](https://hub.docker.com/r/tianon/postgres-upgrade)
- [PostgreSQL Release Notes](https://www.postgresql.org/docs/release/)

---

**Erstellt:** 2025-01-25
**Für:** NocoDB mit PostgreSQL-Backend
