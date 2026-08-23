"""
Shared utilities for expense conversion tools.

Provides common functions for date parsing, category management,
and interactive categorization used by both PDF and Excel converters.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

__version__ = "1.28.1"


def load_category_rules(rules_path=None):
    """Load category mapping rules from JSON file."""
    if rules_path is None:
        rules_path = Path(__file__).parent / "category_rules.json"

    try:
        with open(rules_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: Category rules file not found at {rules_path}")
        return {}


def save_category_rules(rules, rules_path=None):
    """Save updated category rules to JSON file."""
    if rules_path is None:
        rules_path = Path(__file__).parent / "category_rules.json"

    with open(rules_path, 'w', encoding='utf-8') as f:
        json.dump(rules, f, indent=4, ensure_ascii=False)
    print(f"[OK] Updated category rules saved to {rules_path}")


def categorize_merchant(merchant, rules):
    """
    Categorize a merchant based on keyword matching.
    Returns the category or 'Uncategorized' if no match.

    Note: rules should be pre-processed with lowercase keys for efficiency.
    """
    merchant_lower = merchant.lower()

    for keyword_lower, category in rules.items():
        if keyword_lower in merchant_lower:
            return category

    return "Uncategorized"


def parse_date(date_str):
    """
    Parse date from DD/MM/YY or DD/MM/YYYY format to ISO YYYY-MM-DD.

    Supports both 2-digit year (DD/MM/YY) from PDF exports and
    4-digit year (DD/MM/YYYY) from Excel exports.
    """
    formats = ["%d/%m/%y", "%d/%m/%Y"]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def get_month_name(date_str):
    """Get English month name from ISO date string."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%B")
    except ValueError:
        return "Unknown"


def get_year(date_str):
    """Get year integer from ISO date string."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.year
    except ValueError:
        return datetime.now().year


BUILTIN_CATEGORIES = [
    "Banking Fees",
    "Banking Services",
    "Entertainment",
    "Food Delivery",
    "General Services",
    "Groceries",
    "Healthcare",
    "Insurance",
    "Other",
    "Photography",
    "Restaurants",
    "Shopping",
    "Technology",
    "Telecommunications",
    "Transportation",
    "Uncategorized",
    "Utilities",
]


def interactive_categorize_merchant(merchant, existing_rules):
    """
    Prompt user to categorize a merchant interactively.
    Returns (category, keyword) tuple. keyword is None if skipped.
    """
    categories = sorted(BUILTIN_CATEGORIES)

    print(f"\n>> New merchant: {merchant}")
    print("Available categories:")
    for i, cat in enumerate(categories, 1):
        print(f"  {i}. {cat}")

    while True:
        try:
            choice = input("\nSelect category number (or 's' to skip): ").strip().lower()

            if choice == 's':
                return "Uncategorized", None

            category_idx = int(choice) - 1
            if 0 <= category_idx < len(categories):
                selected_category = categories[category_idx]

                print(f"\n[OK] Category: {selected_category}")
                keyword = input(f"Enter keyword to match (default: '{merchant}'): ").strip()
                if not keyword:
                    keyword = merchant

                return selected_category, keyword
            else:
                print("Invalid choice. Try again.")
        except ValueError:
            print("Invalid input. Enter a number or 's' to skip.")


def run_interactive_categorization(expenses, rules, rules_lower, rules_path=None):
    """
    Run interactive categorization loop for all uncategorized merchants.

    Mutates expenses list in place, updating categories.
    Returns dict of newly added rules (may be empty).
    """
    uncategorized_merchants = {}
    for exp in expenses:
        if exp['category'] == "Uncategorized":
            if exp['merchant'] not in uncategorized_merchants:
                uncategorized_merchants[exp['merchant']] = True

    if not uncategorized_merchants:
        return {}

    print(f"\n{'='*60}")
    print(f"Found {len(uncategorized_merchants)} uncategorized merchant(s)")
    print(f"{'='*60}")

    new_rules = {}
    for merchant in uncategorized_merchants:
        category, keyword = interactive_categorize_merchant(merchant, rules)

        if keyword:
            new_rules[keyword] = category
            rules_lower[keyword.lower()] = category

            for expense in expenses:
                if expense['merchant'] == merchant:
                    expense['category'] = category

    if new_rules:
        updated_rules = {**rules, **new_rules}
        save_category_rules(updated_rules, rules_path)
        print(f"\n[OK] Added {len(new_rules)} new categorization rule(s)")

    return new_rules


def save_expenses_json(expenses, output_path):
    """Save expense list to JSON file with UTF-8 encoding."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(expenses, f, indent=4, ensure_ascii=False)
    print(f"\n[OK] Saved {len(expenses)} transactions to {output_path}")


def save_to_db(expenses, db_path, imported_at=None):
    """Insert a list of expense dicts into a SQLite database."""
    from datetime import datetime as _dt
    ts = imported_at or _dt.now().isoformat(timespec="seconds")
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT    NOT NULL,
            merchant    TEXT    NOT NULL,
            amount      REAL    NOT NULL,
            category    TEXT    NOT NULL,
            month       TEXT    NOT NULL,
            year        INTEGER NOT NULL,
            card        TEXT    NOT NULL,
            imported_at TEXT    NOT NULL DEFAULT ''
        )
    """)
    try:
        conn.execute("ALTER TABLE transactions ADD COLUMN imported_at TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # Column already exists
    rows = [{**e, "imported_at": ts} for e in expenses]
    conn.executemany(
        "INSERT INTO transactions "
        "(date, merchant, amount, category, month, year, card, imported_at) "
        "VALUES (:date, :merchant, :amount, :category, :month, :year, :card, :imported_at)",
        rows,
    )
    conn.commit()
    conn.close()
    print(f"\n[OK] Inserted {len(expenses)} transactions into {db_path}")
    print(f"\n[OK] Inserted {len(expenses)} transactions into {db_path}")


def print_summary(expenses):
    """Print a summary of extracted expenses by category."""
    print(f"\nExtracted {len(expenses)} transactions")
    print("Categories found:")
    categories = {}
    for exp in expenses:
        cat = exp['category']
        categories[cat] = categories.get(cat, 0) + 1
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")
