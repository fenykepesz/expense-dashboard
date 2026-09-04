"""
PDF to JSON Converter for Bank Leumi Credit Card Statements.

Parses Bank Leumi Mastercard/Visa PDF statements and converts them
to the dashboard-compatible JSON format with automatic categorization.

Usage:
    python pdf_to_json.py statement.pdf -o expenses.json
"""

import argparse
import re
import os
import sys
from collections import Counter
from pathlib import Path

# Ensure tools/ directory is on import path regardless of working directory
sys.path.insert(0, str(Path(__file__).parent))

try:
    import pdfplumber
except ImportError:
    print("Error: pdfplumber is required. Install with: pip install pdfplumber")
    exit(1)

from utils import (
    __version__,
    load_category_rules,
    categorize_merchant,
    parse_date,
    get_month_name,
    get_year,
    run_interactive_categorization,
    save_expenses_json,
    save_to_db,
    print_summary,
)


def fix_hebrew_text(text):
    """
    Fix Hebrew text that was extracted in reversed order from PDF.

    Bank Leumi PDFs store Hebrew text with characters in reversed order.
    This function reverses strings that contain Hebrew characters to correct
    the display order.

    Mixed Hebrew/English text is handled by reversing only the segments
    that contain Hebrew characters.
    """
    if not text:
        return text

    # Check if text contains Hebrew characters
    has_hebrew = any('\u0590' <= char <= '\u05FF' for char in text)

    if not has_hebrew:
        return text

    # For Bank Leumi PDFs, the entire text line is reversed character by character
    # Simply reverse the string to get the correct order
    return text[::-1]


def extract_transactions(pdf_path):
    """
    Extract transactions from a Bank Leumi PDF statement.
    Returns a list of raw transaction dictionaries.

    Installment continuation rows are a special case, found via real user
    data: Bank Leumi always prints the ORIGINAL purchase date on every
    monthly installment line, never the date the money is actually charged
    this cycle. Confirmed against a real statement labeled "לתקופה: ספטמבר
    2026" (period: September 2026) whose own regular (non-installment)
    transactions were ALL dated in August — Bank Leumi names a statement by
    its billing/due month, not the spending month it covers, so a
    "September" statement's real transactions land in August. An
    installment row in that same file should be dated the same way: same
    spending month as its file's own regular transactions, not its own
    printed (much older) purchase date and not the statement's own label
    either. That target month is derived here from whichever (year, month)
    is most common among the file's regular rows — never guessed from the
    Hebrew period label, which is one month off in the wrong direction.
    """
    transactions = []

    # Pattern to match regular/foreign transaction lines
    # Format: charge_amount type original_amount merchant date
    # Example: 10.00 הליגר הקסע 10.00 קסויקה 28/11/25
    # Transaction types can appear in multiple formats due to PDF extraction inconsistencies:
    # Regular: הליגר הקסע / הקסע רגילה
    # Foreign: ל"וח לקייס / ל"חו לקייס
    regular_pattern = re.compile(
        r'(-?[\d,]+\.?\d*)\s+'         # Charge amount (can be negative for refunds)
        r'(?:הליגר הקסע|ל"וח לקייס|הקסע רגילה|ל"חו לקייס)\s+'  # Transaction type (non-installment)
        r'([\d,]+\.?\d*)\s+'           # Original amount
        r'(.+?)\s+'                     # Merchant name
        r'(\d{2}/\d{2}/\d{2})'         # Date DD/MM/YY
    )

    # Pattern to match installment transaction lines
    # Format: charge_amount type1 type2 original_amount merchant date
    # Installment format has TWO transaction type strings
    # Example: 105.00 םימולשתב הקסע הליגר םימולשת תקסע 1,260.00 ספוש!הלאוו 03/02/25
    installment_pattern = re.compile(
        r'(-?[\d,]+\.?\d*)\s+'         # Charge amount (monthly payment)
        r'(?:םימולשתב הקסע|הליגר םימולשת תקסע)\s+'  # First transaction type
        r'(?:םימולשתב הקסע|הליגר םימולשת תקסע)\s+'  # Second transaction type (yes, both!)
        r'([\d,]+\.?\d*)\s+'           # Original total amount
        r'(.+?)\s+'                     # Merchant name
        r'(\d{2}/\d{2}/\d{2})'         # Date DD/MM/YY
    )

    # The "payment N of M" continuation line that follows an installment
    # row, e.g. raw (un-reversed) ".2 - מ 2 - םולשת" -> "תשלום - 2 מ - .2"
    # ("payment 2 of 2"). Numbers are already left-to-right in the raw
    # extraction (only Hebrew letter runs get reversed), and the TOTAL
    # appears first in raw reading order, current payment number second.
    installment_count_pattern = re.compile(r'\.?(\d+)\s*-\s*מ\s+(\d+)\s*-\s*םולשת')

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            # Split into lines and process each
            lines = text.split('\n')
            for i, line in enumerate(lines):
                # Skip header lines and totals
                if 'בויח םוכס' in line or 'כ"הס' in line:
                    continue

                # Try to match regular transaction pattern first
                is_installment = False
                match = regular_pattern.search(line)
                if not match:
                    # Try installment pattern
                    match = installment_pattern.search(line)
                    is_installment = match is not None

                if match:
                    charge_amount = match.group(1).replace(',', '')
                    merchant = fix_hebrew_text(match.group(3).strip())
                    date_str = match.group(4)

                    # Skip zero or negative amounts (card fees and refunds)
                    try:
                        amount = float(charge_amount)
                        if amount <= 0:
                            continue  # Skip: 0.00 (waived fees) and negative (refunds/credits)
                    except ValueError:
                        continue

                    tx = {'raw_date': date_str, 'merchant': merchant, 'amount': amount}

                    if is_installment:
                        tx['is_installment'] = True
                        # The "payment N of M" detail usually sits on the
                        # very next extracted line.
                        count_match = (
                            installment_count_pattern.search(lines[i + 1])
                            if i + 1 < len(lines) else None
                        )
                        if count_match:
                            total, current = int(count_match.group(1)), int(count_match.group(2))
                            tx['installment'] = (current, total)

                    transactions.append(tx)

    # Re-date installment rows to the same spending month this file's own
    # regular transactions fall in (see docstring above) — computed from
    # whichever (year, month) is most common among the regular rows, since
    # that's ground truth already correctly parsed from the same statement.
    regular_months = []
    for t in transactions:
        if t.get('is_installment'):
            continue
        iso = parse_date(t['raw_date'])
        if iso:
            regular_months.append(iso[:7])
    if regular_months:
        dominant_ym = Counter(regular_months).most_common(1)[0][0]
        for t in transactions:
            if t.get('is_installment'):
                t['billing_date'] = f"{dominant_ym}-01"

    return transactions


