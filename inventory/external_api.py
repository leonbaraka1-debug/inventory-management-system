"""Helpers for talking to the OpenFoodFacts API.

Every function returns "simplified" product dictionaries that match the
shape of our own inventory items, so the Flask app can drop them straight
into the in-memory inventory array.
"""

import requests

BASE_URL = "https://world.openfoodfacts.org"
# OpenFoodFacts asks API users to identify their app with a User-Agent.
HEADERS = {"User-Agent": "InventoryManagementLab/1.0 (student project)"}
TIMEOUT = 10  # seconds


class ExternalAPIError(Exception):
    """Raised when the external API cannot be reached or returns bad data."""


class ProductNotFound(ExternalAPIError):
    """Raised when the external API has no matching product."""


def _simplify(product, fallback_barcode=""):
    """Keep only the fields we care about from an OpenFoodFacts product."""
    return {
        "product_name": (product.get("product_name") or "").strip(),
        "brands": (product.get("brands") or "").strip(),
        "ingredients_text": (product.get("ingredients_text") or "").strip(),
        "barcode": str(product.get("code") or fallback_barcode),
    }


def _get_json(url, params=None):
    """GET a URL and return parsed JSON, converting failures to ExternalAPIError."""
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout as exc:
        raise ExternalAPIError("The OpenFoodFacts API timed out.") from exc
    except requests.exceptions.ConnectionError as exc:
        raise ExternalAPIError("Could not connect to the OpenFoodFacts API.") from exc
    except requests.exceptions.HTTPError as exc:
        raise ExternalAPIError(f"OpenFoodFacts returned an error: {exc}") from exc
    except ValueError as exc:  # response.json() failed
        raise ExternalAPIError("OpenFoodFacts returned invalid JSON.") from exc
    except requests.exceptions.RequestException as exc:
        raise ExternalAPIError(f"Request to OpenFoodFacts failed: {exc}") from exc


def fetch_product_by_barcode(barcode):
    """Return one simplified product for a barcode, or raise ProductNotFound."""
    data = _get_json(f"{BASE_URL}/api/v0/product/{barcode}.json")

    if data.get("status") != 1 or not data.get("product"):
        raise ProductNotFound(f"No product found for barcode {barcode}.")

    return _simplify(data["product"], fallback_barcode=barcode)


def search_products_by_name(name, limit=5):
    """Return a list of simplified products matching a name, or raise ProductNotFound."""
    params = {
        "search_terms": name,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": limit,
    }
    data = _get_json(f"{BASE_URL}/cgi/search.pl", params=params)

    results = [_simplify(p) for p in data.get("products", [])]
    # Skip products that have no name - they are useless in an inventory.
    results = [p for p in results if p["product_name"]]

    if not results:
        raise ProductNotFound(f"No products found matching '{name}'.")

    return results[:limit]