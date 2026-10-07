# Project Instructions

- Keep this project offline-first and compatible with Windows.
- Use Flask for the local UI and Python's built-in `sqlite3` for database access.
- Never modify uploaded Patch or Base databases; merge into a separate copy of Base.
- Open comparison inputs read-only, quote SQLite identifiers, and parameterize values.
- Row changes require matching primary keys; do not guess row matches for tables without them.
- Keep merge operations transactional and fail clearly on unsupported or invalid schema changes.
- Add focused tests with temporary SQLite databases for behavior changes.
- Keep upload handling local-only and validate SQLite integrity before processing.
