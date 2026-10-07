from __future__ import annotations

import re
import shutil
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from .comparison import _columns, _quote, _tables, compare_databases

_CREATE_TABLE_NAME = re.compile(
    r'(?is)^(\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)(?:"(?:[^"]|"")*"|`[^`]*`|\[[^\]]+\]|[^\s(]+)'
)


def _create_with_name(sql: str, name: str) -> str:
    match = _CREATE_TABLE_NAME.match(sql)
    if not match:
        raise ValueError("This table definition cannot be safely rebuilt.")
    return match.group(1) + _quote(name) + sql[match.end():]


def _definition(connection: sqlite3.Connection, table: str) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row[0] or "" if row else ""


def _same_shape(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
    def signature(column: dict[str, Any]) -> tuple[Any, ...]:
        return (
            column["name"], column["type"].strip().upper(), column["notnull"],
            column["dflt_value"], column["pk"],
        )
    return [signature(item) for item in left] == [signature(item) for item in right]


def _copy_table_data(connection: sqlite3.Connection, source: str, destination: str) -> None:
    source_names = {column["name"] for column in _columns(connection, source)}
    destination_names = {column["name"] for column in _columns(connection, destination)}
    common = sorted(source_names & destination_names)
    if not common:
        return
    names = ", ".join(_quote(name) for name in common)
    connection.execute(
        f"INSERT INTO {_quote(destination)} ({names}) "
        f"SELECT {names} FROM {_quote(source)}"
    )


def _create_auxiliary_objects(connection: sqlite3.Connection, patch: sqlite3.Connection, table: str) -> None:
    objects = patch.execute(
        "SELECT sql FROM sqlite_master WHERE tbl_name = ? "
        "AND type IN ('index', 'trigger') AND sql IS NOT NULL ORDER BY type, name",
        (table,),
    )
    for row in objects:
        connection.execute(row[0])


def _rebuild_table(connection: sqlite3.Connection, patch: sqlite3.Connection, table: str) -> None:
    patch_sql = _definition(patch, table)
    if not patch_sql or patch_sql.lstrip().upper().startswith("CREATE VIRTUAL TABLE"):
        raise ValueError(f"Table '{table}' uses a definition that cannot be rebuilt safely.")
    temporary = f"_spm_rebuild_{uuid.uuid4().hex[:12]}"
    connection.execute(_create_with_name(patch_sql, temporary))
    _copy_table_data(connection, table, temporary)
    connection.execute(f"DROP TABLE {_quote(table)}")
    connection.execute(f"ALTER TABLE {_quote(temporary)} RENAME TO {_quote(table)}")
    _create_auxiliary_objects(connection, patch, table)


def _apply_structure(connection: sqlite3.Connection, patch: sqlite3.Connection) -> None:
    patch_tables = _tables(patch)
    base_tables = _tables(connection)
    for table in sorted(set(base_tables) - set(patch_tables)):
        connection.execute(f"DROP TABLE {_quote(table)}")
    for table in sorted(patch_tables):
        if table not in base_tables:
            sql = _definition(patch, table)
            if not sql:
                raise ValueError(f"Table '{table}' cannot be created from its Patch definition.")
            connection.execute(sql)
            _create_auxiliary_objects(connection, patch, table)
            continue
        if (
            not _same_shape(_columns(connection, table), _columns(patch, table))
            or " ".join(_definition(connection, table).split())
            != " ".join(_definition(patch, table).split())
        ):
            _rebuild_table(connection, patch, table)


def _apply_rows(
    connection: sqlite3.Connection,
    patch: sqlite3.Connection,
    *,
    apply_updates: bool,
    apply_deletions: bool,
) -> None:
    patch_tables = _tables(patch)
    base_tables = _tables(connection)
    for table in sorted(set(patch_tables) & set(base_tables)):
        patch_columns = _columns(patch, table)
        base_columns = _columns(connection, table)
        patch_keys = [item["name"] for item in sorted(patch_columns, key=lambda item: item["pk"]) if item["pk"]]
        base_keys = [item["name"] for item in sorted(base_columns, key=lambda item: item["pk"]) if item["pk"]]
        if not patch_keys or patch_keys != base_keys:
            continue
        patch_names = [item["name"] for item in patch_columns]
        base_names = {item["name"] for item in base_columns}
        common = [name for name in patch_names if name in base_names]
        if not common:
            continue
        patch_rows = [dict(row) for row in patch.execute(f"SELECT * FROM {_quote(table)}")]
        patch_key_values = [tuple(row.get(name) for name in patch_keys) for row in patch_rows]
        base_key_values = [
            tuple(row)
            for row in connection.execute(
                f"SELECT {', '.join(_quote(name) for name in patch_keys)} FROM {_quote(table)}"
            )
        ]
        if (
            any(value is None for key in patch_key_values + base_key_values for value in key)
            or len(set(patch_key_values)) != len(patch_key_values)
            or len(set(base_key_values)) != len(base_key_values)
        ):
            raise ValueError(
                f"Table '{table}' has null or duplicate primary-key values; row changes cannot be merged safely."
            )
        conflict = ", ".join(_quote(name) for name in patch_keys)
        insert_columns = ", ".join(_quote(name) for name in common)
        placeholders = ", ".join("?" for _ in common)
        updates = [name for name in common if name not in patch_keys]
        if updates:
            update_clause = ", ".join(
                f"{_quote(name)} = excluded.{_quote(name)}" for name in updates
            )
            upsert = (
                f"INSERT INTO {_quote(table)} ({insert_columns}) VALUES ({placeholders}) "
                f"ON CONFLICT ({conflict}) DO UPDATE SET {update_clause}"
            )
        else:
            upsert = f"INSERT OR IGNORE INTO {_quote(table)} ({insert_columns}) VALUES ({placeholders})"

        if apply_updates:
            for row in patch_rows:
                connection.execute(upsert, [row.get(name) for name in common])

        if apply_deletions:
            base_rows = connection.execute(
                f"SELECT {conflict} FROM {_quote(table)}"
            ).fetchall()
            patch_keys_set = {tuple(row.get(name) for name in patch_keys) for row in patch_rows}
            where_clause = " AND ".join(f"{_quote(name)} = ?" for name in patch_keys)
            for row in base_rows:
                key = tuple(row)
                if key not in patch_keys_set:
                    connection.execute(f"DELETE FROM {_quote(table)} WHERE {where_clause}", key)


def merge_databases(
    patch_path: str | Path,
    base_path: str | Path,
    output_path: str | Path,
    *,
    apply_structure: bool,
    apply_updates: bool,
    apply_deletions: bool,
) -> dict[str, Any]:
    patch_path = Path(patch_path).resolve()
    base_path = Path(base_path).resolve()
    output_path = Path(output_path).resolve()
    if output_path in (patch_path, base_path):
        raise ValueError("The merged output must be a new file.")
    report = compare_databases(patch_path, base_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(base_path, output_path)
    try:
        with closing(sqlite3.connect(patch_path)) as patch, closing(sqlite3.connect(output_path)) as merged:
            patch.row_factory = sqlite3.Row
            merged.row_factory = sqlite3.Row
            with merged:
                merged.execute("PRAGMA foreign_keys = OFF")
                merged.execute("BEGIN IMMEDIATE")
                if apply_structure:
                    _apply_structure(merged, patch)
                if apply_updates or apply_deletions:
                    _apply_rows(
                        merged,
                        patch,
                        apply_updates=apply_updates,
                        apply_deletions=apply_deletions,
                    )
                violations = merged.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise ValueError("The merge would leave foreign-key violations in the output database.")
        return {"output_path": str(output_path), "before": report}
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
