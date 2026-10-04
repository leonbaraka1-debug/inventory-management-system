"""Command-line frontend for the Inventory Management System.

Start the Flask server first (`python app.py`), then run `python cli.py`
in a second terminal.
"""

import os

import requests

API_URL = os.environ.get("INVENTORY_API_URL", "http://127.0.0.1:5000")
TIMEOUT = 15  # seconds


# ---------------------------------------------------------------------------
# Talking to the API
# ---------------------------------------------------------------------------
def api_request(method, path, **kwargs):
    """Send a request to the Flask API.

    Returns (data, error). Exactly one of them is None.
    """
    url = f"{API_URL}{path}"
    try:
        response = requests.request(method, url, timeout=TIMEOUT, **kwargs)
    except requests.exceptions.ConnectionError:
        return None, "Could not connect to the API. Is the Flask server running?"
    except requests.exceptions.Timeout:
        return None, "The API request timed out."
    except requests.exceptions.RequestException as exc:
        return None, f"Request failed: {exc}"

    try:
        data = response.json()
    except ValueError:
        return None, f"Unexpected response from the API (status {response.status_code})."

    if response.status_code >= 400:
        return None, data.get("error", f"API error (status {response.status_code}).")

    return data, None


# ---------------------------------------------------------------------------
# Input helpers (keep asking until the input is valid)
# ---------------------------------------------------------------------------
def prompt_text(label, required=True):
    while True:
        value = input(f"{label}: ").strip()
        if value or not required:
            return value
        print("  This field cannot be empty.")


def prompt_float(label, allow_blank=False):
    while True:
        raw = input(f"{label}: ").strip()
        if raw == "" and allow_blank:
            return None
        try:
            value = float(raw)
            if value < 0:
                raise ValueError
            return value
        except ValueError:
            print("  Please enter a number that is 0 or more.")


def prompt_int(label, allow_blank=False):
    while True:
        raw = input(f"{label}: ").strip()
        if raw == "" and allow_blank:
            return None
        try:
            value = int(raw)
            if value < 0:
                raise ValueError
            return value
        except ValueError:
            print("  Please enter a whole number that is 0 or more.")


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------
def print_item(item):
    print(f"  ID:           {item.get('id', '-')}")
    print(f"  Name:         {item.get('product_name', '')}")
    print(f"  Brand:        {item.get('brands', '')}")
    print(f"  Barcode:      {item.get('barcode', '')}")
    if "price" in item:
        print(f"  Price:        Ksh{item['price']:.2f}")
    if "stock" in item:
        print(f"  Stock:        {item['stock']}")
    print(f"  Ingredients:  {item.get('ingredients_text', '')}")
    print("  " + "-" * 40)


# ---------------------------------------------------------------------------
# Menu actions
# ---------------------------------------------------------------------------
def view_all_items():
    items, error = api_request("GET", "/inventory")
    if error:
        print(f"Error: {error}")
        return
    if not items:
        print("The inventory is empty.")
        return
    print(f"\nInventory ({len(items)} items):")
    for item in items:
        print_item(item)


def view_item():
    item_id = prompt_int("Enter item ID")
    item, error = api_request("GET", f"/inventory/{item_id}")
    if error:
        print(f"Error: {error}")
        return
    print()
    print_item(item)


def add_item():
    print("\nAdd a new item")
    payload = {
        "product_name": prompt_text("Product name"),
        "brands": prompt_text("Brand (optional)", required=False),
        "barcode": prompt_text("Barcode (optional)", required=False),
        "ingredients_text": prompt_text("Ingredients (optional)", required=False),
        "price": prompt_float("Price"),
        "stock": prompt_int("Stock quantity"),
    }
    item, error = api_request("POST", "/inventory", json=payload)
    if error:
        print(f"Error: {error}")
        return
    print("Item added:")
    print_item(item)


def update_item():
    item_id = prompt_int("Enter ID of the item to update")
    print("Leave a field blank to keep its current value.")
    price = prompt_float("New price", allow_blank=True)
    stock = prompt_int("New stock level", allow_blank=True)

    payload = {}
    if price is not None:
        payload["price"] = price
    if stock is not None:
        payload["stock"] = stock
    if not payload:
        print("Nothing to update.")
        return

    item, error = api_request("PATCH", f"/inventory/{item_id}", json=payload)
    if error:
        print(f"Error: {error}")
        return
    print("Item updated:")
    print_item(item)


def delete_item():
    item_id = prompt_int("Enter ID of the item to delete")
    confirm = input(f"Delete item {item_id}? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return
    data, error = api_request("DELETE", f"/inventory/{item_id}")
    if error:
        print(f"Error: {error}")
        return
    print(data["message"])


def find_on_api():
    """Look a product up on OpenFoodFacts and optionally add it to the inventory."""
    print("\nFind a product on OpenFoodFacts")
    print("  1. Search by barcode")
    print("  2. Search by name")
    choice = input("Choose 1 or 2: ").strip()

    if choice == "1":
        barcode = prompt_text("Barcode")
        product, error = api_request("GET", f"/external/barcode/{barcode}")
        if error:
            print(f"Error: {error}")
            return
        products = [product]
    elif choice == "2":
        name = prompt_text("Product name")
        products, error = api_request("GET", "/external/search", params={"name": name})
        if error:
            print(f"Error: {error}")
            return
    else:
        print("Invalid choice.")
        return

    print(f"\nFound {len(products)} product(s):")
    for number, product in enumerate(products, start=1):
        print(f"[{number}]")
        print_item(product)

    pick = input("Enter a number to add it to your inventory (or press Enter to skip): ").strip()
    if not pick:
        return
    if not pick.isdigit() or not 1 <= int(pick) <= len(products):
        print("Invalid selection. Nothing was added.")
        return

    chosen = products[int(pick) - 1]
    payload = {
        **chosen,
        "price": prompt_float("Price"),
        "stock": prompt_int("Stock quantity"),
    }
    item, error = api_request("POST", "/inventory", json=payload)
    if error:
        print(f"Error: {error}")
        return
    print("Item added to inventory:")
    print_item(item)


# ---------------------------------------------------------------------------
# Main menu loop
# ---------------------------------------------------------------------------
MENU = """
===== Inventory Management =====
1. View all items
2. View one item
3. Add a new item
4. Update price / stock
5. Delete an item
6. Find a product on OpenFoodFacts
7. Exit
"""

ACTIONS = {
    "1": view_all_items,
    "2": view_item,
    "3": add_item,
    "4": update_item,
    "5": delete_item,
    "6": find_on_api,
}


def main():
    while True:
        print(MENU)
        choice = input("Choose an option (1-7): ").strip()
        if choice == "7":
            print("Goodbye!")
            break
        action = ACTIONS.get(choice)
        if action is None:
            print("Invalid option. Please choose a number from 1 to 7.")
            continue
        try:
            action()
        except (KeyboardInterrupt, EOFError):
            print("\nAction cancelled.")


if __name__ == "__main__":
    main()