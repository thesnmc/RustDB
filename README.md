# TheSNMC RustDB

TheSNMC RustDB is a self-hosted lifecycle engine where data "rusts" over time unless accessed.

It ingests files and records, tracks heat/fidelity, applies staged transforms, and eventually deletes/purges stale artifacts to control storage growth.

## Why RustDB

- Automatic storage pressure management
- Policy-driven decay timeline
- Type-aware transforms (images, text, spreadsheets, docs, binaries)
- Recoverability window without permanent full-fidelity retention
- Local-first deployment (no managed service required)

## Quickstart

### Windows (fastest)

```powershell
.\start_local.ps1
```

`start_local.ps1` is one-command bootstrap:

- auto-detects Python (`py` or `python`)
- creates `.venv` on first run
- installs/updates dependencies from `requirements.txt`
- launches the API at `127.0.0.1:8080`

Open `http://127.0.0.1:8080/admin` and use API key `devkey`.

### Docker stack

```bash
docker compose up --build
```

Open `http://127.0.0.1:8081/admin` and use API key `devkey`.

## Lifecycle model

Objects move through stages:

- `0 Hot` - original fidelity
- `1 Warm` - first transform
- `2 Cold` - stronger transform
- `4 Purged` - artifacts physically removed

### Tick behavior (important)

- `Run Tick` in the dashboard now runs in **force mode**:
  - it advances objects without waiting for wall-clock `next_decay_at`
  - this is intentional for easy manual testing/demos
- per-upload `Decay speed` still applies:
  - `1.0x` -> one tick usually advances one stage
  - `0.5x` -> roughly two ticks per stage
  - `2.0x` -> can advance with progress headroom
- background scheduler continues to run with normal time-based behavior

## Deletion and purge model (important)

RustDB runs in single-copy mode:

- each stage keeps only the latest active artifact
- old intermediate artifacts are removed as decay advances
- delete stage purges physical files immediately

This maximizes storage savings and minimizes artifact buildup.

## Supported file types and decay behavior

| Type | Detection | Stage 1 | Stage 2 |
|---|---|---|---|
| Images | `png/jpg/jpeg/webp/gif` | JPEG compression | Aggressive JPEG + resize |
| Text | `txt/md/log/json` | Summary text artifact | Further lifecycle decay |
| Spreadsheet | `csv/xlsx/xls/xlsm` | Summary snapshot | Compact summary artifact |
| Documents | `pdf/doc/docx/ppt/pptx` | Safe summary fallback | Further compact summary/metadata |
| Binary/other | fallback | gzip | metadata-only artifact |

Storage location:

- default: `rustdb_storage/`
- override: `RUSTDB_STORAGE_DIR`

## Upload toggle: keep original for restore

During upload you can enable:

- `Keep original for full restore window`

If enabled:

- RustDB preserves the original file path for the configured `restore_window_sec`
- restore within window can return original-format quality
- other generated artifacts still decay/purge normally
- in forced manual ticking, delete stage purges original immediately for predictable testing

If disabled:

- RustDB stays in strict single-copy mode and purges aggressively

## Dashboard usage

1. Open `http://127.0.0.1:8080/admin`
2. Dashboard auto-detects backend and auto-loads existing objects
3. Upload file with `Upload Data`
   - policy is selected automatically by file type
   - file input resets after successful upload
4. Run decay with `Run Tick` (forced manual progression)
5. Manage rows with:
   - `View Data`
   - `Rename`
   - `Delete`
   - `Purge Now` (immediate file/artifact removal)
   - `Restore` (available only if an artifact still exists)
6. Inspect object history in "Inspect One Object"

### Why connection settings exist

Most users can ignore connection settings and use defaults on localhost.

Advanced settings are for:

- running API on a different host/port
- using a different API key/tenant mapping
- connecting to remote/self-hosted RustDB instances in team environments

## View Data behavior

`View Data` opens current payload in a new tab:

- file payload -> streams file content
- text payload -> plain text preview
- deleted object -> returns `object_deleted` until restored

It always reflects the **current** stage artifact, not necessarily the original file.

## API endpoints

- `GET /healthz`
- `PUT /rot/policies`
- `GET /rot/policies`
- `GET /objects`
- `POST /objects`
- `POST /upload`
- `POST /ingest`
- `GET /objects/{id}`
- `GET /objects/{id}/file`
- `POST /objects/{id}/rename`
- `POST /objects/{id}/delete`
- `POST /rot/run`
- `GET /rot/state/{id}`
- `POST /rot/restore/{id}`
- `POST /rot/control/{id}`
- `GET /rot/metrics`
- `GET /metrics`

OpenAPI: `openapi.yaml`

## Auth and tenancy

- all non-health routes require API key
- header: `X-API-Key`
- key mapping: `RUSTDB_API_KEYS` (default includes `devkey:default`)
- objects/policies/metrics are tenant-scoped

### API key customization (self-hosted users)

You do not need to pre-provision keys in code. Users customize keys at deploy/runtime using env vars.

Format:

```text
RUSTDB_API_KEYS=key1:tenant_a,key2:tenant_b
```

Examples:

- single tenant:
  - `RUSTDB_API_KEYS=mysecretkey:default`
- multi-tenant:
  - `RUSTDB_API_KEYS=clientAkey:tenant_a,clientBkey:tenant_b,opskey:ops`

Windows PowerShell example:

```powershell
$env:RUSTDB_API_KEYS="mysecretkey:default"
.\start_local.ps1
```

Docker Compose example:

```yaml
environment:
  RUSTDB_API_KEYS: mysecretkey:default,teamkey:team_a
```

Client request example:

```bash
curl -H "X-API-Key: mysecretkey" http://127.0.0.1:8080/objects
```

## Environment

See `.env.example`.

Primary variables:

- `RUSTDB_PG_DSN`
- `RUSTDB_API_KEYS`
- `RUSTDB_TENANT`
- `RUSTDB_TICK_INTERVAL_SEC`
- `RUSTDB_SHADOW_MODE`
- `RUSTDB_STORAGE_DIR`

Legacy `DECAYDB_*` names are supported for compatibility.

## Verification

```bash
python -m unittest discover -s tests -v
python scripts/smoke_test.py
```

## Troubleshooting

- `backend not reachable`
  - restart and refresh: `Ctrl+C` -> `.\start_local.ps1` -> `Ctrl+F5`
- `unauthorized`
  - wrong API key; use `devkey` in local default setup
- `View Data shows text`
  - expected if current stage payload is a summary/metadata artifact
- deleted row still visible
  - uncheck "Show deleted rows" or run refresh
- `Keep Original column shows no when checked`
  - restart server so latest API shape is loaded
  - verify with fresh upload after restart
- `manual tick needs multiple clicks unexpectedly`
  - check selected `Decay speed` (for `0.5x`, two ticks per stage is expected)

