import pdfplumber
import sys

# Quick script to explore PDF structure
pdf_path = sys.argv[1] if len(sys.argv) > 1 else "9334December.pdf"

with pdfplumber.open(pdf_path) as pdf:
    print(f"Total pages: {len(pdf.pages)}")
    
    # Extract first 2 pages to understand structure
    for i, page in enumerate(pdf.pages[:2]):
        print(f"\n{'='*60}")
        print(f"PAGE {i+1}")
        print('='*60)
        
        # Get text
        text = page.extract_text()
        if text:
            print("\n--- RAW TEXT (first 2000 chars) ---")
            print(text[:2000])
        
        # Get tables
        tables = page.extract_tables()
        if tables:
            print(f"\n--- TABLES FOUND: {len(tables)} ---")
            for j, table in enumerate(tables[:2]):
                print(f"\nTable {j+1} (first 5 rows):")
                for row in table[:5]:
                    print(row)
