# Personal Expense Dashboard

A beautiful, interactive expense tracking dashboard built with HTML, CSS, and Chart.js Front End, Elasticsearch backend and FastAPI REST API.

![Screenshot](Screenshot.jpg)

## Features

- **Dashboard View**: Interactive charts showing spending by category, merchant, and card
- **Monthly Trends**: Line chart tracking spending over time
- **Filtering**: Filter expenses by month, category, card, or search by merchant
- **Full CRUD Operations**: Create, read, update, and delete expenses
- **Elasticsearch Backend**: Fast, scalable search and storage

## Architecture

```
??? backend/                 # FastAPI backend
?   ??? main.py             # API endpoints
?   ??? models.py           # Pydantic models
?   ??? elasticsearch_client.py  # ES connection
?   ??? requirements.txt    # Python dependencies
??? scripts/
?   ??? migrate_data.py     # Data migration script
??? index.html              # Frontend dashboard
??? expense_data.json       # Sample data
```

## Prerequisites

- Python 3.10+
- Elasticsearch 8.x running on `localhost:9200`

## Setup

### 1. Start Elasticsearch

Make sure Elasticsearch is running locally:

```bash
# Using Docker
docker run -d --name elasticsearch \
  -p 9200:9200 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  elasticsearch:8.12.0
```

### 2. Install Python Dependencies

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Migrate Sample Data

```bash
cd scripts
python migrate_data.py
```

### 4. Start the Backend

```bash
cd backend
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

### 5. Open the Dashboard

Open `index.html` in your browser, or serve it with a local server:

```bash
# Using Python
python -m http.server 3000

# Then open http://localhost:3000
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/expenses` | List all expenses (with filters) |
| GET | `/api/expenses/{id}` | Get single expense |
| POST | `/api/expenses` | Create new expense |
| PUT | `/api/expenses/{id}` | Update expense |
| DELETE | `/api/expenses/{id}` | Delete expense |
| GET | `/api/categories` | List unique categories |
| GET | `/api/months` | List unique months |
| GET | `/api/cards` | List unique card numbers |
| GET | `/health` | Health check |

### Query Parameters for `/api/expenses`

- `month` - Filter by month (e.g., "Jan 2024")
- `category` - Filter by category
- `card` - Filter by card last 4 digits
- `merchant` - Search by merchant name (fuzzy match)
- `min_amount` - Minimum amount filter
- `max_amount` - Maximum amount filter
- `size` - Number of results (default: 1000)

## API Documentation

Interactive API docs available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ELASTICSEARCH_URL` | `http://localhost:9200` | Elasticsearch URL |
| `ELASTICSEARCH_INDEX` | `expenses` | Index name |
| `ELASTICSEARCH_USERNAME` | - | Optional: ES username |
| `ELASTICSEARCH_PASSWORD` | - | Optional: ES password |

## License

MIT License - see [LICENSE](LICENSE) for details.
