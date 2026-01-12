import json
import argparse
from datetime import datetime
import calendar
import sys

# Mapping of month numbers to names for English month names
MONTH_NAMES = {i: calendar.month_name[i] for i in range(1, 13)}

def custom_date_parser(date_str):
    """
    Parses a date string in DD/MM/YY or DD/MM/YYYY format.
    Returns a datetime object or None if invalid.
    """
    formats = ["%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None

def convert_data(input_file, output_file):
    print(f"Reading from: {input_file}")
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        converted_data = []
        skipped_count = 0
        
        for entry in data:
            original_date = entry.get('date')
            if not original_date:
                skipped_count += 1
                continue
                
            date_obj = custom_date_parser(original_date)
            if not date_obj:
                print(f"Warning: Skipping invalid date: {original_date} for merchant {entry.get('merchant', 'Unknown')}")
                skipped_count += 1
                continue
            
            # Create new entry, preserving existing fields but updating date info
            new_entry = entry.copy()
            new_entry['date'] = date_obj.strftime("%Y-%m-%d") # standardize to ISO
            new_entry['year'] = date_obj.year
            new_entry['month'] = MONTH_NAMES[date_obj.month]
            
            converted_data.append(new_entry)
            
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(converted_data, f, indent=4, ensure_ascii=False)
            
        print(f"Success! {len(converted_data)} transactions converted.")
        if skipped_count > 0:
            print(f"Skipped {skipped_count} invalid entries.")
        print(f"Saved new file to: {output_file}")
        
    except FileNotFoundError:
        print(f"Error: The file '{input_file}' was not found.")
    except json.JSONDecodeError:
        print(f"Error: '{input_file}' is not a valid JSON file.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert legacy expense JSON data to the new dashboard format.")
    parser.add_argument("input", help="Path to the input JSON file (legacy format)")
    parser.add_argument("-o", "--output", default="expenses_v2.json", help="Path to the output JSON file (default: expenses_v2.json)")
    
    args = parser.parse_args()
    
    convert_data(args.input, args.output)
