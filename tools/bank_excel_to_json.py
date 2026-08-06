"""
Excel to JSON Converter for Bank Leumi checking-account exports.

Like the credit card export, the ".xls" file is actually an HTML document.
The transactions live in a <table class="xlTable">:

    row 1:  title 'תנועות בחשבון'
    row 2:  headers: תאריך | תאריך ערך | תיאור | אסמכתא | בחובה | בזכות | היתרה בש"ח | הערה
    row 3+: data rows, newest first, dates DD/MM/YYYY, amounts like "1,234.56"

Debit (בחובה) and credit (בזכות) are separate columns — exactly one is
non-zero per row. Output amounts are signed: credit → positive income,
debit → negative expense. The running balance column becomes
balance_after. The account number (e.g. 688-23692/92) appears in the
metadata header and is returned so the UI can cross-check the target
account.

Usage:
    python bank_excel_to_json.py export.xls -o transactions.json
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import __version__

# Column order in the transactions table
COL_DATE, COL_VALUE_DATE, COL_DESC, COL_REF, COL_DEBIT, COL_CREDIT, COL_BALANCE, COL_NOTE = range(8)

HEADER_FIRST_CELL = 'תאריך'
SUMMARY_KEYWORDS = ["סה\"כ", "סה״כ", "סך הכל", "total"]

ACCOUNT_NUMBER_RE = re.compile(r'(\d{2,4}-\d{4,6}/\d{2})')


class BankLeumiAccountParser(HTMLParser):
    """Extract raw transaction rows from the xlTable of an account export."""

    def __init__(self):
        super().__init__()
        self.rows = []
        self.in_xl_table = False
        self.table_depth_in_xl = 0
        self.in_td = False
        self.current_row = []
        self.cell_text = ""
        self.full_text = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'table':
            if self.in_xl_table:
                self.table_depth_in_xl += 1
            elif 'xlTable' in (attrs_dict.get('class') or ''):
                self.in_xl_table = True
                self.table_depth_in_xl = 0
        elif tag == 'tr':
            self.current_row = []
        elif tag in ('td', 'th'):
            self.in_td = True
            self.cell_text = ""

    def handle_endtag(self, tag):
        if tag == 'table' and self.in_xl_table:
            if self.table_depth_in_xl > 0:
                self.table_depth_in_xl -= 1
            else:
                self.in_xl_table = False
        elif tag in ('td', 'th'):
            self.in_td = False
            self.current_row.append(self.cell_text.strip())
        elif tag == 'tr' and self.in_xl_table and self.current_row:
            self.rows.append(self.current_row)

    def handle_data(self, data):
        self.full_text.append(data)
        if self.in_td:
            self.cell_text += data


def parse_amount(raw):
    """'1,234.56' → 1234.56; returns None if unparseable."""
    cleaned = raw.replace(",", "").replace("₪", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_bank_date(raw):
    """DD/MM/YYYY → YYYY-MM-DD; returns None if unparseable."""
    try:
        return datetime.strptime(raw.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_bank_export(file_path):
    """Parse a Bank Leumi account export.

    Returns (transactions, account_number, skipped_count).
    Each transaction: date (ISO), description, reference, amount (signed),
    balance_after, type ('income'|'expense'), notes.
    Rows are returned oldest-first, ready for insertion.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    parser = BankLeumiAccountParser()
    parser.feed(content)

    match = ACCOUNT_NUMBER_RE.search(" ".join(parser.full_text))
    account_number = match.group(1) if match else ""

    transactions = []
    skipped = 0
    for row in parser.rows:
        if len(row) < 7:
            continue  # title row / malformed
        if row[COL_DATE] == HEADER_FIRST_CELL:
            continue  # header row
        if any(k in row[COL_DESC] for k in SUMMARY_KEYWORDS):
            continue

        # Older rows carry a '**' footnote marker instead of a booking date
        # ("transactions performed in accounts..."); their value date is real
        iso_date = parse_bank_date(row[COL_DATE]) or parse_bank_date(row[COL_VALUE_DATE])
        debit = parse_amount(row[COL_DEBIT])
        credit = parse_amount(row[COL_CREDIT])
        if iso_date is None or (debit is None and credit is None):
            skipped += 1
            continue

        debit = debit or 0.0
        credit = credit or 0.0
        amount = round(credit - debit, 2)
        balance = parse_amount(row[COL_BALANCE])
        note = row[COL_NOTE].strip() if len(row) > COL_NOTE else ""

        transactions.append({
            "date": iso_date,
            "description": row[COL_DESC].strip(),
            "reference": row[COL_REF].strip(),
            "amount": amount,
            "balance_after": balance,
            "type": "income" if amount >= 0 else "expense",
            "notes": note,
        })

    transactions.reverse()  # file is newest-first; return oldest-first
    return transactions, account_number, skipped


def verify_balance_chain(transactions):
    """Check that each running balance equals the previous one plus the
    transaction amount. Returns a list of mismatch descriptions.

    Same-day rows can be ordered arbitrarily by the bank, so mismatches
    are only reported when the chain breaks across the whole file, not
    within a same-date group.
    """
    mismatches = []
    prev_balance = None
    prev_date = None
    for t in transactions:
        if t["balance_after"] is None:
            continue
        if prev_balance is not None:
            expected = round(prev_balance + t["amount"], 2)
            if abs(expected - t["balance_after"]) > 0.01 and t["date"] != prev_date:
                mismatches.append(
                    f'{t["date"]} {t["description"]}: expected {expected}, got {t["balance_after"]}'
                )
        prev_balance = t["balance_after"]
        prev_date = t["date"]
    return mismatches


def main():
    parser = argparse.ArgumentParser(
        description="Convert a Bank Leumi account export to JSON."
    )
    parser.add_argument("excel", help="Path to the account export (.xls) file")
    parser.add_argument("-o", "--output", default=None, help="Output JSON file path")
    parser.add_argument("--version", action="version", version=f"bank_excel_to_json {__version__}")
    args = parser.parse_args()

    if not os.path.exists(args.excel):
        print(f"Error: File not found: {args.excel}")
        return

    transactions, account_number, skipped = parse_bank_export(args.excel)

    income = sum(t["amount"] for t in transactions if t["amount"] > 0)
    expense = sum(t["amount"] for t in transactions if t["amount"] < 0)
    print(f"[OK] Account {account_number or '?'}: {len(transactions)} transactions "
          f"({transactions[0]['date']} → {transactions[-1]['date']})" if transactions
          else "[!] No transactions found")
    print(f"     income: {income:,.2f}  expenses: {expense:,.2f}")
    if skipped:
        print(f"     skipped {skipped} unparseable row(s)")

    mismatches = verify_balance_chain(transactions)
    if mismatches:
        print(f"[!] {len(mismatches)} balance-chain mismatch(es):")
        for m in mismatches[:5]:
            print(f"    {m}")
    else:
        print("     balance chain: consistent")

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(transactions, f, ensure_ascii=False, indent=2)
        print(f"[OK] Wrote {args.output}")


if __name__ == "__main__":
    main()
