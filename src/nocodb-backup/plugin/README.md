# backuphelper-nocodb

NocoDB extension for the BAUER GROUP **BackupHelper** engine. It adds the two
NocoDB-specific pieces that the generic engine cannot know about, and inherits
everything else (scheduling, sha256 manifest, off-site S3, retention, encryption,
notifications, DB dump + data-file restore) from the engine core.

## What it adds

### 1. `nocodb-rest` source

Captures the NocoDB REST-API export as a single snapshot component:

- walks `GET /api/v2/meta/bases` → tables → full schema
- paginates `GET /api/v2/tables/{id}/records` (1000/page)
- downloads attachment binaries referenced by `Attachment` columns
- writes a portable, self-describing tree (`bases/<base>/tables/<table>/{schema.json,
  records.json.gz, attachments/…}` + a top-level `manifest.json`), tarred into the
  snapshot as `nocodb.tar.gz`.

Config (in `BACKUP_CONFIG_JSON`, secrets via `${VAR}`):

```json
{ "type": "nocodb-rest", "name": "nocodb",
  "api_url": "http://nocodb-server:8080",
  "token": "${NOCODB_API_TOKEN}",
  "include_records": true, "include_attachments": true, "enabled": true }
```

Skips cleanly (no component) when `enabled` is false or the token is empty — so
`BACKUP_API_EXPORT=false` is just an unset token.

### 2. `nocodb` restore command group

Mounted under the engine CLI as `backuphelper nocodb …`:

| command | what |
| --- | --- |
| `restore-schema <id>` | recreate bases + tables from the export (schema-aware: skips system/virtual/pk columns, carries Select options into `dtxp`). `--base/--table/--skip-existing/--force` |
| `restore-records <id>` | batched (100) record re-insert into existing tables, strips system fields. `--base/--table/--with-attachments/--force` |
| `restore-attachments <id>` | re-upload + relink attachments onto existing records, matched by original id (4-strategy file finder). `--base/--table/--force` |

The **generic** halves of the old bespoke restore live in the engine:

- database dump → `backuphelper restore <id> --only <db-name>`
- NocoDB data files → `backuphelper restore <id> --only <files-name>`

## Install (meta image)

```dockerfile
FROM ghcr.io/bauer-group/cs-backuphelper/backuphelper:latest
COPY plugin /opt/nocodb-plugin
RUN pip install --no-cache-dir /opt/nocodb-plugin
```

## Tests

```bash
pip install -e . pytest
PYTHONPATH=../../..:../../../../BackupHelper/src pytest
```
