# Inventory Management System

A Flask REST API for managing a small retail inventory, with a command-line
interface (CLI) and an integration with the
[OpenFoodFacts API](https://world.openfoodfacts.org/) to pull in real product details.

Data is stored in an in-memory Python list, so it resets whenever the server restarts.

## Project structure

```
inventory-management-system/
├── app.py                   # Flask API (routes, validation, in-memory "database")
├── cli.py                   # Command-line interface that talks to the API
├── inventory/
│   ├── __init__.py
│   └── external_api.py      # OpenFoodFacts helper functions
├── tests/
│   ├── test_app.py          # API endpoint tests
│   ├── test_cli.py          # CLI tests
│   └── test_external_api.py # OpenFoodFacts helper tests
├── docs/                    # mock-ups and extra documentation
├── pytest.ini               # tells pytest where to find the project modules
├── requirements.txt
├── README.md
└── .gitignore
```

## Installation and setup

```bash
git clone https://github.com/leonbaraka1-debug/<your-repo-name>.git
cd <your-repo-name>

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

## Running the app

Use two terminals.

**Terminal 1 – start the API:**

```bash
python app.py
```

The API runs at `http://127.0.0.1:5000` (Flask debug mode is on).

**Terminal 2 – start the CLI:**

```bash
python cli.py
```

To point the CLI at a different server, set `INVENTORY_API_URL`.

## API endpoints

| Method | Endpoint                      | Description                                        |
|--------|-------------------------------|----------------------------------------------------|
| GET    | `/inventory`                  | Fetch all items                                    |
| GET    | `/inventory/<id>`             | Fetch a single item                                |
| POST   | `/inventory`                  | Add a new item                                     |
| PATCH  | `/inventory/<id>`             | Update one or more fields of an item               |
| DELETE | `/inventory/<id>`             | Remove an item                                     |
| GET    | `/external/barcode/<barcode>` | Look up a product on OpenFoodFacts by barcode      |
| GET    | `/external/search?name=...`   | Search OpenFoodFacts by product name               |
| POST   | `/inventory/import`           | Fetch from OpenFoodFacts and add to the inventory  |

### Item shape

```json
{
  "id": 1,
  "product_name": "Organic Almond Milk",
  "brands": "Silk",
  "ingredients_text": "Filtered water, almonds, cane sugar",
  "barcode": "025293600010",
  "price": 530,
  "stock": 25
}
```

`product_name` is required when creating an item. `price` must be 0 or more and
`stock` must be a whole number of 0 or more.

### Example requests

```bash
# Add an item
curl -X POST http://127.0.0.1:5000/inventory \
  -H "Content-Type: application/json" \
  -d '{"product_name": "Oat Milk", "brands": "Oatly", "price": 420, "stock": 10}'

# Update price and stock
curl -X PATCH http://127.0.0.1:5000/inventory/1 \
  -H "Content-Type: application/json" \
  -d '{"price": 580, "stock": 30}'

# Delete an item
curl -X DELETE http://127.0.0.1:5000/inventory/1

# Import a product from OpenFoodFacts by barcode
curl -X POST http://127.0.0.1:5000/inventory/import \
  -H "Content-Type: application/json" \
  -d '{"barcode": "3017620422003", "price": 600, "stock": 12}'
```

### Error responses

Errors are always JSON, for example `{"error": "Item 99 not found."}`.

| Status | Meaning                                              |
|--------|------------------------------------------------------|
| 400    | Invalid or missing input                             |
| 404    | Item or external product not found                   |
| 405    | Method not allowed                                   |
| 502    | OpenFoodFacts could not be reached or failed         |

## CLI usage

```
===== Inventory Management =====
1. View all items
2. View one item
3. Add a new item
4. Update price / stock
5. Delete an item
6. Find a product on OpenFoodFacts
7. Exit
```

Example session – finding a product online and adding it to the inventory:

```
Choose an option (1-7): 6
Choose 1 or 2: 1
Barcode: 3017620422003
Found 1 product(s):
[1]
  Name:         Nutella
  ...
Enter a number to add it to your inventory (or press Enter to skip): 1
Price: 600
Stock quantity: 12
Item added to inventory:
```

## Running the tests

```bash
pytest -v
```

All external HTTP calls are mocked with `unittest.mock`, so the tests run
offline and never touch the real OpenFoodFacts API.

## Maintainability notes

- Validation lives in one function (`validate_fields`) used by every write route.
- IDs come from a counter, so a deleted item's ID is never reused.
- All OpenFoodFacts logic is isolated in `inventory/external_api.py`, so it is easy to swap or mock.