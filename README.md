# 🚀 RustDB
> A self-hosted lifecycle engine where data intentionally "rusts" over time unless accessed, automatically controlling storage growth by degrading and purging stale artifacts.

[![License](https://img.shields.io/badge/License-TheSNMC-blue.svg)](LICENSE)

## 📖 Overview
TheSNMC RustDB is a self-hosted lifecycle engine that ingests files and records, tracks their heat/fidelity, and applies staged transformations over time. Rather than keeping every uploaded file at full 100% fidelity forever, RustDB lets unaccessed data "decay." 

It moves data through stages—from high-resolution originals to compressed versions, then to metadata summaries, and eventually into total physical deletion.

**The Core Mandate:** Automatic storage pressure management. By running in a strict single-copy mode and intelligently degrading files based on their type, RustDB maximizes storage savings and minimizes artifact buildup without relying on a managed cloud service.

## ✨ Key Features
* **Automatic Storage Pressure Management:** Prevents infinite disk growth by physically purging stale artifacts and intermediate states.
* **Type-Aware Transforms:** Intelligently degrades files (images, text, spreadsheets, docs, binaries) based on their specific formats.
* **Policy-Driven Decay Timeline:** Configurable ticking behavior controls how fast objects decay, with options for manual forced progression.
* **Recoverability Window:** Optional toggle during upload to keep the original file for a full restore window without permanent full-fidelity retention.
* **Local-First Deployment:** Completely self-hosted with no managed service required.

## 🛠️ Tech Stack
* **Language:** Python
* **Deployment Environment:** Windows (PowerShell) / Docker
* **Storage Interface:** Local File System (`rustdb_storage/` or `RUSTDB_STORAGE_DIR`)
* **API Interface:** OpenAPI-compliant REST API

## ⚙️ Architecture & Data Flow
RustDB operates on a strict single-copy progression model. Each stage keeps only the latest active artifact, and old intermediate artifacts are removed as decay advances.

### Lifecycle Stages
Objects move through the following stages:
* **0 Hot** - Original fidelity
* **1 Warm** - First transform (e.g., JPEG compression)
* **2 Cold** - Stronger transform (e.g., Aggressive JPEG + resize)
* **4 Purged** - Artifacts physically removed from disk

### Supported File Types and Decay Behavior

| Type Detection | Stage 1 | Stage 2 |
| :--- | :--- | :--- |
| **Images** (`png/jpg/jpeg/webp/gif`) | JPEG compression | Aggressive JPEG + resize |
| **Text** (`txt/md/log/json`) | Summary text artifact | Further lifecycle decay |
| **Spreadsheet** (`csv/xlsx/xls/xlsm`) | Summary snapshot | Compact summary artifact |
| **Documents** (`pdf/doc/docx/ppt/pptx`) | Safe summary fallback | Further compact summary/metadata |
| **Binary/other** | fallback gzip | metadata-only artifact |

### Tick Behavior (Progression Logic)
* **Background Scheduler:** Runs normal time-based behavior based on wall-clock `next_decay_at`.
* **Manual Tick** (Run Tick in dashboard): Runs in force mode. It advances objects without waiting for the wall-clock time (intentional for easy testing/demos).
* **Decay Speed:** Per-upload modifiers apply (1.0x = 1 tick usually advances 1 stage; 0.5x = roughly 2 ticks per stage; 2.0x = can advance with progress headroom).

### Upload Toggle: Keep Original for Restore
During upload, you can enable: *Keep original for full restore window.*
* **If enabled:** Preserves the original file path for the configured `restore_window_sec`. Restores within this window return original-format quality. Other generated artifacts still decay normally.
* **If disabled:** RustDB stays in strict single-copy mode and purges aggressively immediately.

## 🔒 Privacy & Data Sovereignty
* **Data Sovereignty:** All processing and storage happens locally. No cloud sync.
* **Auth & Tenancy:** All non-health routes require an API key via the `X-API-Key` header. Objects, policies, and metrics are tenant-scoped.
* **Storage Location:** Default is `rustdb_storage/`, but can be overridden via `RUSTDB_STORAGE_DIR`.

## 🚀 Getting Started

### Prerequisites
* Python (`py` or `python`) for Windows bootstrap.
* Docker and Docker Compose for containerized deployment.

### Installation

#### Option A: Windows (Fastest)
`start_local.ps1` is a one-command bootstrap that auto-detects Python, creates a `.venv` on first run, installs dependencies from `requirements.txt`, and launches the API.

```powershell
.\start_local.ps1
```
Open `http://127.0.0.1:8080/admin` and use API key `devkey`.

#### Option B: Docker Stack
```bash
docker compose up --build
```
Open `http://127.0.0.1:8081/admin` and use API key `devkey`.

### Verification
To verify the engine is running correctly, run the test suites:
```bash
python -m unittest discover -s tests -v
python scripts/smoke_test.py
```

## 🎛️ Dashboard Usage
Open `http://127.0.0.1:8080/admin` (or `8081` for Docker).
The Dashboard auto-detects the backend and auto-loads existing objects.

* **Upload** a file with *Upload Data* (policy is selected automatically by file type).
* **Run decay** with *Run Tick* (forced manual progression).
* **Manage rows with:**
  * **View Data:** Opens current payload in a new tab (streams file, plain text preview, or returns `object_deleted`). It always reflects the current stage artifact.
  * **Rename**
  * **Delete**
  * **Purge Now:** Immediate file/artifact removal.
  * **Restore:** Available only if an artifact still exists.
* **Inspect** object history using *Inspect One Object*.

*Note: Advanced connection settings in the dashboard are only necessary if running the API on a different host/port, using a different API key/tenant, or connecting to a remote instance.*

## 🔌 API & Configuration

### API Endpoints (OpenAPI: `openapi.yaml`)
* `GET /healthz`
* `PUT /rot/policies`
* `GET /rot/policies`
* `GET /objects`
* `POST /objects`
* `POST /upload`
* `POST /ingest`
* `GET /objects/{id}`
* `GET /objects/{id}/file`
* `POST /objects/{id}/rename`
* `POST /objects/{id}/delete`
* `POST /rot/run`
* `GET /rot/state/{id}`
* `POST /rot/restore/{id}`
* `POST /rot/control/{id}`
* `GET /rot/metrics`
* `GET /metrics`

### Environment Variables
See `.env.example` for full list. Primary variables include:
* `RUSTDB_PG_DSN`
* `RUSTDB_API_KEYS`
* `RUSTDB_TENANT`
* `RUSTDB_TICK_INTERVAL_SEC`
* `RUSTDB_SHADOW_MODE`
* `RUSTDB_STORAGE_DIR`

*(Legacy `DECAYDB_*` names are supported for compatibility).*

### API Key Customization (Self-Hosted Users)
Users customize keys at deploy/runtime using env vars. Format: `RUSTDB_API_KEYS=key1:tenant_a,key2:tenant_b`

**Windows PowerShell example:**
```powershell
$env:RUSTDB_API_KEYS="mysecretkey:default"
.\start_local.ps1
```

**Docker Compose example:**
```yaml
environment:
  RUSTDB_API_KEYS: mysecretkey:default,teamkey:team_a
```

**Client Request example:**
```bash
curl -H "X-API-Key: mysecretkey" [http://127.0.0.1:8080/objects](http://127.0.0.1:8080/objects)
```

## 🛠️ Troubleshooting
* **`backend not reachable`**
  Restart and refresh: `Ctrl+C` -> `.\start_local.ps1` -> `Ctrl+F5`
* **`unauthorized`**
  Wrong API key; use `devkey` in local default setup.
* **`View Data` shows text**
  Expected if the current stage payload is a summary/metadata artifact.
* **Deleted row still visible**
  Uncheck "Show deleted rows" or run refresh.
* **`Keep Original` column shows "no" when checked**
  Restart the server so the latest API shape is loaded; verify with a fresh upload after restart.
* **Manual tick needs multiple clicks unexpectedly**
  Check the selected Decay speed (for `0.5x`, two ticks per stage is expected).

## 🤝 Contributing
Contributions, issues, and feature requests are welcome. Feel free to check the issues page if you want to contribute.

## 📄 License
see the LICENSE file for details.
