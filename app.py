import json
import os
import sys
import tempfile
import threading
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, send_file, send_from_directory, request

sys.path.insert(0, str(Path(__file__).parent / "tools"))
from utils import load_category_rules, save_category_rules

import db

app = Flask(__name__, static_folder='.', static_url_path='')

CONFIG_PATH = Path(__file__).parent / "config.json"
DEFAULT_BACKUP_PATH = Path(__file__).parent / "backups"
AUTO_BACKUP_DAYS = 30


# ── Config helpers ────────────────────────────────────────────────────────────

def _load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"backup_path": str(DEFAULT_BACKUP_PATH)}


def _save_config(config):
    CONFIG_PATH.write_text(json.dumps(config, indent=4), encoding="utf-8")


def _backup_dir():
    return Path(_load_config().get("backup_path", str(DEFAULT_BACKUP_PATH)))


# ── Backup helpers ────────────────────────────────────────────────────────────

def _create_backup():
    """Create a timestamped zip of the DB. Returns the zip path."""
    backup_dir = _backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    zip_path = backup_dir / f"backup_{timestamp}.zip"

    # Use SQLite backup API for a consistent snapshot
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        import sqlite3
        src = sqlite3.connect(str(db.DB_PATH))
        dst = sqlite3.connect(tmp_path)
        src.backup(dst)
        dst.close()
        src.close()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_path, "expenses.db")
    finally:
        os.unlink(tmp_path)

    db.set_setting("last_backup_at", datetime.now().isoformat(timespec="seconds"))

    # Keep only the 10 most recent backups
    backups = sorted(backup_dir.glob("backup_*.zip"))
    for old in backups[:-10]:
        old.unlink()

    return zip_path


def _maybe_auto_backup():
    """Auto-backup if last backup is older than AUTO_BACKUP_DAYS days (or never)."""
    last = db.get_setting("last_backup_at")
    if last:
        try:
            if (datetime.now() - datetime.fromisoformat(last)).days < AUTO_BACKUP_DAYS:
                return
        except ValueError:
            pass
    try:
        _create_backup()
    except Exception:
        pass  # Never fail a request due to backup error


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


# --- Transactions ---

@app.route('/api/transactions')
def get_transactions():
    _maybe_auto_backup()
    return jsonify(db.get_all_transactions())


@app.route('/api/transactions/<int:transaction_id>', methods=['DELETE'])
def delete_transaction(transaction_id):
    db.delete_transaction(transaction_id)
    return jsonify({'deleted': transaction_id})


@app.route('/api/transactions/<int:transaction_id>', methods=['PATCH'])
def patch_transaction(transaction_id):
    data = request.get_json()
    if data is None:
        return jsonify({'error': 'request body required'}), 400
    if 'excluded' in data:
        db.set_transaction_excluded(transaction_id, data['excluded'])
    if 'notes' in data:
        db.set_transaction_note(transaction_id, data['notes'])
    return jsonify({'id': transaction_id, **{k: data[k] for k in ('excluded', 'notes') if k in data}})


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

    skipped = []
    try:
        if filename.endswith('.pdf'):
            from pdf_to_json import convert_pdf_to_json
            expenses = convert_pdf_to_json(tmp_path)
        elif filename.endswith('.xls') or filename.endswith('.xlsx'):
            from excel_to_json import convert_excel_to_json
            expenses, skipped = convert_excel_to_json(tmp_path, exchange_rates=exchange_rates)
        else:
            return jsonify({'error': 'Unsupported file type. Use .xls or .pdf'}), 400
    finally:
        os.unlink(tmp_path)

    duplicate_count = db.check_duplicates(expenses)
    return jsonify({'transactions': expenses, 'duplicate_count': duplicate_count, 'skipped': skipped})


@app.route('/api/import/confirm', methods=['POST'])
def import_confirm():
    data = request.get_json()
    if not data or 'transactions' not in data:
        return jsonify({'error': 'No transactions provided'}), 400

    # Auto-backup before inserting new data
    try:
        _create_backup()
    except Exception:
        pass

    transactions = data['transactions']
    count = db.insert_transactions(transactions)

    # Apply each merchant's category to all existing transactions and save as rule
    merchant_categories = {}
    for t in transactions:
        merchant_categories[t['merchant']] = t['category']

    rules = load_category_rules()
    for merchant, category in merchant_categories.items():
        db.update_merchant_category(merchant, category)
        rules[merchant] = category
    save_category_rules(rules)

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
    return jsonify([c['name'] for c in db.get_categories()])


@app.route('/api/categories/details')
def get_categories_details():
    return jsonify(db.get_category_details())


