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

    EVERY transaction gets a `billing_date` — the (year, month) most common
    among this same statement's own transactions, day fixed to the 1st —
    separate from `raw_date`, its own literal printed date. Two real,
    confirmed-with-the-user cases motivate always preferring billing_date as
    the transaction's primary date (`date`/`month`/`year` downstream), with
    raw_date kept only as a secondary reference field:
    1. Installment continuation rows always print the ORIGINAL purchase
       date, sometimes many months before the payment is actually charged.
    2. A single statement's own regular transactions can straddle a
       calendar-month boundary (confirmed: a card's billing cycle ran
       27/07-31/08, so its "September" statement had 4 real, non-installment
       purchases dated 31/07 alongside 28 dated in August) — those 4 belong
       to the SAME bill/billing-cycle as the rest, so they should be grouped
       and totaled with it, not siphoned off into the adjacent month.
    The target month is never guessed from the statement's own "לתקופה"
    header line either — confirmed against real data that a statement
    labeled "September" bills for AUGUST's spending (Bank Leumi names a
    statement by its due month, one month after the spending it covers), so
    parsing that label and using it directly would be exactly one month
    wrong. Instead it's derived purely from a majority vote over the file's
    own transaction dates — self-consistent, no offset convention to get
    wrong.
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

    # Every transaction gets billing_date = this file's own dominant
    # (year, month) — see docstring above. Computed across ALL rows
    # (installment included): in real data the installment/boundary rows
    # are always a small minority, so they never skew the majority vote,
    # they just correctly inherit its result.
    all_months = []
    for t in transactions:
        iso = parse_date(t['raw_date'])
        if iso:
            all_months.append(iso[:7])
    if all_months:
        dominant_ym = Counter(all_months).most_common(1)[0][0]
        for t in transactions:
            # Installment rows ALWAYS override (their own printed date is
            # untrustworthy for billing purposes regardless of month). A
            # regular row only overrides if its own real date falls
            # OUTSIDE the statement's dominant month — the rare
            # cycle-boundary case — so the vast majority of transactions,
            # already in the right month, keep their real day intact
            # instead of collapsing every date in the file to the 1st.
            if t.get('is_installment'):
                t['billing_date'] = f"{dominant_ym}-01"
                continue
            iso = parse_date(t['raw_date'])
            if iso and iso[:7] != dominant_ym:
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
        # The transaction's PRIMARY date is now its billing-cycle date (see
        # extract_transactions' docstring) — the literal printed date is
        # kept separately as transaction_date, for reference/investigation
        # only, never used for month/year grouping or totals.
        raw_iso_date = parse_date(tx['raw_date'])
        iso_date = tx.get('billing_date') or raw_iso_date
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
            "transaction_date": raw_iso_date or iso_date,
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
