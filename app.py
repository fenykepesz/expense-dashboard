from flask import Flask, jsonify, send_from_directory
import db

app = Flask(__name__, static_folder='.', static_url_path='')


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/api/transactions')
def get_transactions():
    return jsonify(db.get_all_transactions())


@app.route('/api/transactions/<int:transaction_id>', methods=['DELETE'])
def delete_transaction(transaction_id):
    db.delete_transaction(transaction_id)
    return jsonify({'deleted': transaction_id})


if __name__ == '__main__':
    db.init_db()
    print("Expense Dashboard running at http://localhost:5000")
    app.run(debug=True)
