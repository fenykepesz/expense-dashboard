"""
Excel to JSON Converter for Bank Leumi Credit Card Statements.

Parses Bank Leumi "Excel" exports (.xls files that are actually HTML tables)
containing all cards' expenses and converts them to the dashboard-compatible
JSON format with automatic categorization.

Usage:
    python excel_to_json.py statement.xls -o expenses.json
    python excel_to_json.py statement.xls -o expenses.json -i
    python excel_to_json.py statement.xls -o expenses.json --usd-rate 3.65
"""

import argparse
import os
import sys
import re
from html.parser import HTMLParser
from pathlib import Path

# Ensure tools/ directory is on import path regardless of working directory
sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    load_category_rules,
    categorize_merchant,
    parse_date,
    get_month_name,
    get_year,
    run_interactive_categorization,
    save_expenses_json,
    print_summary,
)


# Section headers in Bank Leumi exports
ILS_SECTION_HEADER = 'עסקאות בש"ח במועד החיוב'
FOREIGN_SECTION_HEADER = 'עסקאות מחויבות במט"ח'

# Summary row keywords to skip
SUMMARY_KEYWORDS = ["סה\"כ", "סה״כ", "סך הכל", "total"]


class BankLeumiHTMLParser(HTMLParser):
    """
    Parse Bank Leumi HTML-formatted .xls exports.

    Extracts transaction rows from the ILS and foreign currency tables.
    The file contains nested tables — metadata tables are skipped,
    and only transaction data tables (identified by section headers) are processed.
    """

    def __init__(self):
        super().__init__()
        self.transactions = []
        self.current_section = None  # 'ils' or 'foreign'
        self.in_header_row = False
        self.in_td = False
        self.in_bold = False
        self.current_row = []
        self.current_cell_text = ""
        self.header_row_seen = False
        self.row_is_header = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == 'tr':
            self.current_row = []
            self.current_cell_text = ""
            # Header rows have bgcolor attribute
            self.row_is_header = 'bgcolor' in attrs_dict

        elif tag == 'td':
            self.in_td = True
            self.current_cell_text = ""
            # Check for colspan — section header cells
            colspan = attrs_dict.get('colspan', '')
            if colspan:
                self.in_bold = False  # Reset, will be set by <b> tag

        elif tag == 'b':
            self.in_bold = True

    def handle_endtag(self, tag):
        if tag == 'td':
            self.in_td = False
            self.current_row.append(self.current_cell_text.strip())
            self.current_cell_text = ""

        elif tag == 'b':
            self.in_bold = False

        elif tag == 'tr':
            if not self.current_row:
                return

            # Check if this row contains a section header
            row_text = " ".join(self.current_row)

            if ILS_SECTION_HEADER in row_text:
                self.current_section = 'ils'
                self.header_row_seen = False
                return

            if FOREIGN_SECTION_HEADER in row_text:
                self.current_section = 'foreign'
                self.header_row_seen = False
                return

            # Skip if not in a transaction section
            if self.current_section is None:
                return

            # Skip the column header row (first row after section header)
            if self.row_is_header:
                self.header_row_seen = True
                return

            # Skip rows before we've seen the header
            if not self.header_row_seen:
                return

            # Process data rows (need at least 6 columns for card, date, merchant, amount, currency, charge)
            if len(self.current_row) >= 6:
                self._process_data_row(self.current_row)

        elif tag == 'table':
            # Reset section when table closes
            if self.current_section is not None:
                self.current_section = None
                self.header_row_seen = False

    def handle_data(self, data):
        if self.in_td:
            self.current_cell_text += data

    def _process_data_row(self, cells):
        """Process a single data row from a transaction table."""
        card = cells[0].strip()
        date_str = cells[1].strip()
        merchant = cells[2].strip()
        currency = cells[4].strip()
        charge_str = cells[5].strip()

        # Skip empty rows
        if not card or not date_str or not merchant:
            return

        # Skip summary/total rows
        for keyword in SUMMARY_KEYWORDS:
            if keyword in merchant:
                return

        self.transactions.append({
            'card': card,
            'date_str': date_str,
            'merchant': merchant,
            'charge_str': charge_str,
            'currency': currency,
            'section': self.current_section,
        })


