"""Tests for the Flask API endpoints (external API calls are mocked)."""

import unittest
from unittest.mock import patch

import app as app_module
from inventory.external_api import ExternalAPIError, ProductNotFound


class APITestCase(unittest.TestCase):
    def setUp(self):
        app_module.seed_inventory()  # fresh data for every test
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()


class TestGetRoutes(APITestCase):
    def test_get_all_items(self):
        response = self.client.get("/inventory")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()), 2)

    def test_get_single_item(self):
        response = self.client.get("/inventory/1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["product_name"], "Organic Almond Milk")

    def test_get_missing_item_returns_404(self):
        response = self.client.get("/inventory/999")
        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.get_json())


class TestPost(APITestCase):
    def test_create_item(self):
        payload = {"product_name": "Oat Milk", "brands": "Oatly", "price": 3.5, "stock": 10}
        response = self.client.post("/inventory", json=payload)
        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["id"], 3)
        self.assertEqual(body["product_name"], "Oat Milk")
        self.assertEqual(len(app_module.inventory), 3)

    def test_create_applies_defaults(self):
        response = self.client.post("/inventory", json={"product_name": "Rice"})
        body = response.get_json()
        self.assertEqual(body["price"], 0.0)
        self.assertEqual(body["stock"], 0)

    def test_create_requires_product_name(self):
        response = self.client.post("/inventory", json={"price": 2})
        self.assertEqual(response.status_code, 400)

    def test_create_rejects_negative_price(self):
        response = self.client.post("/inventory", json={"product_name": "X", "price": -1})
        self.assertEqual(response.status_code, 400)

    def test_create_rejects_non_integer_stock(self):
        response = self.client.post("/inventory", json={"product_name": "X", "stock": 1.5})
        self.assertEqual(response.status_code, 400)

    def test_create_rejects_invalid_json(self):
        response = self.client.post(
            "/inventory", data="not json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)


class TestPatch(APITestCase):
    def test_update_price_and_stock(self):
        response = self.client.patch("/inventory/1", json={"price": 6.25, "stock": 5})
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["price"], 6.25)
        self.assertEqual(body["stock"], 5)
        # Fields we did not send stay the same.
        self.assertEqual(body["product_name"], "Organic Almond Milk")

    def test_update_missing_item_returns_404(self):
        response = self.client.patch("/inventory/999", json={"price": 1})
        self.assertEqual(response.status_code, 404)

    def test_update_with_empty_body_returns_400(self):
        response = self.client.patch("/inventory/1", json={})
        self.assertEqual(response.status_code, 400)

    def test_update_with_invalid_value_returns_400(self):
        response = self.client.patch("/inventory/1", json={"stock": -4})
        self.assertEqual(response.status_code, 400)


class TestDelete(APITestCase):
    def test_delete_item(self):
        response = self.client.delete("/inventory/1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/inventory/1").status_code, 404)
        self.assertEqual(len(app_module.inventory), 1)

    def test_delete_missing_item_returns_404(self):
        response = self.client.delete("/inventory/999")
        self.assertEqual(response.status_code, 404)

    def test_ids_are_not_reused_after_delete(self):
        self.client.delete("/inventory/2")
        response = self.client.post("/inventory", json={"product_name": "New"})
        self.assertEqual(response.get_json()["id"], 3)


class TestExternalRoutes(APITestCase):
    FAKE_PRODUCT = {
        "product_name": "Nutella",
        "brands": "Ferrero",
        "ingredients_text": "Sugar, palm oil, hazelnuts",
        "barcode": "3017620422003",
    }

    @patch("app.fetch_product_by_barcode")
    def test_external_barcode_found(self, mock_fetch):
        mock_fetch.return_value = self.FAKE_PRODUCT
        response = self.client.get("/external/barcode/3017620422003")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["product_name"], "Nutella")

    @patch("app.fetch_product_by_barcode", side_effect=ProductNotFound("nope"))
    def test_external_barcode_not_found(self, _mock):
        response = self.client.get("/external/barcode/0000")
        self.assertEqual(response.status_code, 404)

    @patch("app.fetch_product_by_barcode", side_effect=ExternalAPIError("down"))
    def test_external_barcode_api_failure_returns_502(self, _mock):
        response = self.client.get("/external/barcode/123")
        self.assertEqual(response.status_code, 502)

    @patch("app.search_products_by_name")
    def test_external_search(self, mock_search):
        mock_search.return_value = [self.FAKE_PRODUCT]
        response = self.client.get("/external/search?name=nutella")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()), 1)

    def test_external_search_requires_name(self):
        response = self.client.get("/external/search")
        self.assertEqual(response.status_code, 400)

    @patch("app.fetch_product_by_barcode")
    def test_import_by_barcode_adds_to_inventory(self, mock_fetch):
        mock_fetch.return_value = self.FAKE_PRODUCT
        response = self.client.post(
            "/inventory/import", json={"barcode": "3017620422003", "price": 5, "stock": 12}
        )
        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["product_name"], "Nutella")
        self.assertEqual(body["price"], 5.0)
        self.assertEqual(body["stock"], 12)
        self.assertEqual(len(app_module.inventory), 3)

    @patch("app.search_products_by_name")
    def test_import_by_name_uses_first_result(self, mock_search):
        mock_search.return_value = [self.FAKE_PRODUCT]
        response = self.client.post("/inventory/import", json={"name": "nutella"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["brands"], "Ferrero")

    def test_import_requires_barcode_or_name(self):
        response = self.client.post("/inventory/import", json={})
        self.assertEqual(response.status_code, 400)

    @patch("app.fetch_product_by_barcode", side_effect=ProductNotFound("nope"))
    def test_import_not_found_adds_nothing(self, _mock):
        response = self.client.post("/inventory/import", json={"barcode": "0"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(app_module.inventory), 2)


class TestErrorHandlers(APITestCase):
    def test_unknown_route_returns_json_404(self):
        response = self.client.get("/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.get_json())

    def test_wrong_method_returns_json_405(self):
        response = self.client.put("/inventory")
        self.assertEqual(response.status_code, 405)
        self.assertIn("error", response.get_json())


if __name__ == "__main__":
    unittest.main()