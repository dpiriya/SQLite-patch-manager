from pathlib import Path
import sqlite3


OUTPUT_DIR = Path(__file__).resolve().parent


def create_database(path: Path, statements: str) -> None:
    path.unlink(missing_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(statements)


def main() -> None:
    base_path = OUTPUT_DIR / "sample_base.sqlite"
    patch_path = OUTPUT_DIR / "sample_patch.sqlite"

    create_database(base_path, """
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            legacy_code TEXT
        );
        INSERT INTO customers VALUES (1, 'Avery Morgan', 'avery@example.test', 'L-100');
        INSERT INTO customers VALUES (2, 'Blair Chen', 'blair@example.test', 'L-200');
        INSERT INTO customers VALUES (3, 'Casey Patel', 'casey@example.test', 'L-300');

        CREATE TABLE orders (
            order_id INTEGER NOT NULL,
            line_no INTEGER NOT NULL,
            sku TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            total INTEGER NOT NULL,
            PRIMARY KEY (order_id, line_no)
        );
        CREATE INDEX idx_orders_sku ON orders (sku);
        INSERT INTO orders VALUES (100, 1, 'MUG-01', 2, 48);
        INSERT INTO orders VALUES (100, 2, 'TEA-04', 1, 16);
        INSERT INTO orders VALUES (101, 1, 'BOOK-09', 1, 32);

        CREATE TABLE staging_notes (note TEXT, owner TEXT);
        INSERT INTO staging_notes VALUES ('Review address', 'Avery');
        INSERT INTO staging_notes VALUES ('Check tax code', 'Blair');

        CREATE TABLE legacy_imports (
            id INTEGER PRIMARY KEY,
            source_file TEXT NOT NULL
        );
        INSERT INTO legacy_imports VALUES (1, 'import-2023.csv');
        INSERT INTO legacy_imports VALUES (2, 'import-2024.csv');
    """)

    create_database(patch_path, """
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            loyalty_tier TEXT NOT NULL DEFAULT 'standard'
        );
        INSERT INTO customers VALUES (1, 'Avery Morgan', 'avery.morgan@example.test', 'gold');
        INSERT INTO customers VALUES (2, 'Blair Chen', 'blair@example.test', 'silver');
        INSERT INTO customers VALUES (4, 'Devon Reed', 'devon@example.test', 'standard');

        CREATE TABLE orders (
            order_id INTEGER NOT NULL,
            line_no INTEGER NOT NULL,
            sku TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            total REAL NOT NULL,
            PRIMARY KEY (order_id, line_no)
        );
        CREATE INDEX idx_orders_sku ON orders (sku);
        INSERT INTO orders VALUES (100, 1, 'MUG-01', 2, 52.50);
        INSERT INTO orders VALUES (100, 2, 'TEA-04', 1, 16.00);
        INSERT INTO orders VALUES (102, 1, 'BOOK-12', 1, 28.00);

        CREATE TABLE staging_notes (note TEXT, owner TEXT);
        INSERT INTO staging_notes VALUES ('Review address', 'Avery');
        INSERT INTO staging_notes VALUES ('Archive tax note', 'Blair');

        CREATE TABLE review_flags (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            reason TEXT NOT NULL
        );
        INSERT INTO review_flags VALUES (1, 2, 'Confirm billing address');
        INSERT INTO review_flags VALUES (2, 4, 'Verify new account');
    """)

    print(f"Created Base:  {base_path}")
    print(f"Created Patch: {patch_path}")


if __name__ == "__main__":
    main()
