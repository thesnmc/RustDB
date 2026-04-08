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
- `3 Deleted` - tombstoned
- `4 Purged` - artifacts physically removed

`Run Tick` advances eligible objects by one stage.

## Restore model (important)

Each policy includes `restore_window_sec`:

- restore **within window**: can return full-quality origin
- restore **after window**: degraded restore only (best available artifact)

This keeps short-term safety but preserves long-term storage savings.

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

## Dashboard usage

1. Connect (`Auto Detect Backend` -> `Test Connection`)
2. Create default policy once
3. Upload file with `Upload Data`
4. Run decay with `Run Tick`
5. Manage rows with:
   - `View Data`
   - `Rename`
   - `Delete`
   - `Restore`
6. Inspect object history in "Inspect One Object"

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

## GitHub release files

- `LICENSE`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `openapi.yaml`
