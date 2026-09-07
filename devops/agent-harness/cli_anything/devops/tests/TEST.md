# Test plan

- test_core.py: persistence across Store instances, strict fields/enums, per-project issue numbers under concurrent creates, issue comments/audit, project isolation, optimistic concurrency, sprint lifecycle and one-active-sprint constraint, releases blocked by unfinished work.
- test_full_e2e.py: real ephemeral HTTP server and installed CLI command: project → sprint → issue → transition → comment → release → report; CLI writes read through HTTP and vice versa; JSON errors and nonzero exit; cross-origin POST, hostile Host, malformed JSON and request bounds rejected.
- Browser acceptance: create/edit an issue; move it on board; filter; add comment; create project/sprint/release; switch projects; read CLI-created ticket. Demo data is labeled, never asserted to be real production activity.

Tests use independent temporary SQLite paths and server ports; no test alters the user's live database. No external services or credentials required.

## Verified 2026-09-07

- Python: 24 passed, including installed-CLI HTTP roundtrip, version edits, empty-link rejection, whitespace normalization and published-version immutability.
- Node: 1 passed. The actual refresh function is tested with delayed responses while switching projects; an obsolete response cannot switch back to the previous project.
- Browser: project creation/switching, issue creation/edit/status/comment/search, sprint creation, version creation/edit with CLI readback, and CLI changes visible in issue detail. DEMO-13 records the actual browser/CLI acceptance flow; APP is a separate empty working project. Drag gestures were not separately browser-automated; status changes were verified through the detail selector and CLI.
- Runtime: persisted SQLite data survives restart; the forge-devops process runs under PM2. REPL health command returns the live service result.

## Management analytics extension · 2026-09-07

- 32 Python tests and 4 Node tests pass. New cases cover project/sprint isolation, active vs planned/empty scopes, null denominators, overdue and soon-due boundaries, missing owners/zero points/stale fields, workload totals, project-level release gates, and real installed CLI-to-browser metric consistency with no audit mutation.
- Frontend regressions cover report-scope selection (including constructor/toString/__proto__), risk filtering, zero values and HTML escaping.
- Browser verification: project, active iteration and planned iteration scope changes; empty iteration percentages; risk filtering and task-detail drilldown; original board's six new project summary indicators. The live database was only queried during this extension; no iteration or work item was changed.
