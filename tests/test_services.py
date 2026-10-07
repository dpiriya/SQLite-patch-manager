import sqlite3

from services.comparison import compare_databases
from services.merge import merge_databases


def _database(path, statements):
    with sqlite3.connect(path) as connection:
        connection.executescript(statements)


def test_comparison_reports_schema_and_row_changes(tmp_path):
    patch = tmp_path / "patch.db"
    base = tmp_path / "base.db"
    _database(patch, """
        CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT, note TEXT);
        INSERT INTO items VALUES (1, 'updated', 'new column');
        INSERT INTO items VALUES (3, 'added', 'new row');
        CREATE TABLE patch_only (id INTEGER PRIMARY KEY);
        INSERT INTO patch_only VALUES (10);
    """)
    _database(base, """
        CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT, old_note TEXT);
        INSERT INTO items VALUES (1, 'original', 'legacy');
        INSERT INTO items VALUES (2, 'deleted', 'legacy');
        CREATE TABLE base_only (id INTEGER PRIMARY KEY);
        INSERT INTO base_only VALUES (20);
    """)

    report = compare_databases(patch, base)

    assert report["tables_added"] == ["patch_only"]
    assert report["tables_deleted"] == ["base_only"]
    assert report["stats"]["columns_added"] == 2
    assert report["stats"]["columns_deleted"] == 2
    assert report["stats"]["rows_added"] == 2
    assert report["stats"]["rows_changed"] == 1
    assert report["stats"]["rows_deleted"] == 2
    assert report["row_changes"]["patch_only"]["added"][0]["key"] == [10]
    assert report["row_changes"]["base_only"]["deleted"][0]["key"] == [20]


def test_tables_without_primary_keys_are_not_row_mergeable(tmp_path):
    patch = tmp_path / "patch.db"
    base = tmp_path / "base.db"
    _database(patch, "CREATE TABLE items (value TEXT); INSERT INTO items VALUES ('patch');")
    _database(base, "CREATE TABLE items (value TEXT); INSERT INTO items VALUES ('base');")

    report = compare_databases(patch, base)

    assert report["row_changes"]["items"]["supported"] is False
    assert report["stats"]["rows_added"] == 0


def test_nullable_composite_primary_keys_are_not_row_mergeable(tmp_path):
    patch = tmp_path / "patch.db"
    base = tmp_path / "base.db"
    _database(patch, "CREATE TABLE items (part TEXT, id INTEGER, PRIMARY KEY (part, id)); INSERT INTO items VALUES (NULL, 1);")
    _database(base, "CREATE TABLE items (part TEXT, id INTEGER, PRIMARY KEY (part, id));")

    report = compare_databases(patch, base)

    assert report["row_changes"]["items"]["supported"] is False


def test_merge_updates_a_copy_and_keeps_base_unchanged(tmp_path):
    patch = tmp_path / "patch.db"
    base = tmp_path / "base.db"
    output = tmp_path / "merged.db"
    _database(patch, """
        CREATE TABLE items (id INTEGER PRIMARY KEY, value TEXT);
        INSERT INTO items VALUES (1, 'patch');
        INSERT INTO items VALUES (2, 'added');
    """)
    _database(base, """
        CREATE TABLE items (id INTEGER PRIMARY KEY, value TEXT);
        INSERT INTO items VALUES (1, 'base');
        INSERT INTO items VALUES (3, 'base-only');
    """)

    merge_databases(
        patch, base, output,
        apply_structure=False,
        apply_updates=True,
        apply_deletions=False,
    )

    with sqlite3.connect(base) as connection:
        assert connection.execute("SELECT value FROM items WHERE id = 1").fetchone()[0] == "base"
        assert connection.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2
    with sqlite3.connect(output) as connection:
        assert connection.execute("SELECT value FROM items WHERE id = 1").fetchone()[0] == "patch"
        assert connection.execute("SELECT value FROM items WHERE id = 2").fetchone()[0] == "added"
        assert connection.execute("SELECT value FROM items WHERE id = 3").fetchone()[0] == "base-only"
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_merge_deletions_and_structure_option(tmp_path):
    patch = tmp_path / "patch.db"
    base = tmp_path / "base.db"
    output = tmp_path / "merged.db"
    _database(patch, """
        CREATE TABLE items (id INTEGER PRIMARY KEY, value TEXT, extra TEXT DEFAULT 'x');
        INSERT INTO items (id, value) VALUES (1, 'keep');
        CREATE TABLE patch_only (id INTEGER PRIMARY KEY);
        CREATE INDEX idx_patch_only_id ON patch_only (id);
    """)
    _database(base, """
        CREATE TABLE items (id INTEGER PRIMARY KEY, value TEXT, obsolete TEXT);
        INSERT INTO items VALUES (1, 'old', 'remove');
        INSERT INTO items VALUES (2, 'delete', 'remove');
        CREATE TABLE base_only (id INTEGER PRIMARY KEY);
    """)

    merge_databases(
        patch, base, output,
        apply_structure=True,
        apply_updates=True,
        apply_deletions=True,
    )

    with sqlite3.connect(output) as connection:
        assert {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )} == {"items", "patch_only"}
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_patch_only_id'"
        ).fetchone() == (1,)
        assert connection.execute("SELECT id, value, extra FROM items").fetchall() == [(1, "keep", "x")]
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
