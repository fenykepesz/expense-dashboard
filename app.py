import sys
import tempfile
import os
from pathlib import Path
from flask import Flask, jsonify, send_from_directory, request

# Allow importing converter tools
sys.path.insert(0, str(Path(__file__).parent / "tools"))
from utils import get_available_categories, load_category_rules, save_category_rules

import db

app = Flask(__name__, static_folder='.', static_url_path='')


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


# --- Transactions ---

@app.route('/api/transactions')
def get_transactions():
    return jsonify(db.get_all_transactions())


@app.route('/api/transactions/<int:transaction_id>', methods=['DELETE'])
def delete_transaction(transaction_id):
    db.delete_transaction(transaction_id)
    return jsonify({'deleted': transaction_id})


# --- Import ---

@app.route('/api/import', methods=['POST'])
def import_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    f = request.files['file']
    filename = f.filename.lower()

    exchange_rates = {}
    for key in ('usd_rate', 'eur_rate', 'gbp_rate'):
        val = request.form.get(key)
        if val:
            currency = key.split('_')[0].upper()
            try:
                exchange_rates[currency] = float(val)
            except ValueError:
                pass

    suffix = '.pdf' if filename.endswith('.pdf') else '.xls'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name

    try:
        if filename.endswith('.pdf'):
            from pdf_to_json import convert_pdf_to_json
            expenses = convert_pdf_to_json(tmp_path)
        elif filename.endswith('.xls') or filename.endswith('.xlsx'):
            from excel_to_json import convert_excel_to_json
            expenses = convert_excel_to_json(tmp_path, exchange_rates=exchange_rates)
        else:
            return jsonify({'error': 'Unsupported file type. Use .xls or .pdf'}), 400
    finally:
        os.unlink(tmp_path)

    duplicate_count = db.check_duplicates(expenses)
    return jsonify({
        'transactions': expenses,
        'duplicate_count': duplicate_count,
    })


@app.route('/api/import/confirm', methods=['POST'])
def import_confirm():
    data = request.get_json()
    if not data or 'transactions' not in data:
        return jsonify({'error': 'No transactions provided'}), 400

    expenses = data['transactions']
    count = db.insert_transactions(expenses)
    return jsonify({'inserted': count}), 201


# --- Merchants ---

@app.route('/api/merchants')
def get_merchants():
    return jsonify(db.get_merchants())


@app.route('/api/merchants', methods=['PUT'])
def update_merchant():
    data = request.get_json()
    merchant = data.get('merchant')
    new_category = data.get('new_category')
    save_rule = data.get('save_rule', False)

    if not merchant or not new_category:
        return jsonify({'error': 'merchant and new_category are required'}), 400

    db.update_merchant_category(merchant, new_category)

    if save_rule:
        rules = load_category_rules()
        rules[merchant] = new_category
        save_category_rules(rules)

    return jsonify({'updated': merchant, 'category': new_category, 'rule_saved': save_rule})


# --- Categories ---

@app.route('/api/categories')
def get_categories():
    return jsonify(get_available_categories())


if __name__ == '__main__':
    db.init_db()
    print("Expense Dashboard running at http://localhost:5000")
    app.run(debug=True)
