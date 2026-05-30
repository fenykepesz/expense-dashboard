"""
One-time migration script: load an existing expenses JSON file into SQLite.

Usage:
    python tools/migrate_to_db.py expense_data.json
    python tools/migrate_to_db.py expense_data.json --db path/to/expenses.db
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import save_to_db

DEFAULT_DB = Path(__file__).parent.parent / "expenses.db"


def main():
    parser = argparse.ArgumentParser(
        description="Migrate an existing expenses JSON file into a SQLite database."
    )
    parser.add_argument("input", help="Path to the expenses JSON file")
    parser.add_argument("--db", default=str(DEFAULT_DB),
                        help=f"SQLite database path (default: {DEFAULT_DB})")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        expenses = json.load(f)

    if not isinstance(expenses, list):
        print("Error: JSON file must contain an array of expense objects.")
        sys.exit(1)

    save_to_db(expenses, args.db, imported_at="migrated")
    print(f"[OK] Migration complete — {len(expenses)} records written to {args.db}")


if __name__ == "__main__":
    main()