@app.route('/api/categories', methods=['POST'])
def create_category():
    data = request.get_json()
    name = (data or {}).get('name', '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400
    updated = db.add_category(name)
    return jsonify({'categories': updated}), 201


@app.route('/api/categories/<path:name>', methods=['DELETE'])
def remove_category(name):
    try:
        updated = db.delete_category(name)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    db.update_merchant_category_by_category(name, 'Uncategorized')
    return jsonify({'categories': updated})


# --- Household Members ---

@app.route('/api/household-members')
def get_household_members():
    return jsonify(db.get_household_members())


@app.route('/api/household-members', methods=['POST'])
def create_household_member():
    data = request.get_json()
    name = (data or {}).get('name', '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400
    updated = db.add_household_member(name)
    return jsonify({'members': updated}), 201


@app.route('/api/household-members/<int:member_id>', methods=['DELETE'])
def remove_household_member(member_id):
    try:
        updated = db.delete_household_member(member_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'members': updated})


# --- Long-Term Funds ---

@app.route('/api/funds')
def get_funds():
    return jsonify(db.get_funds())


@app.route('/api/funds', methods=['POST'])
def create_fund():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    fund_type = data.get('fund_type')
    owner_id = data.get('owner_id')
    if not name or not fund_type:
        return jsonify({'error': 'name and fund_type are required'}), 400
    try:
        updated = db.add_fund(name, fund_type, owner_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'funds': updated}), 201


@app.route('/api/funds/<int:fund_id>', methods=['DELETE'])
def remove_fund(fund_id):
    try:
        updated = db.delete_fund(fund_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'funds': updated})


@app.route('/api/funds/<int:fund_id>/balances')
def get_fund_balances(fund_id):
    return jsonify(db.get_fund_balances(fund_id))


@app.route('/api/funds/<int:fund_id>/balances', methods=['POST'])
def create_fund_balance(fund_id):
    data = request.get_json() or {}
    date = data.get('date')
    balance = data.get('balance')
    contribution = data.get('contribution', 0)
    if not date or balance is None:
        return jsonify({'error': 'date and balance are required'}), 400
    try:
        updated = db.add_fund_balance(fund_id, date, balance, contribution)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'balances': updated}), 201


@app.route('/api/fund-balances/<int:balance_id>', methods=['DELETE'])
def remove_fund_balance(balance_id):
    try:
        updated = db.delete_fund_balance(balance_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'balances': updated})


# --- Bank Accounts ---

@app.route('/api/bank-accounts')
def get_bank_accounts():
    return jsonify(db.get_bank_accounts())


@app.route('/api/bank-accounts', methods=['POST'])
def create_bank_account():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    owner_id = data.get('owner_id')
    account_number = (data.get('account_number') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400
    updated = db.add_bank_account(name, owner_id, account_number)
    return jsonify({'accounts': updated}), 201


@app.route('/api/bank-accounts/<int:account_id>', methods=['DELETE'])
def remove_bank_account(account_id):
    try:
        updated = db.delete_bank_account(account_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'accounts': updated})


@app.route('/api/bank-accounts/<int:account_id>/transactions')
def get_bank_account_transactions(account_id):
    return jsonify(db.get_bank_transactions(account_id))


@app.route('/api/bank-accounts/<int:account_id>/transactions', methods=['POST'])
def create_bank_transaction(account_id):
    data = request.get_json() or {}
    date = data.get('date')
    description = (data.get('description') or '').strip()
    amount = data.get('amount')
    txn_type = data.get('type')
    if not date or not description or amount is None or txn_type not in ('income', 'expense'):
        return jsonify({'error': 'date, description, amount, and a valid type are required'}), 400
    signed_amount = abs(float(amount)) if txn_type == 'income' else -abs(float(amount))
    row = {
        'date': date, 'description': description, 'amount': signed_amount, 'type': txn_type,
        'category': data.get('category', 'Uncategorized'),
    }
    db.insert_bank_transactions([row], account_id)
    return jsonify({'transactions': db.get_bank_transactions(account_id)}), 201


@app.route('/api/bank-transactions/<int:transaction_id>', methods=['PATCH'])
def patch_bank_transaction(transaction_id):
    data = request.get_json()
    if data is None:
        return jsonify({'error': 'request body required'}), 400
    if 'excluded' in data:
        db.set_bank_transaction_excluded(transaction_id, data['excluded'])
    if 'notes' in data:
        db.set_bank_transaction_note(transaction_id, data['notes'])
    return jsonify({'id': transaction_id, **{k: data[k] for k in ('excluded', 'notes') if k in data}})


@app.route('/api/bank-transactions/<int:transaction_id>', methods=['DELETE'])
def remove_bank_transaction(transaction_id):
    db.delete_bank_transaction(transaction_id)
    return jsonify({'deleted': transaction_id})


# --- Backup ---

@app.route('/api/backup')
def download_backup():
    try:
        zip_path = _create_backup()
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return send_file(str(zip_path), as_attachment=True, download_name=zip_path.name)


@app.route('/api/backup/info')
def backup_info():
    last = db.get_setting("last_backup_at")
    config = _load_config()
    return jsonify({
        "last_backup_at": last,
        "backup_path": config.get("backup_path", str(DEFAULT_BACKUP_PATH)),
    })


# --- Config ---

@app.route('/api/config')
def get_config():
    return jsonify(_load_config())


@app.route('/api/config', methods=['PUT'])
def update_config():
    data = request.get_json()
    config = _load_config()
    if 'backup_path' in data:
        config['backup_path'] = data['backup_path']
    _save_config(config)
    return jsonify(config)


if __name__ == '__main__':
    db.init_db()
    print("Expense Dashboard running at http://localhost:5000")
    # Only open browser on the main process, not the reloader child
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        threading.Timer(1.0, lambda: webbrowser.open("http://localhost:5000")).start()
    app.run(debug=True, reloader_type='stat')