def extract_transactions_from_html(file_path):
    """
    Parse the Bank Leumi HTML file and extract raw transaction data.

    Args:
        file_path: Path to the .xls (HTML) file.

    Returns:
        List of raw transaction dicts from the parser.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    parser = BankLeumiHTMLParser()
    parser.feed(content)
    return parser.transactions


def parse_amount(raw_value):
    """
    Parse an amount string from the HTML cell.

    Handles formats like: "269", "1,234.56", "27.9"
    Returns float or None if unparseable.
    """
    cleaned = raw_value.replace(",", "").replace("₪", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_card_digits(raw_value):
    """
    Extract last 4 card digits from cell value.
    Returns "0000" if no 4-digit number found.
    """
    match = re.search(r'(\d{4})', raw_value.strip())
    if match:
        return match.group(1)
    return "0000"


def convert_excel_to_json(excel_path, output_path=None, rules_path=None,
                          interactive=False, exchange_rates=None):
    """
    Main conversion function.

    Args:
        excel_path:     Path to the Bank Leumi .xls export
        output_path:    Output JSON file path (optional)
        rules_path:     Path to category rules JSON (optional)
        interactive:    Enable interactive categorization for unknown merchants
        exchange_rates: Dict mapping currency code to ILS rate (e.g., {"USD": 3.65})

    Returns:
        List of converted expense dictionaries.
    """
    if exchange_rates is None:
        exchange_rates = {}

    # Load category rules
    rules = load_category_rules(rules_path)
    rules_lower = {k.lower(): v for k, v in rules.items()}

    # Extract raw transactions from HTML
    raw_transactions = extract_transactions_from_html(excel_path)
    print(f"[OK] Parsed {len(raw_transactions)} raw transaction rows")

    # Convert to dashboard format
    expenses = []
    skipped_count = 0
    skipped_foreign = 0

    for tx in raw_transactions:
        # Parse date
        iso_date = parse_date(tx['date_str'])
        if iso_date is None:
            print(f"Warning: Skipping transaction with unparseable date: {tx['date_str']} ({tx['merchant']})")
            skipped_count += 1
            continue

        # Parse charge amount
        amount = parse_amount(tx['charge_str'])
        if amount is None:
            skipped_count += 1
            continue

        # Skip zero or negative amounts (waived fees, refunds)
        if amount <= 0:
            continue

        # Handle foreign currency conversion
        currency = tx['currency'].upper()
        if currency != 'ILS':
            if currency in exchange_rates:
                amount = round(amount * exchange_rates[currency], 2)
            else:
                skipped_foreign += 1
                continue

        # Extract card digits
        card = extract_card_digits(tx['card'])

        # Categorize merchant
        category = categorize_merchant(tx['merchant'], rules_lower)

        expense = {
            "date": iso_date,
            "merchant": tx['merchant'],
            "amount": amount,
            "category": category,
            "month": get_month_name(iso_date),
            "year": get_year(iso_date),
            "card": card,
        }
        expenses.append(expense)

    # Interactive categorization
    if interactive:
        run_interactive_categorization(expenses, rules, rules_lower, rules_path)

    # Sort by date descending
    expenses.sort(key=lambda x: x['date'], reverse=True)

    # Save to file
    if output_path:
        save_expenses_json(expenses, output_path)

    # Print warnings
    if skipped_count > 0:
        print(f"Note: Skipped {skipped_count} row(s) with invalid data")
    if skipped_foreign > 0:
        print(f"Note: Skipped {skipped_foreign} foreign currency transaction(s) (no exchange rate provided)")
        print("  Use --usd-rate, --eur-rate, --gbp-rate to include them")

    return expenses


def main():
    parser = argparse.ArgumentParser(
        description="Convert Bank Leumi Excel exports to dashboard JSON format."
    )
    parser.add_argument("excel", help="Path to the Excel (.xls) statement file")
    parser.add_argument("-o", "--output", default="expenses_converted.json",
                        help="Output JSON file path (default: expenses_converted.json)")
    parser.add_argument("-r", "--rules", default=None,
                        help="Path to category rules JSON (default: tools/category_rules.json)")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="Enable interactive categorization for unknown merchants")
    parser.add_argument("--usd-rate", type=float, default=None,
                        help="USD to ILS exchange rate (e.g., 3.65)")
    parser.add_argument("--eur-rate", type=float, default=None,
                        help="EUR to ILS exchange rate (e.g., 3.92)")
    parser.add_argument("--gbp-rate", type=float, default=None,
                        help="GBP to ILS exchange rate (e.g., 4.55)")

    args = parser.parse_args()

    if not os.path.exists(args.excel):
        print(f"Error: File not found: {args.excel}")
        return

    # Build exchange rates dict from CLI arguments
    exchange_rates = {}
    if args.usd_rate:
        exchange_rates["USD"] = args.usd_rate
    if args.eur_rate:
        exchange_rates["EUR"] = args.eur_rate
    if args.gbp_rate:
        exchange_rates["GBP"] = args.gbp_rate

    expenses = convert_excel_to_json(
        args.excel, args.output, args.rules, args.interactive, exchange_rates
    )
    print_summary(expenses)


if __name__ == "__main__":
    main()
