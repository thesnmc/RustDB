# 🏗️ Architecture & Design Document: TheSNMC RustDB
**Version:** 1.0.0 | **Date:** 2026-04-23 | **Author:** Sujay

---

## 1. Executive Summary
This document outlines the architecture for TheSNMC RustDB, a self-hosted lifecycle engine designed to operate entirely on local infrastructure to permanently solve runaway storage bloat. By intentionally allowing unaccessed data to "rust" and degrade over time—moving from high-fidelity originals down to lightweight metadata summaries and eventually total physical deletion—RustDB aggressively manages storage pressure while preserving data sovereignty and eliminating dependency on managed cloud services.

## 2. Architectural Drivers
**What forces shaped this architecture?**

* **Primary Goals:** Automatic storage pressure management, strict single-copy object retention, and intelligent, type-aware data degradation over a policy-driven timeline.
* **Technical Constraints:** Must run self-hosted via standard local environments (Windows PowerShell or Docker), operate without a managed database dependency, and utilize a time-based scheduler alongside manual forced-progression overrides.
* **Non-Functional Requirements (NFRs):**
  * **Security/Privacy:** Complete local data sovereignty with no external telemetry. Multi-tenancy must be supported via easily configurable environment variables (`RUSTDB_API_KEYS`).
  * **Reliability:** Predictable decay behavior with safe generic fallbacks (gzipping) for unsupported or obscure binary file types.
  * **Performance:** Background scheduler must continuously evaluate decay timelines without blocking the primary REST API, ensuring immediate responses for upload and retrieval requests.

## 3. System Architecture (The 10,000-Foot View)
The system is decoupled into three primary operational layers, running independently but interacting through a shared local state.

* **Presentation Layer:** OpenAPI-compliant REST API serving endpoints like `/objects`, `/upload`, and `/rot/run`. A lightweight, auto-detecting web dashboard (`/admin`) acts as the primary GUI for interacting with the engine, uploading data, and visualizing current artifact states.
* **Domain Layer (The Decay Engine):** The core Python backend containing the background scheduler and forced-tick logic. It houses the Type-Detection Engine (mapping extensions to transform policies) and the Transform Engine (executing aggressive JPEG compressions, spreadsheet summations, or text extractions based on the target Stage).
* **Data/Hardware Layer:** The local file system (`RUSTDB_STORAGE_DIR`). RustDB strictly manages this directory in single-copy mode, physically overwriting or deleting old artifacts as objects progress from Stage 0 (Hot) to Stage 4 (Purged).

## 4. Design Decisions & Trade-Offs (The "Why")

* **Decision 1: Strict Single-Copy Storage Model by Default**
  * **Rationale:** To maximize storage savings and prevent artifact buildup. If we kept the original file alongside the Stage 2 summary, we would defeat the core mandate of the application.
  * **Trade-off:** Prevents full-fidelity rollback once an intermediate stage is reached. We mitigated this by introducing an optional, configurable `restore_window_sec` at upload, which preserves the original path only for a specific time window before aggressive purging resumes.

* **Decision 2: Type-Aware Transforms over Generic Compression**
  * **Rationale:** Simply zipping a file only yields marginal space savings. Intelligently extracting the summary from a `.csv` or aggressively resizing a `.jpg` yields massive context-to-size ratios, preserving the "idea" of the data while shedding the byte weight.
  * **Trade-off:** Requires maintaining specific parsing libraries for images, spreadsheets, and documents, increasing the dependency surface area.

* **Decision 3: Local-First Environment Variable Auth**
  * **Rationale:** Removing the need for a complex database-backed user management system keeps the deploy footprint tiny. Tenant mapping is handled purely via `RUSTDB_API_KEYS=key:tenant`.
  * **Trade-off:** Key rotation requires an application restart, but for self-hosted and internal team deployments, this is an acceptable friction point compared to managing a separate PostgreSQL auth database.

## 5. Data Flow & Lifecycle

* **Ingestion:** A file is posted to `/upload` or `/ingest`. The Type-Detection Engine assigns a decay policy. The original file is stored in `rustdb_storage/` at Stage 0 Hot.
* **Processing:** The background scheduler (or a forced manual tick via the dashboard) detects the object's `next_decay_at` time has passed. The engine advances the object to Stage 1 Warm or Stage 2 Cold, applying the relevant transform (e.g., resizing an image).
* **Execution/Output:** The old Stage 0 artifact is physically removed from the disk. When a user requests to View Data, the API streams the current Stage artifact. Eventually, the object hits Stage 4 Purged and all physical traces are immediately deleted from the hardware.

## 6. Security & Privacy Threat Model

* **Data at Rest:** Data is entirely isolated to `RUSTDB_STORAGE_DIR`. RustDB relies on host OS permissions to secure the directory from unauthorized local users.
* **Data in Transit:** API requests require the `X-API-Key` header. In production deployments, it is expected that this is run behind a reverse proxy (like Nginx or Traefik) handling TLS/SSL.
* **Mitigated Risks:** Multi-tenant bleed is prevented via strict `RUSTDB_TENANT` scoping. Objects, policies, and metrics are isolated to the tenant associated with the provided API key.

## 7. Future Architecture Roadmap
While the current architecture perfectly serves local-first, disk-bound environments, future iterations may look to expand the storage interface. We plan to explore abstracting the Data/Hardware Layer to support S3-compatible object storage backends. This would allow RustDB's decay engine to manage storage pressure across distributed buckets, gracefully degrading cloud blobs over time without altering the core Domain Layer logic. Additionally, we plan to implement webhook callbacks for lifecycle events so external systems can be notified when an object transitions to a new state or is completely purged.
