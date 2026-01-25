# NocoDB Audit-Tabellen Bereinigung

## Übersicht

Bei aktiviertem `NC_DISABLE_AUDIT=true` werden keine neuen Einträge in die Audit-Tabellen geschrieben.
Bestehende historische Daten bleiben jedoch erhalten und können bei Upgrades Probleme verursachen.

Dieses Dokument beschreibt die sichere Bereinigung dieser Tabellen.

## Betroffene Tabellen

| Tabelle | Beschreibung | Bei NC_DISABLE_AUDIT=true |
|---------|--------------|---------------------------|
| `nc_audit_v2` | Hauptaudit-Log (Benutzeraktionen) | Nicht mehr beschrieben |
| `nc_hook_logs_v2` | Webhook-Ausführungslogs | Weiterhin beschrieben (optional bereinigen) |
| `nc_sync_logs_v2` | Sync-Logs | Weiterhin beschrieben (optional bereinigen) |
| `nc_automation_executions` | Automation-Logs | Weiterhin beschrieben (optional bereinigen) |

## Voraussetzungen

1. **Backup erstellen** (WICHTIG!)
2. NocoDB-Container stoppen (empfohlen, aber nicht zwingend)
3. Direkter Zugriff auf PostgreSQL-Datenbank

## psql-Befehl Erklärung

Der `psql`-Befehl ist der PostgreSQL-Kommandozeilen-Client:

```bash
psql -U nocodb -d nocodb -c "SQL_BEFEHL"
```

| Parameter    | Bedeutung                                      |
| ------------ | ---------------------------------------------- |
| `psql`       | PostgreSQL Kommandozeilen-Client               |
| `-U nocodb`  | Benutzername (`-U` = User), hier: `nocodb`     |
| `-d nocodb`  | Datenbankname (`-d` = Database), hier: `nocodb`|
| `-c "..."`   | SQL-Befehl direkt ausführen (`-c` = Command)   |

### Interaktiver Modus

Ohne `-c` Parameter öffnet sich eine interaktive SQL-Shell:

```bash
# Interaktive PostgreSQL-Shell öffnen
docker compose exec database-server psql -U nocodb -d nocodb

# In der Shell können dann SQL-Befehle eingegeben werden:
nocodb=# SELECT COUNT(*) FROM nc_audit_v2;
nocodb=# \dt           -- Alle Tabellen anzeigen
nocodb=# \q            -- Shell beenden
```

### Nützliche psql-Befehle

| Befehl       | Beschreibung                    |
| ------------ | ------------------------------- |
| `\dt`        | Alle Tabellen auflisten         |
| `\dt nc_*`   | Alle NocoDB-Tabellen auflisten  |
| `\d tabelle` | Tabellenstruktur anzeigen       |
| `\x`         | Erweiterte Ausgabe ein/aus      |
| `\q`         | psql beenden                    |
| `\?`         | Hilfe anzeigen                  |

## Bereinigung durchführen

### Option 1: Nur Audit-Tabelle (empfohlen)

Bereinigt nur die Tabelle, die bei `NC_DISABLE_AUDIT=true` nicht mehr genutzt wird:

```sql
-- NocoDB Audit-Tabelle bereinigen
-- Führe diesen Befehl in der NocoDB-Datenbank aus

TRUNCATE TABLE nc_audit_v2;
```

### Option 2: Alle Log-Tabellen bereinigen

Bereinigt alle Log-/Audit-Tabellen für einen kompletten Neustart:

```sql
-- Alle NocoDB Log-Tabellen bereinigen
-- ACHTUNG: Entfernt ALLE historischen Logs!

BEGIN;

-- Hauptaudit-Log
TRUNCATE TABLE nc_audit_v2;

-- Webhook-Logs (optional)
TRUNCATE TABLE nc_hook_logs_v2;

-- Sync-Logs (optional)
TRUNCATE TABLE nc_sync_logs_v2;

-- Automation-Logs (optional, falls Tabelle existiert)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'nc_automation_executions') THEN
        EXECUTE 'TRUNCATE TABLE nc_automation_executions';
    END IF;
END $$;

COMMIT;
```

### Option 3: Einzeiler für schnelle Bereinigung

```sql
TRUNCATE TABLE nc_audit_v2, nc_hook_logs_v2, nc_sync_logs_v2;
```

## Ausführung mit Docker

### Variante A: Über docker exec

```bash
# Container-Name anpassen (z.B. db_crm_app_bauer-group_com_DATABASE)
CONTAINER_NAME="${STACK_NAME}_DATABASE"

# Nur Audit-Tabelle
docker exec -it $CONTAINER_NAME psql -U nocodb -d nocodb -c "TRUNCATE TABLE nc_audit_v2;"

# Alle Log-Tabellen
docker exec -it $CONTAINER_NAME psql -U nocodb -d nocodb -c "TRUNCATE TABLE nc_audit_v2, nc_hook_logs_v2, nc_sync_logs_v2;"
```

### Variante B: Über docker compose

```bash
# Im NocoDB-Projektverzeichnis

# Nur Audit-Tabelle
docker compose exec database-server psql -U nocodb -d nocodb -c "TRUNCATE TABLE nc_audit_v2;"

# Alle Log-Tabellen
docker compose exec database-server psql -U nocodb -d nocodb -c "TRUNCATE TABLE nc_audit_v2, nc_hook_logs_v2, nc_sync_logs_v2;"
```

## Verifizierung

Nach der Bereinigung prüfen:

