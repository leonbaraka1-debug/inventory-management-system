"""Flask REST API for the Inventory Management System.

The "database" is a plain Python list (`inventory`) that lives in memory,
so data resets every time the server restarts.
"""

from flask import Flask, jsonify, request

from inventory.external_api import (
    ExternalAPIError,
    ProductNotFound,
    fetch_product_by_barcode,
    search_products_by_name,
)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Mock database (array of dictionaries, each with a unique id)
# ---------------------------------------------------------------------------
inventory = []
_next_id = 1


def seed_inventory():
    """Reset the mock database to a small set of starter items."""
    global _next_id
    inventory.clear()
    _next_id = 1
    starter_items = [
        {
            "product_name": "Organic Almond Milk",
            "brands": "Silk",
            "ingredients_text": "Filtered water, almonds, cane sugar",
            "barcode": "025293600010",
            "price": 130.00,
            "stock": 25,
        },
        {
            "product_name": "Crunchy Peanut Butter",
            "brands": "Jif",
            "ingredients_text": "Roasted peanuts, sugar, palm oil, salt",
            "barcode": "051500255162",
            "price": 3.49,
            "stock": 40,
        },
    ]
    for item in starter_items:
        add_to_inventory(item)


def add_to_inventory(fields):
    """Give the item a new unique id, append it to the array and return it."""
    global _next_id
    item = {"id": _next_id, **fields}
    _next_id += 1
    inventory.append(item)
    return item


def find_item(item_id):
    """Return the item with this id, or None."""
    return next((item for item in inventory if item["id"] == item_id), None)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def is_number(value):
    # bool is a subclass of int in Python, so exclude it explicitly.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_fields(data, partial=False):
    """Validate request data.

    Returns (clean_fields, error_message). When `partial` is True (PATCH),
    no field is required; when False (POST), product_name is required.
    """
    if not isinstance(data, dict):
        return None, "Request body must be a JSON object."

    clean = {}

    if "product_name" in data or not partial:
        name = data.get("product_name")
        if not isinstance(name, str) or not name.strip():
            return None, "product_name is required and must be a non-empty string."
        clean["product_name"] = name.strip()

    for field in ("brands", "ingredients_text", "barcode"):
        if field in data:
            if not isinstance(data[field], str):
                return None, f"{field} must be a string."
            clean[field] = data[field].strip()

    if "price" in data:
        if not is_number(data["price"]) or data["price"] < 0:
            return None, "price must be a number that is 0 or more."
        clean["price"] = round(float(data["price"]), 2)

    if "stock" in data:
        if not isinstance(data["stock"], int) or isinstance(data["stock"], bool) or data["stock"] < 0:
            return None, "stock must be a whole number that is 0 or more."
        clean["stock"] = data["stock"]

    if partial and not clean:
        return None, "Provide at least one field to update."

    return clean, None


def error_response(message, status):
    return jsonify({"error": message}), status


# ---------------------------------------------------------------------------
# CRUD routes
# ---------------------------------------------------------------------------
@app.route("/inventory", methods=["GET"])
def get_inventory():
    """Fetch all items."""
    return jsonify(inventory), 200


@app.route("/inventory/<int:item_id>", methods=["GET"])
def get_item(item_id):
    """Fetch a single item."""
    item = find_item(item_id)
    if item is None:
        return error_response(f"Item {item_id} not found.", 404)
    return jsonify(item), 200


@app.route("/inventory", methods=["POST"])
def create_item():
    """Add a new item."""
    data = request.get_json(silent=True)
    clean, error = validate_fields(data)
    if error:
        return error_response(error, 400)

    # Fill in defaults for anything the client did not send.
    fields = {
        "brands": "",
        "ingredients_text": "",
        "barcode": "",
        "price": 0.0,
        "stock": 0,
        **clean,
    }
    return jsonify(add_to_inventory(fields)), 201


@app.route("/inventory/<int:item_id>", methods=["PATCH"])
def update_item(item_id):
    """Update one or more fields of an item."""
    item = find_item(item_id)
    if item is None:
        return error_response(f"Item {item_id} not found.", 404)

    data = request.get_json(silent=True)
    clean, error = validate_fields(data, partial=True)
    if error:
        return error_response(error, 400)

    item.update(clean)
    return jsonify(item), 200


@app.route("/inventory/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    """Remove an item."""
    item = find_item(item_id)
    if item is None:
        return error_response(f"Item {item_id} not found.", 404)

    inventory.remove(item)
    return jsonify({"message": f"Item {item_id} deleted.", "item": item}), 200


# ---------------------------------------------------------------------------
# External API (OpenFoodFacts) helper routes
# ---------------------------------------------------------------------------
@app.route("/external/barcode/<barcode>", methods=["GET"])
def external_by_barcode(barcode):
    """Look up a product on OpenFoodFacts by barcode (does not save it)."""
    try:
        return jsonify(fetch_product_by_barcode(barcode)), 200
    except ProductNotFound as exc:
        return error_response(str(exc), 404)
    except ExternalAPIError as exc:
        return error_response(str(exc), 502)


@app.route("/external/search", methods=["GET"])
def external_search():
    """Search OpenFoodFacts by product name (does not save anything)."""
    name = request.args.get("name", "").strip()
    if not name:
        return error_response("Query parameter 'name' is required.", 400)

    try:
        return jsonify(search_products_by_name(name)), 200
    except ProductNotFound as exc:
        return error_response(str(exc), 404)
    except ExternalAPIError as exc:
        return error_response(str(exc), 502)


@app.route("/inventory/import", methods=["POST"])
def import_item():
    """Fetch a product from OpenFoodFacts and add it to the inventory.

    Body: {"barcode": "..."} or {"name": "..."}, plus optional price and stock.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("Request body must be a JSON object.", 400)

    barcode = str(data.get("barcode", "")).strip()
    name = str(data.get("name", "")).strip()
    if not barcode and not name:
        return error_response("Provide either 'barcode' or 'name'.", 400)

    # Validate price/stock before we spend time calling the external API.
    extras = {k: data[k] for k in ("price", "stock") if k in data}
    clean_extras = {}
    if extras:
        clean_extras, error = validate_fields(
            {"product_name": "placeholder", **extras}
        )
        if error:
            return error_response(error, 400)
        clean_extras.pop("product_name")

    try:
        if barcode:
            product = fetch_product_by_barcode(barcode)
        else:
            product = search_products_by_name(name, limit=1)[0]
    except ProductNotFound as exc:
        return error_response(str(exc), 404)
    except ExternalAPIError as exc:
        return error_response(str(exc), 502)

    fields = {"price": 0.0, "stock": 0, **product, **clean_extras}
    return jsonify(add_to_inventory(fields)), 201


# ---------------------------------------------------------------------------
# JSON error handlers (so the CLI always receives JSON, never HTML)
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def handle_404(_error):
    return error_response("Resource not found.", 404)


@app.errorhandler(405)
def handle_405(_error):
    return error_response("Method not allowed.", 405)


@app.errorhandler(500)
def handle_500(_error):
    return error_response("Internal server error.", 500)


seed_inventory()

if __name__ == "__main__":
    app.run(debug=True)