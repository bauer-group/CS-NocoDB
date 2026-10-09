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
  records.json.gz, attachments.json, attachments/<field>/<file>}` + a top-level
  `manifest.json`), tarred into the snapshot as `nocodb.tar.gz`.

Attachment files are named after the attachment title; a repeated title in a field
gets a numbered name (`invoice.pdf`, `invoice (2).pdf`). `attachments.json` maps each
stored attachment (its NocoDB `path`, else `url`) to its file, and the restore reads
it, so every record gets its own file back. A stored file referenced by several cells
is downloaded once. The manifest's `attachments_count` counts a table's own files.

Config (in `BACKUP_CONFIG_JSON`, secrets via `${VAR}`):

```json
{ "type": "nocodb-rest", "name": "nocodb",
  "api_url": "http://nocodb-server:8080",
  "token": "${NOCODB_API_TOKEN}",
  "include_records": true, "include_attachments": true, "enabled": true }
```

Skips cleanly (no component) when `enabled` is false or the token is empty — so
`BACKUP_API_EXPORT=false` is just an unset token.

A token NocoDB rejects fails the component (the base list is the root of the
export). Since BackupHelper 1.7.7 that ends the run in `error`: `--now` exits 1,
the alert goes out at every level and the container turns unhealthy (up to 1.7.6
the job only degraded to warning while the other components succeeded). A failed
table list, schema, records page or attachment download keeps the rest of the
export and is reported in `metadata.warnings`, so the engine degrades the job to
warning and alerts. Attachments are fetched through their signed link where
NocoDB provides one; the API token is only ever sent to `api_url`, never to an
object-storage host or a redirect target elsewhere.

### 2. `nocodb` restore command group

Mounted under the engine CLI as `backuphelper nocodb …`:

| command | what |
| --- | --- |
| `restore-schema <id>` | recreate bases + tables from the export (schema-aware: skips system/virtual/pk columns, carries Select options into `dtxp`). `--base/--table/--skip-existing/--force` |
| `restore-records <id>` | batched (100) record re-insert into existing tables, strips system fields. `--base/--table/--with-attachments/--force` |
| `restore-attachments <id>` | re-upload + relink attachments onto existing records, matched by original id. Files come from `attachments.json`; exports without it fall back to a 4-strategy file finder. `--base/--table/--force` |

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
