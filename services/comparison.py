from __future__ import annotations

import base64
import sqlite3
from pathlib import Path
from typing import Any


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def open_readonly(path: str | Path) -> sqlite3.Connection:
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _tables(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return {row["name"]: row["sql"] or "" for row in rows}


def _columns(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    rows = connection.execute(f"PRAGMA table_info({_quote(table)})")
    return [dict(row) for row in rows]


def _display(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"binary_base64": base64.b64encode(value).decode("ascii")}
    return value


def _key_columns(columns: list[dict[str, Any]]) -> list[str]:
    return [column["name"] for column in sorted(columns, key=lambda item: item["pk"]) if column["pk"]]


def _column_signature(column: dict[str, Any]) -> tuple[Any, ...]:
    return (
        column["type"].strip().upper(),
        column["notnull"],
        column["dflt_value"],
        column["pk"],
    )


def _read_rows(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(f"SELECT * FROM {_quote(table)}")]


def compare_databases(patch_path: str | Path, base_path: str | Path) -> dict[str, Any]:
    with open_readonly(patch_path) as patch, open_readonly(base_path) as base:
        patch_tables = _tables(patch)
        base_tables = _tables(base)
        patch_names = set(patch_tables)
        base_names = set(base_tables)
        tables_added = sorted(patch_names - base_names)
        tables_deleted = sorted(base_names - patch_names)
        schema_tables: list[dict[str, Any]] = []
        row_changes: dict[str, dict[str, Any]] = {}
        column_added_count = 0
        column_deleted_count = 0
        column_changed_count = 0
        changed_table_count = 0
        rows_added = 0
        rows_changed = 0
        rows_deleted = 0

        for table in tables_added:
            patch_columns = _columns(patch, table)
            added_columns = [column["name"] for column in patch_columns]
            column_added_count += len(added_columns)
            schema_tables.append({
                "name": table,
                "added_columns": added_columns,
                "deleted_columns": [],
                "changed_columns": [],
                "definition_changed": False,
            })
            keys = _key_columns(patch_columns)
            if keys:
                patch_rows = _read_rows(patch, table)
                keyed_rows = {tuple(row[key] for key in keys): row for row in patch_rows}
                if len(keyed_rows) == len(patch_rows) and all(all(value is not None for value in key) for key in keyed_rows):
                    added_rows = [
                        {"key": [_display(value) for value in key], "after": {name: _display(row.get(name)) for name in added_columns}}
                        for key, row in keyed_rows.items()
                    ]
                    row_changes[table] = {
                        "supported": True,
                        "reason": None,
                        "primary_key": keys,
                        "added": added_rows,
                        "changed": [],
                        "deleted": [],
                    }
                    rows_added += len(added_rows)
                else:
                    row_changes[table] = {
                        "supported": False,
                        "reason": "Primary-key values must be unique and non-null for row-level comparison.",
                        "primary_key": keys,
                        "added": [],
                        "changed": [],
                        "deleted": [],
                    }
            else:
                row_changes[table] = {
                    "supported": False,
                    "reason": "A primary key is required for row-level comparison.",
                    "primary_key": [],
                    "added": [],
                    "changed": [],
                    "deleted": [],
                }
        for table in tables_deleted:
            base_columns = _columns(base, table)
            deleted_columns = [column["name"] for column in base_columns]
            column_deleted_count += len(deleted_columns)
            schema_tables.append({
                "name": table,
                "added_columns": [],
                "deleted_columns": deleted_columns,
                "changed_columns": [],
                "definition_changed": False,
            })
            keys = _key_columns(base_columns)
            if keys:
                base_rows = _read_rows(base, table)
                keyed_rows = {tuple(row[key] for key in keys): row for row in base_rows}
                if len(keyed_rows) == len(base_rows) and all(all(value is not None for value in key) for key in keyed_rows):
                    deleted_rows = [
                        {"key": [_display(value) for value in key], "before": {name: _display(row.get(name)) for name in deleted_columns}}
                        for key, row in keyed_rows.items()
                    ]
                    row_changes[table] = {
                        "supported": True,
                        "reason": None,
                        "primary_key": keys,
                        "added": [],
                        "changed": [],
                        "deleted": deleted_rows,
                    }
                    rows_deleted += len(deleted_rows)
                else:
                    row_changes[table] = {
                        "supported": False,
                        "reason": "Primary-key values must be unique and non-null for row-level comparison.",
                        "primary_key": keys,
                        "added": [],
                        "changed": [],
                        "deleted": [],
                    }
            else:
                row_changes[table] = {
                    "supported": False,
                    "reason": "A primary key is required for row-level comparison.",
                    "primary_key": [],
                    "added": [],
                    "changed": [],
                    "deleted": [],
                }

        for table in sorted(patch_names & base_names):
            patch_columns = _columns(patch, table)
            base_columns = _columns(base, table)
            patch_by_name = {column["name"]: column for column in patch_columns}
            base_by_name = {column["name"]: column for column in base_columns}
            added_columns = [name for name in patch_by_name if name not in base_by_name]
            deleted_columns = [name for name in base_by_name if name not in patch_by_name]
            changed_columns = [
                name
                for name in patch_by_name.keys() & base_by_name.keys()
                if _column_signature(patch_by_name[name]) != _column_signature(base_by_name[name])
            ]
            added_columns.sort()
            deleted_columns.sort()
            changed_columns.sort()
            column_added_count += len(added_columns)
            column_deleted_count += len(deleted_columns)
            column_changed_count += len(changed_columns)
            sql_changed = " ".join(patch_tables[table].split()) != " ".join(base_tables[table].split())
            if added_columns or deleted_columns or changed_columns or sql_changed:
                changed_table_count += 1
            schema_tables.append({
                "name": table,
                "added_columns": added_columns,
                "deleted_columns": deleted_columns,
                "changed_columns": changed_columns,
                "definition_changed": sql_changed,
            })

            patch_keys = _key_columns(patch_columns)
            base_keys = _key_columns(base_columns)
            if not patch_keys or patch_keys != base_keys or any(key not in base_by_name for key in patch_keys):
                row_changes[table] = {
                    "supported": False,
                    "reason": "Matching primary keys are required for row-level comparison.",
                    "primary_key": patch_keys,
                    "added": [],
                    "changed": [],
                    "deleted": [],
                }
                continue

            patch_rows = _read_rows(patch, table)
            base_rows = _read_rows(base, table)
            patch_by_key = {tuple(row[key] for key in patch_keys): row for row in patch_rows}
            base_by_key = {tuple(row[key] for key in patch_keys): row for row in base_rows}
            if (
                len(patch_by_key) != len(patch_rows)
                or len(base_by_key) != len(base_rows)
                or any(value is None for key in patch_by_key for value in key)
                or any(value is None for key in base_by_key for value in key)
            ):
                row_changes[table] = {
                    "supported": False,
                    "reason": "Primary-key values must be unique and non-null for row-level comparison.",
                    "primary_key": patch_keys,
                    "added": [],
                    "changed": [],
                    "deleted": [],
                }
                continue
            common_columns = [name for name in patch_by_name if name in base_by_name]
            added_rows = []
            changed_rows = []
            deleted_rows = []

            for key, patch_row in patch_by_key.items():
                display_key = [_display(value) for value in key]
                base_row = base_by_key.get(key)
                if base_row is None:
                    added_rows.append({"key": display_key, "after": {name: _display(patch_row.get(name)) for name in common_columns}})
                    continue
                changed_fields = [
                    name for name in common_columns
                    if patch_row.get(name) != base_row.get(name)
                ]
                if changed_fields:
                    changed_rows.append({
                        "key": display_key,
                        "fields": changed_fields,
                        "before": {name: _display(base_row.get(name)) for name in common_columns},
                        "after": {name: _display(patch_row.get(name)) for name in common_columns},
                    })

            for key, base_row in base_by_key.items():
                if key not in patch_by_key:
                    deleted_rows.append({
                        "key": [_display(value) for value in key],
                        "before": {name: _display(base_row.get(name)) for name in common_columns},
                    })

            added_rows.sort(key=lambda item: repr(item["key"]))
            changed_rows.sort(key=lambda item: repr(item["key"]))
            deleted_rows.sort(key=lambda item: repr(item["key"]))
            row_changes[table] = {
                "supported": True,
                "reason": None,
                "primary_key": patch_keys,
                "added": added_rows,
                "changed": changed_rows,
                "deleted": deleted_rows,
            }
            rows_added += len(added_rows)
            rows_changed += len(changed_rows)
            rows_deleted += len(deleted_rows)

        return {
            "tables_added": tables_added,
            "tables_deleted": tables_deleted,
            "schema_tables": schema_tables,
            "row_changes": row_changes,
            "stats": {
                "tables_added": len(tables_added),
                "tables_deleted": len(tables_deleted),
                "tables_changed": changed_table_count,
                "columns_added": column_added_count,
                "columns_deleted": column_deleted_count,
                "columns_changed": column_changed_count,
                "rows_added": rows_added,
                "rows_changed": rows_changed,
                "rows_deleted": rows_deleted,
            },
        }
