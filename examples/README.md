# Sample databases

Use these files to try the upload and comparison flow:

- `sample_patch.sqlite` as **Patch database**
- `sample_base.sqlite` as **Base database**

The pair exercises added/changed/deleted tables, added/deleted/changed columns, row additions/updates/deletions, a composite primary key, an added index, and a table without a primary key. The keyless table is marked unsupported for row-level changes.

Expected high-level differences before merging:

- Tables: 1 added, 2 changed, 1 deleted.
- Rows: 4 added, 2 changed, 4 deleted; keyless-table rows are excluded from row counts.
- The `staging_notes` table is flagged because it has no primary key.

Regenerate both fixtures with:

```powershell
.\.venv\Scripts\python.exe examples\create_sample_databases.py
```
