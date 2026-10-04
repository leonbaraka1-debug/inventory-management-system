"""Tests for the CLI commands (user input and API calls are mocked)."""

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

import requests

import cli

SAMPLE_ITEM = {
    "id": 1,
    "product_name": "Organic Almond Milk",
    "brands": "Silk",
    "ingredients_text": "Filtered water, almonds",
    "barcode": "123",
    "price": 4.99,
    "stock": 25,
}


def run(func, inputs):
    """Run a CLI function with scripted input and return everything it printed."""
    buffer = io.StringIO()
    with patch("builtins.input", side_effect=inputs), redirect_stdout(buffer):
        func()
    return buffer.getvalue()


class TestApiRequest(unittest.TestCase):
    @patch("cli.requests.request")
    def test_success_returns_data(self, mock_request):
        mock_request.return_value = MagicMock(status_code=200, json=lambda: [SAMPLE_ITEM])
        data, error = cli.api_request("GET", "/inventory")
        self.assertEqual(data, [SAMPLE_ITEM])
        self.assertIsNone(error)

    @patch("cli.requests.request")
    def test_error_status_returns_message(self, mock_request):
        mock_request.return_value = MagicMock(
            status_code=404, json=lambda: {"error": "Item 9 not found."}
        )
        data, error = cli.api_request("GET", "/inventory/9")
        self.assertIsNone(data)
        self.assertEqual(error, "Item 9 not found.")

    @patch("cli.requests.request", side_effect=requests.exceptions.ConnectionError)
    def test_connection_error(self, _mock):
        data, error = cli.api_request("GET", "/inventory")
        self.assertIsNone(data)
        self.assertIn("Could not connect", error)

    @patch("cli.requests.request", side_effect=requests.exceptions.Timeout)
    def test_timeout(self, _mock):
        _data, error = cli.api_request("GET", "/inventory")
        self.assertIn("timed out", error)

    @patch("cli.requests.request")
    def test_non_json_response(self, mock_request):
        response = MagicMock(status_code=500)
        response.json.side_effect = ValueError
        mock_request.return_value = response
        _data, error = cli.api_request("GET", "/inventory")
        self.assertIn("Unexpected response", error)


class TestInputHelpers(unittest.TestCase):
    def test_prompt_float_retries_until_valid(self):
        buffer = io.StringIO()
        with patch("builtins.input", side_effect=["abc", "-3", "4.5"]), redirect_stdout(buffer):
            self.assertEqual(cli.prompt_float("Price"), 4.5)
        self.assertIn("Please enter a number", buffer.getvalue())

    def test_prompt_int_blank_allowed(self):
        with patch("builtins.input", side_effect=[""]):
            self.assertIsNone(cli.prompt_int("Stock", allow_blank=True))

    def test_prompt_int_rejects_decimals(self):
        buffer = io.StringIO()
        with patch("builtins.input", side_effect=["2.5", "7"]), redirect_stdout(buffer):
            self.assertEqual(cli.prompt_int("Stock"), 7)

    def test_prompt_text_rejects_empty_when_required(self):
        buffer = io.StringIO()
        with patch("builtins.input", side_effect=["", "Milk"]), redirect_stdout(buffer):
            self.assertEqual(cli.prompt_text("Name"), "Milk")


class TestMenuActions(unittest.TestCase):
    @patch("cli.api_request", return_value=([SAMPLE_ITEM], None))
    def test_view_all_items(self, _mock):
        output = run(cli.view_all_items, [])
        self.assertIn("Organic Almond Milk", output)

    @patch("cli.api_request", return_value=([], None))
    def test_view_all_items_empty(self, _mock):
        self.assertIn("empty", run(cli.view_all_items, []))

    @patch("cli.api_request", return_value=(None, "Could not connect to the API."))
    def test_view_all_items_shows_api_error(self, _mock):
        self.assertIn("Could not connect", run(cli.view_all_items, []))

    @patch("cli.api_request", return_value=(SAMPLE_ITEM, None))
    def test_add_item_sends_correct_payload(self, mock_api):
        inputs = ["Almond Milk", "Silk", "123", "Water, almonds", "4.99", "25"]
        run(cli.add_item, inputs)
        method, path = mock_api.call_args.args
        payload = mock_api.call_args.kwargs["json"]
        self.assertEqual((method, path), ("POST", "/inventory"))
        self.assertEqual(payload["product_name"], "Almond Milk")
        self.assertEqual(payload["price"], 4.99)
        self.assertEqual(payload["stock"], 25)

    @patch("cli.api_request", return_value=(SAMPLE_ITEM, None))
    def test_update_item_only_sends_changed_fields(self, mock_api):
        run(cli.update_item, ["1", "5.50", ""])  # new price, keep stock
        self.assertEqual(mock_api.call_args.args, ("PATCH", "/inventory/1"))
        self.assertEqual(mock_api.call_args.kwargs["json"], {"price": 5.5})

    @patch("cli.api_request")
    def test_update_item_with_nothing_to_change_makes_no_request(self, mock_api):
        output = run(cli.update_item, ["1", "", ""])
        self.assertIn("Nothing to update", output)
        mock_api.assert_not_called()

    @patch("cli.api_request", return_value=({"message": "Item 1 deleted."}, None))
    def test_delete_item_confirmed(self, mock_api):
        output = run(cli.delete_item, ["1", "y"])
        self.assertIn("deleted", output)
        self.assertEqual(mock_api.call_args.args, ("DELETE", "/inventory/1"))

    @patch("cli.api_request")
    def test_delete_item_cancelled(self, mock_api):
        output = run(cli.delete_item, ["1", "n"])
        self.assertIn("Cancelled", output)
        mock_api.assert_not_called()

    @patch("cli.api_request")
    def test_find_by_barcode_then_add(self, mock_api):
        found = {
            "product_name": "Nutella",
            "brands": "Ferrero",
            "ingredients_text": "Sugar",
            "barcode": "3017620422003",
        }
        mock_api.side_effect = [(found, None), ({**found, "id": 3}, None)]
        output = run(cli.find_on_api, ["1", "3017620422003", "1", "5.99", "10"])
        self.assertIn("Nutella", output)
        self.assertIn("added to inventory", output)
        post_call = mock_api.call_args_list[1]
        self.assertEqual(post_call.args, ("POST", "/inventory"))
        self.assertEqual(post_call.kwargs["json"]["price"], 5.99)

    @patch("cli.api_request", return_value=(None, "No product found."))
    def test_find_on_api_shows_error(self, _mock):
        self.assertIn("No product found", run(cli.find_on_api, ["1", "000"]))

    @patch("cli.api_request")
    def test_find_on_api_skip_adding(self, mock_api):
        mock_api.return_value = ([{"product_name": "Milk", "barcode": "1"}], None)
        run(cli.find_on_api, ["2", "milk", ""])
        self.assertEqual(mock_api.call_count, 1)  # only the search, no POST


class TestMain(unittest.TestCase):
    def test_exit(self):
        self.assertIn("Goodbye", run(cli.main, ["7"]))

    def test_invalid_option_then_exit(self):
        output = run(cli.main, ["99", "7"])
        self.assertIn("Invalid option", output)

    @patch("cli.api_request", return_value=([SAMPLE_ITEM], None))
    def test_menu_dispatches_to_action(self, _mock):
        output = run(cli.main, ["1", "7"])
        self.assertIn("Organic Almond Milk", output)


if __name__ == "__main__":
    unittest.main()