def extract_card_number(pdf_path):
    """Extract card last 4 digits from PDF."""
    with pdfplumber.open(pdf_path) as pdf:
        text = pdf.pages[0].extract_text() if pdf.pages else ""

        # Look for card number in title (e.g., "9334 דראקרטסמ ימואל סיטרכל")
        match = re.search(r'(\d{4})\s+דראקרטסמ|(\d{4})\s+הזיו', text)
        if match:
            return match.group(1) or match.group(2)

    return "0000"


def convert_pdf_to_json(pdf_path, output_path=None, rules_path=None, interactive=False):
    """
    Main conversion function.

    Args:
        pdf_path: Path to the Bank Leumi PDF statement
        output_path: Output JSON file path (optional)
        rules_path: Path to category rules JSON (optional)
        interactive: Enable interactive categorization for unknown merchants (optional)

    Returns:
        List of converted expense dictionaries
    """
    # Load category rules
    rules = load_category_rules(rules_path)

    # Pre-process rules for case-insensitive matching
    rules_lower = {k.lower(): v for k, v in rules.items()}

    # Extract card number
    card = extract_card_number(pdf_path)

    # Extract raw transactions
    raw_transactions = extract_transactions(pdf_path)

    # Convert to dashboard format
    expenses = []
    skipped_count = 0

    for tx in raw_transactions:
        # Installment continuation rows use the re-derived billing month
        # (see extract_transactions' docstring) instead of their own
        # printed original-purchase date.
        iso_date = tx.get('billing_date') or parse_date(tx['raw_date'])
        if not iso_date:
            print(f"Warning: Skipping transaction with invalid date '{tx['raw_date']}' from merchant: {tx['merchant']}")
            skipped_count += 1
            continue

        category = categorize_merchant(tx['merchant'], rules_lower)
        installment = ''
        if tx.get('installment'):
            current, total = tx['installment']
            installment = f"{current}/{total}"

        expense = {
            "date": iso_date,
            "merchant": tx['merchant'],
            "amount": tx['amount'],
            "category": category,
            "month": get_month_name(iso_date),
            "year": get_year(iso_date),
            "card": card,
            "installment": installment,
        }
        expenses.append(expense)

    # Interactive categorization for uncategorized merchants
    if interactive:
        run_interactive_categorization(expenses, rules, rules_lower, rules_path)

    # Sort by date descending
    expenses.sort(key=lambda x: x['date'], reverse=True)

    # Save to file if output path provided
    if output_path:
        save_expenses_json(expenses, output_path)

    if skipped_count > 0:
        print(f"Note: Skipped {skipped_count} transaction(s) with invalid dates")

    return expenses


def main():
    parser = argparse.ArgumentParser(
        description="Convert Bank Leumi PDF statements to dashboard JSON format."
    )
    parser.add_argument("pdf", help="Path to the PDF statement file")
    parser.add_argument("-o", "--output", default="expenses_converted.json",
                        help="Output JSON file path (default: expenses_converted.json)")
    parser.add_argument("-r", "--rules", default=None,
                        help="Path to category rules JSON (default: tools/category_rules.json)")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="Enable interactive categorization for unknown merchants")
    parser.add_argument("--db", default=None,
                        help="SQLite database path to write transactions into (e.g., expenses.db)")
    parser.add_argument("--version", action="version", version=f"pdf_to_json {__version__}")

    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        print(f"Error: PDF file not found: {args.pdf}")
        return

    # When --db is given without -o, skip JSON output
    output_path = args.output if not args.db else None

    expenses = convert_pdf_to_json(args.pdf, output_path, args.rules, args.interactive)

    if args.db:
        save_to_db(expenses, args.db)

    print_summary(expenses)


if __name__ == "__main__":
    main()
