"""Tests for the OpenFoodFacts helpers (HTTP calls are mocked)."""

import unittest
from unittest.mock import MagicMock, patch

import requests

from inventory import external_api
from inventory.external_api import ExternalAPIError, ProductNotFound


def fake_response(json_data=None, status_error=None, json_error=None):
    response = MagicMock()
    if status_error:
        response.raise_for_status.side_effect = status_error
    if json_error:
        response.json.side_effect = json_error
    else:
        response.json.return_value = json_data
    return response


class TestFetchByBarcode(unittest.TestCase):
    @patch("inventory.external_api.requests.get")
    def test_returns_simplified_product(self, mock_get):
        mock_get.return_value = fake_response(
            {
                "status": 1,
                "product": {
                    "code": "123",
                    "product_name": "Organic Almond Milk",
                    "brands": "Silk",
                    "ingredients_text": "Filtered water, almonds",
                    "extra_field": "ignored",
                },
            }
        )
        product = external_api.fetch_product_by_barcode("123")
        self.assertEqual(
            product,
            {
                "product_name": "Organic Almond Milk",
                "brands": "Silk",
                "ingredients_text": "Filtered water, almonds",
                "barcode": "123",
            },
        )

    @patch("inventory.external_api.requests.get")
    def test_status_zero_raises_not_found(self, mock_get):
        mock_get.return_value = fake_response({"status": 0})
        with self.assertRaises(ProductNotFound):
            external_api.fetch_product_by_barcode("000")

    @patch("inventory.external_api.requests.get", side_effect=requests.exceptions.ConnectionError)
    def test_connection_error(self, _mock):
        with self.assertRaises(ExternalAPIError):
            external_api.fetch_product_by_barcode("123")

    @patch("inventory.external_api.requests.get", side_effect=requests.exceptions.Timeout)
    def test_timeout(self, _mock):
        with self.assertRaises(ExternalAPIError):
            external_api.fetch_product_by_barcode("123")

    @patch("inventory.external_api.requests.get")
    def test_http_error(self, mock_get):
        mock_get.return_value = fake_response(status_error=requests.exceptions.HTTPError("500"))
        with self.assertRaises(ExternalAPIError):
            external_api.fetch_product_by_barcode("123")

    @patch("inventory.external_api.requests.get")
    def test_invalid_json(self, mock_get):
        mock_get.return_value = fake_response(json_error=ValueError("bad json"))
        with self.assertRaises(ExternalAPIError):
            external_api.fetch_product_by_barcode("123")


class TestSearchByName(unittest.TestCase):
    @patch("inventory.external_api.requests.get")
    def test_returns_results_and_skips_unnamed(self, mock_get):
        mock_get.return_value = fake_response(
            {
                "products": [
                    {"code": "1", "product_name": "Milk", "brands": "A"},
                    {"code": "2", "product_name": "", "brands": "B"},
                    {"code": "3", "product_name": "Oat Milk", "brands": "C"},
                ]
            }
        )
        results = external_api.search_products_by_name("milk")
        self.assertEqual([p["barcode"] for p in results], ["1", "3"])

    @patch("inventory.external_api.requests.get")
    def test_no_results_raises_not_found(self, mock_get):
        mock_get.return_value = fake_response({"products": []})
        with self.assertRaises(ProductNotFound):
            external_api.search_products_by_name("zzzz")

    @patch("inventory.external_api.requests.get")
    def test_respects_limit(self, mock_get):
        mock_get.return_value = fake_response(
            {"products": [{"code": str(i), "product_name": f"P{i}"} for i in range(10)]}
        )
        self.assertEqual(len(external_api.search_products_by_name("p", limit=3)), 3)


if __name__ == "__main__":
    unittest.main()