```sql
-- Anzahl der Einträge prüfen (sollte 0 sein)
SELECT
    'nc_audit_v2' AS table_name, COUNT(*) AS row_count FROM nc_audit_v2
UNION ALL
SELECT
    'nc_hook_logs_v2', COUNT(*) FROM nc_hook_logs_v2
UNION ALL
SELECT
    'nc_sync_logs_v2', COUNT(*) FROM nc_sync_logs_v2;
```

## Problembehebung bei Upgrades

Falls Migrations-Fehler wie `nc_054_id_length` auftreten:

```sql
-- Prüfen ob problematische Indizes existieren
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'nc_audit_v2';

-- Falls Index-Konflikte bestehen, vor dem Upgrade:
BEGIN;
TRUNCATE TABLE nc_audit_v2;
-- Index entfernen falls nötig
DROP INDEX IF EXISTS nc_audit_v2_project_id_index;
DROP INDEX IF EXISTS nc_audit_v2_base_id_index;
COMMIT;
```

## Automatische regelmäßige Bereinigung (optional)

Falls Audit temporär aktiviert wird, kann ein Cronjob alte Einträge bereinigen:

```sql
-- Einträge älter als 30 Tage löschen
DELETE FROM nc_audit_v2 WHERE created_at < NOW() - INTERVAL '30 days';
DELETE FROM nc_hook_logs_v2 WHERE created_at < NOW() - INTERVAL '30 days';
```

## Fix: AuditMigration Fehler "nc_audit_v2_old does not exist"

Nach Bereinigung der Audit-Tabellen kann NocoDB beim Start wiederholt diesen Fehler ausgeben:

```text
[AuditMigration] Error running audit migration
error: relation "nc_audit_v2_old" does not exist
```

**Ursache:** NocoDB versucht Daten aus einer alten Migrations-Tabelle zu migrieren, die nicht (mehr) existiert. Dies ist ein Bug - die Migration prüft nicht, ob die Tabelle vorhanden ist.

**Lösung:** Leere Dummy-Tabelle erstellen, damit die Migration erfolgreich abschließt:

```bash
docker compose exec database-server psql -U nocodb -d nocodb -c "
CREATE TABLE IF NOT EXISTS nc_audit_v2_old (
    id VARCHAR(20) PRIMARY KEY,
    op_type VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);"
```

Nach NocoDB-Neustart wird die Migration 0 Zeilen finden und erfolgreich abschließen. Die leere Tabelle kann danach optional gelöscht werden:

```bash
docker compose exec database-server psql -U nocodb -d nocodb -c "DROP TABLE IF EXISTS nc_audit_v2_old;"
```

## Diagnose: Datenbank 100% CPU

Wenn die PostgreSQL-Datenbank hohe CPU-Last verursacht, helfen diese Diagnose-Queries.

### Aktive Queries anzeigen

Zeigt alle laufenden Queries mit Laufzeit - hilfreich um lang laufende oder blockierte Operationen zu finden:

```sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS runtime,
    query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY runtime DESC;
```

| Spalte | Bedeutung |
|--------|-----------|
| `pid` | Prozess-ID (zum Beenden mit `pg_terminate_backend(pid)`) |
| `state` | `active` = läuft, `idle in transaction` = wartet in Transaktion |
| `wait_event_type` | `Lock` = wartet auf Sperre, `Client` = wartet auf Client |
| `runtime` | Wie lange die Query bereits läuft |

### Blockierte Queries finden

Prüft ob Queries durch andere blockiert werden - sehr häufige Ursache für hohe CPU:

```sql
SELECT
    a.pid               AS blocked_pid,
    a.query             AS blocked_query,
    b.pid               AS blocking_pid,
    b.query             AS blocking_query,
    now() - a.query_start AS blocked_runtime
FROM pg_stat_activity a
JOIN pg_locks l1 ON l1.pid = a.pid AND NOT l1.granted
JOIN pg_locks l2
     ON l1.locktype = l2.locktype
    AND l1.database IS NOT DISTINCT FROM l2.database
    AND l1.relation IS NOT DISTINCT FROM l2.relation
    AND l1.page IS NOT DISTINCT FROM l2.page
    AND l1.tuple IS NOT DISTINCT FROM l2.tuple
    AND l1.transactionid IS NOT DISTINCT FROM l2.transactionid
    AND l1.classid IS NOT DISTINCT FROM l2.classid
    AND l1.objid IS NOT DISTINCT FROM l2.objid
    AND l1.objsubid IS NOT DISTINCT FROM l2.objsubid
JOIN pg_stat_activity b ON b.pid = l2.pid
WHERE l2.granted;
```

| Spalte | Bedeutung |
|--------|-----------|
| `blocked_pid` | PID der blockierten Query |
| `blocked_query` | Die wartende Query |
| `blocking_pid` | PID der blockierenden Query |
| `blocking_query` | Die Query, die andere blockiert |
| `blocked_runtime` | Wie lange bereits blockiert |

### Blockierende Query beenden

Falls eine Query andere blockiert und beendet werden soll:

```sql
-- Sanft beenden (SIGTERM)
SELECT pg_cancel_backend(blocking_pid);

-- Erzwungen beenden (SIGKILL) - nur wenn pg_cancel nicht hilft
SELECT pg_terminate_backend(blocking_pid);
```

**Achtung:** `pg_terminate_backend` beendet die gesamte Verbindung sofort!

## Referenzen

- [NocoDB Audit Dokumentation](https://docs.nocodb.com/0.109.7/setup-and-usages/audit/)
- [NC_DISABLE_AUDIT Implementation (PR #5137)](https://github.com/nocodb/nocodb/pull/5137)
- [NocoDB Environment Variables](https://nocodb.com/docs/self-hosting/environment-variables)

---

**Erstellt:** 2025-01-25
**Für:** NocoDB mit PostgreSQL-Backend
