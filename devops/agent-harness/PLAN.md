# Forge DevOps implementation plan

Goal: Jira-inspired local projects, issues, Kanban, sprints and release tracking operated from both browser and CLI-Anything.

Architecture: Python HTTP API and SQLite transactional domain store, static frontend, independently installable Click CLI calling the same live HTTP API. One-shot commands, JSON output and REPL. Data persists outside the checkout. Codex uses the real CLI through a discoverable skill; the page does not pretend to host an LLM.

Scope: single-user loopback service; projects, issue fields/filters/comments/audit, sprint lifecycle, release records with completion gates. No hosted Jira connection, external CI deployment or multi-user authentication in this version.

1. Write domain and HTTP/installed-CLI workflow tests: persistence, validation, concurrent numbering, sprint/project boundaries, release gates, malformed requests and local browser access protections.
2. Implement SQLite store and shared API; never execute user-supplied shell text.
3. Implement Click command groups and installed CLI-to-API tests.
4. Implement board, list, detail/editor, sprint and release views, audit and Codex guide; verify via browser interactions and CLI round trip.
5. Install to persistent local venv, add reusable Codex skill, launch local service, seed explicitly marked demo project through CLI, hand over verified URL and actual task IDs.

Reference: https://www.atlassian.com/software/jira/features and https://www.atlassian.com/software/jira/features/scrum-boards
