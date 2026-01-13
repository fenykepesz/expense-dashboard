# Interactive Categorization Mode Guide

## Overview

The PDF converter now includes an **interactive mode** (`-i` flag) that helps you quickly categorize unknown merchants and automatically saves the rules for future use.

## How It Works

### Step 1: Run with Interactive Mode

```bash
python tools/pdf_to_json.py "statement.pdf" -o expenses.json -i
```

### Step 2: Categorize Merchants

When the tool finds uncategorized merchants, you'll see a prompt like this:

```
============================================================
Found 10 uncategorized merchant(s)
============================================================

>> New merchant: חברת פרטנר תקשורת בע"מ (הו"ק)
Available categories:
  1. Groceries
  2. Restaurants
  3. Food Delivery
  4. Transportation
  5. Shopping
  6. Technology
  7. Entertainment
  8. Telecommunications
  9. Insurance
  10. Banking Fees
  11. Healthcare
  12. Utilities
  13. General Services
  14. Other

Select category number (or 's' to skip):
```

### Step 3: Enter Category Number

Type the number corresponding to the category. For example, for "Partner Communications":

```
Select category number (or 's' to skip): 8

[OK] Category: Telecommunications
Enter keyword to match (default: 'חברת פרטנר תקשורת בע"מ (הו"ק)'):
```

### Step 4: Choose Keyword (Optional)

You can:
- Press **Enter** to use the full merchant name as the keyword
- Or enter a **shorter keyword** like "פרטנר" to match all Partner transactions

For example:
```
Enter keyword to match (default: 'חברת פרטנר תקשורת בע"מ (הו"ק)'): פרטנר
```

This will match any merchant containing "פרטנר".

### Step 5: Rules Are Saved Automatically

After categorizing all merchants:

```
[OK] Updated category rules saved to ...\tools\category_rules.json
[OK] Added 10 new categorization rule(s)

[OK] Saved 10 transactions to expenses.json
```

## Benefits

1. **One-time effort**: Categorize each merchant once, reuse forever
2. **Smart keywords**: Use short keywords to match variations (e.g., "איקאה" matches "IKEA", "איקאה ישראל", etc.)
3. **Automatic updates**: Rules are saved to `category_rules.json` immediately
4. **Future-proof**: Next PDF will use the updated rules automatically

## Tips

- **Use short keywords** for merchants with variations
  - Example: "פרטנר" instead of full company name
  - Example: "wolt" for "WOLT" or "Wolt Delivery"

- **Skip if unsure**: Press 's' to leave as "Uncategorized"
  - You can always re-run with `-i` later

- **Hebrew and English**: Keywords work with both Hebrew and English text

## Example Session

```bash
$ python tools/pdf_to_json.py "Jan2026.pdf" -o expenses.json -i

============================================================
Found 3 uncategorized merchant(s)
============================================================

>> New merchant: וואלה!שופס
Available categories:
  1. Groceries
  ... (categories list) ...
  7. Entertainment

Select category number (or 's' to skip): 7

[OK] Category: Entertainment
Enter keyword to match (default: 'וואלה!שופס'): וואלה

>> New merchant: מגדל חיים/בריאות
Available categories:
  ... (categories list) ...
  9. Insurance

Select category number (or 's' to skip): 9

[OK] Category: Insurance
Enter keyword to match (default: 'מגדל חיים/בריאות'): מגדל

>> New merchant: איתוראן איתור ושליטה בע"מ הוראות קבע
Available categories:
  ... (categories list) ...
  13. General Services

Select category number (or 's' to skip): 13

[OK] Category: General Services
Enter keyword to match (default: 'איתוראן איתור ושליטה בע"מ הוראות קבע'): איתוראן

[OK] Updated category rules saved to tools\category_rules.json
[OK] Added 3 new categorization rule(s)

[OK] Saved 10 transactions to expenses.json

Extracted 10 transactions
Categories found:
  Entertainment: 1
  Insurance: 2
  General Services: 1
  Telecommunications: 2
  ... (etc)
```

## Available Categories

The tool provides these standard categories:

1. Groceries
2. Restaurants
3. Food Delivery
4. Transportation
5. Shopping
6. Technology
7. Entertainment
8. Telecommunications
9. Insurance
10. Banking Fees
11. Healthcare
12. Utilities
13. General Services
14. Other

These match the categories used in the dashboard for consistency.
