# My SQLite Patch Manager: Implementation Plan

## Current status
- [x] Workspace created; implementation plan saved.
- [x] Flask upload, comparison dashboard, change browser, and row detail views scaffolded.
- [x] SQLite schema/row comparison and transactional merge services implemented.
- [x] Temporary-database tests authored; static diagnostics report no issues.
- [x] Offline Windows build script and portable launcher added.
- [ ] Execute tests and build the Windows bundle on a machine with Python installed.

## Goal
Build an offline, single-user Flask application for Windows that compares a Patch SQLite database with a Base SQLite database, previews differences, applies configured changes to a copy of Base, and downloads the merged database. Package the finished app for USB use with its runtime and dependencies bundled.

## Confirmed decisions
- Patch is the database whose changes flow into Base.
- Keep the uploaded originals unchanged; merge into a copy of Base.
- Provide separate controls for schema changes, row updates, and row deletions. Row additions are included with row changes.
- Match rows by declared primary key. Tables without a primary key are reported and excluded from row-level merge.
- Run locally for one user, offline, without installation or internet access; final Windows package includes the runtime.
- Do not infer table or column renames.

## Implementation steps
1. Establish the Flask project structure, dependency list, Windows local launcher, and temporary upload/output storage.
2. Validate uploaded SQLite files, inspect schemas, compare table/column structure, and report schema mismatches.
3. Compare rows by primary key; report added, changed, and deleted rows and mark tables without primary keys as unsupported for row changes.
4. Build the upload flow, CRUD/schema dashboard, change filters, wildcard table search, configurable pagination, and highlighted table/row inspection.
5. Add configurable merge options, preview/confirmation, and a transactional merge into a copy of Base. Recompute dashboard counts and offer the merged file for download.
6. Test schema and row comparisons, merge options, original-file preservation, and merged database integrity using temporary databases.
7. Document local development and build a portable Windows bundle that launches the Flask server on loopback without internet access.

## Proposed structure
- `app.py`: Flask routes and request/session orchestration.
- `services/comparison.py`: database validation, schema inspection, and row comparison.
- `services/merge.py`: merge planning and transactional updates to a Base copy.
- `templates/` and `static/`: upload, dashboard, change browser, and row grid.
- `tests/`: focused temporary SQLite database tests.
- `requirements.txt`, `README.md`, Windows launch/package configuration.

## Acceptance criteria
- User can upload Patch and Base databases and see schema and CRUD comparison statistics.
- User can filter and paginate tables, inspect table changes, and see changed rows highlighted by change type.
- User can choose enabled merge categories, apply them to a Base copy, see refreshed statistics, and download a valid SQLite database.
- Invalid/corrupt uploads and unsupported primary-key cases are clearly reported; the original uploads are never modified.
- The app and its tests run locally; the packaged app starts offline on Windows from USB.
