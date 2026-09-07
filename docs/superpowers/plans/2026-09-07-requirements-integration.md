# Requirements Integration Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for the independent UI task, and inline test-driven implementation for the closely coupled domain/import/transport work. Never delete files or push business data.

**Goal:** Make all original Changan requirements and GWT evidence available in Forge work items and boards without data loss.

**Architecture:** Immutable import snapshot plus versioned analysis overlays in the existing SQLite store. One requirement links to one normal issue. CLI and read-only MCP share the API.

**Tech Stack:** Existing Python/SQLite/stdlib HTTP, Click, MCP, vanilla JavaScript/CSS. No new runtime dependency.

**Spec:** docs/superpowers/specs/2026-09-07-requirements-integration.md

## Global Constraints

- Preserve raw fields, NULL values, full descriptions, documents, scenarios and original code archive; no business data in public Git.
- Existing DEMO/APP unchanged; no deletion, no destructive SQL, no original application scripts executed.
- Requirement review status is not issue delivery status; person-days are not SP; derived scenarios are not confirmed.
- Use parameterized SQL, escaped HTML, fixed actions, local-only same-origin guard and version conflict checks.
- Keep current installed source path; work on codex/requirements-integration in the separate Forge checkout.

### Task 1: Integrated requirement interface

Files: web/app.js, web/index.html, new web/requirements.js and web/requirements.css, tests/test_web_requirements.cjs (all beneath devops/agent-harness/cli_anything/devops/). The implementer owns only these files. Backend contract is the design document's API section, consumed verbatim.

- [ ] Write failing Node tests for source-code/system filtering, missing fields, escaping long raw descriptions and GWT, and pagination boundaries. Example: `assert.equal(ForgeRequirements.matches({requirement:{system_name:'税务',missing:['deliverable']}},{system:'税务',missing:'deliverable'}),true)`.
- [ ] Run `node --test cli_anything/devops/tests/test_web_requirements.cjs`, observe missing behavior.
- [ ] Implement pure helper/render module `ForgeRequirements`, integrate it into existing list, board and issue detail. Preserve existing ordinary issue flows. Add system/chapter/requirement-type/missing filters; reset dependent filters when project changes; every source field and scenario visible safely. Show raw provenance separately from editable analysis. Use inline forms with original versions; partial save and refresh detail, explicit errors on conflict. Offer JSON export of the source_id with overlays. 50 rows/page and 30 cards/column initially, show-more controls expose all results.
- [ ] Run all Node frontend tests. Report coverage and any cross-task assumptions without committing others' files.

### Task 2: Lossless domain and transport

Files: new requirements.py, store.py, server.py, backend.py, devops_cli.py, mcp_server.py and new tests/test_requirements.py; extend tests/test_mcp.py.

- [ ] Add tests using a 13,010-character requirement with an unknown nested field, NULL estimates, one scenario, one parsed document and an ordinary APP issue. Call `store.call('requirement.import', {'bundle': bundle})` and assert exact raw/current/initial row and document preservation through `requirement.export`; test identical retry, source change rejection and duplicate-code/foreign-scenario rollback.
- [ ] Run new tests and verify unknown-operation failures.
- [ ] Add additive schema initialized by Store; module functions invoked through Store.call's transaction. Validate all records before inserting; snapshot digest determines idempotency. Create source projects atomically, map source requirement metadata to normal issues with no long text truncation in archive, and attach lightweight summary only in lists. Implement update/get/report/export contracts; update audit without mutating source snapshot.
- [ ] Add dedicated 32 MiB import route with the same guards and JSON error handling. Leave /api/call limit 65,536 bytes. Map only requirement.import to that route in Backend.call.
- [ ] Add CLI requirement import/get/report/export/update/scenario-update, using JSON files for bulk/partial field payloads. Add MCP list_requirements(project, search='', limit=50, offset=0), get_requirement(key), get_requirement_report(project), all read-only.
- [ ] Verify real HTTP/CLI import and MCP retrieval, ordinary suites, and concurrency conflicts.

### Task 3: Source archival, deployment and acceptance

Files: new scripts/archive_changan.py, tests/test_archive_changan.py, docs/REQUIREMENTS.md; local-only archive directory beneath ~/.local/share/forge-devops/imports/.

- [ ] Test archive path validation with a ZIP containing `../escape` and duplicate entries, verify rejection before writes, and test valid UTF-8 source files are preserved with SHA256 manifest.
- [ ] Implement fixed-table MySQL snapshot export via the bundled MySQL client in one `START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY` transaction; use column discovery and JSON_OBJECT, force utf8mb4, preserve decimals as strings and timestamps as strings. Keep all original schema metadata, initial JSON and document text. Do not execute source code.
- [ ] Save archive and bundle under a new exclusive local directory; back up existing Forge DB using SQLite backup API. Import through CLI/API after domain tests pass; do not mutate live DB via one-off SQL.
- [ ] Restart only verified forge-devops PM2 process. Compare original snapshot with API export, per-project counts and original APP/DEMO API data. Browser verify both views, filter and detail; persist local acceptance summary. Run full tests and request read-only code review. Keep branch local without push.
