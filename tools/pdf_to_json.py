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

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            # Split into lines and process each
            lines = text.split('\n')
            for line in lines:
                # Skip header lines and totals
                if 'בויח םוכס' in line or 'כ"הס' in line:
                    continue

                # Try to match regular transaction pattern first
                match = regular_pattern.search(line)
                if not match:
                    # Try installment pattern
                    match = installment_pattern.search(line)

                if match:
                    charge_amount = match.group(1).replace(',', '')
                    original_amount = match.group(2).replace(',', '')
                    merchant = fix_hebrew_text(match.group(3).strip())
                    date_str = match.group(4)

                    # Skip zero or negative amounts (card fees and refunds)
                    try:
                        amount = float(charge_amount)
                        if amount <= 0:
                            continue  # Skip: 0.00 (waived fees) and negative (refunds/credits)
                    except ValueError:
                        continue

                    transactions.append({
                        'raw_date': date_str,
                        'merchant': merchant,
                        'amount': amount
                    })

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
        iso_date = parse_date(tx['raw_date'])
        if not iso_date:
            print(f"Warning: Skipping transaction with invalid date '{tx['raw_date']}' from merchant: {tx['merchant']}")
            skipped_count += 1
            continue

        category = categorize_merchant(tx['merchant'], rules_lower)

        expense = {
            "date": iso_date,
            "merchant": tx['merchant'],
            "amount": tx['amount'],
            "category": category,
            "month": get_month_name(iso_date),
            "year": get_year(iso_date),
            "card": card
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
    parser.add_argument("--version", action="version", version=f"pdf_to_json {__version__}")

    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        print(f"Error: PDF file not found: {args.pdf}")
        return

    expenses = convert_pdf_to_json(args.pdf, args.output, args.rules, args.interactive)
    print_summary(expenses)


if __name__ == "__main__":
    main()
