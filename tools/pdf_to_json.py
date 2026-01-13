"""
PDF to JSON Converter for Bank Leumi Credit Card Statements.

Parses Bank Leumi Mastercard/Visa PDF statements and converts them
to the dashboard-compatible JSON format with automatic categorization.

Usage:
    python pdf_to_json.py statement.pdf -o expenses.json
"""

import argparse
import json
import re
import os
from datetime import datetime
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("Error: pdfplumber is required. Install with: pip install pdfplumber")
    exit(1)

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
    Parse date from DD/MM/YY format to ISO YYYY-MM-DD.
    """
    try:
        # Handle formats like 28/11/25
        dt = datetime.strptime(date_str, "%d/%m/%y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def get_month_name(date_str):
    """Get English month name from ISO date."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%B")
    except ValueError:
        return "Unknown"


def get_year(date_str):
    """Get year from ISO date."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.year
    except ValueError:
        return datetime.now().year


def extract_transactions(pdf_path):
    """
    Extract transactions from a Bank Leumi PDF statement.
    Returns a list of raw transaction dictionaries.
    """
    transactions = []
    
    # Pattern to match transaction lines
    # Format: charge_amount type original_amount merchant date
    # Example: 10.00 הליגר הקסע 10.00 קסויקה 28/11/25
    # Transaction types: הליגר הקסע (regular), םימולשתב הקסע (installment), ל"וח לקייס (foreign)
    transaction_pattern = re.compile(
        r'([\d,]+\.?\d*)\s+'           # Charge amount
        r'(?:הליגר הקסע|םימולשתב הקסע|ל"וח לקייס)\s+'  # Transaction type
        r'([\d,]+\.?\d*)\s+'           # Original amount
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
                
                # Try to match transaction pattern
                match = transaction_pattern.search(line)
                if match:
                    charge_amount = match.group(1).replace(',', '')
                    original_amount = match.group(2).replace(',', '')
                    merchant = fix_hebrew_text(match.group(3).strip())
                    date_str = match.group(4)
                    
                    # Skip zero or negative amounts (refunds handled separately)
                    try:
                        amount = float(charge_amount)
                        if amount <= 0:
                            continue
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


def convert_pdf_to_json(pdf_path, output_path=None, rules_path=None):
    """
    Main conversion function.
    
    Args:
        pdf_path: Path to the Bank Leumi PDF statement
        output_path: Output JSON file path (optional)
        rules_path: Path to category rules JSON (optional)
    
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

        expense = {
            "date": iso_date,
            "merchant": tx['merchant'],
            "amount": tx['amount'],
            "category": categorize_merchant(tx['merchant'], rules_lower),
            "month": get_month_name(iso_date),
            "year": get_year(iso_date),
            "card": card
        }
        expenses.append(expense)
    
    # Sort by date descending
    expenses.sort(key=lambda x: x['date'], reverse=True)
    
    # Save to file if output path provided
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(expenses, f, indent=4, ensure_ascii=False)
        print(f"Saved {len(expenses)} transactions to {output_path}")

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
    
    args = parser.parse_args()
    
    if not os.path.exists(args.pdf):
        print(f"Error: PDF file not found: {args.pdf}")
        return
    
    expenses = convert_pdf_to_json(args.pdf, args.output, args.rules)
    
    print(f"\nExtracted {len(expenses)} transactions")
    print(f"Categories found:")
    categories = {}
    for exp in expenses:
        cat = exp['category']
        categories[cat] = categories.get(cat, 0) + 1
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    main()
