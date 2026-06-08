# Copyright 2026 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for conversion upload tools."""

import unittest
from unittest.mock import patch

from fastmcp.exceptions import ToolError
from google.ads.googleads.v24.services.types import conversion_upload_service

from ads_mcp.tools import conversions


class _FakeConversionUploadService:
    def __init__(self):
        self.request = None

    def upload_click_conversions(self, request):
        self.request = request
        return conversion_upload_service.UploadClickConversionsResponse()


class TestConversionTools(unittest.TestCase):
    """Tests conversion upload guardrails and request construction."""

    @patch.dict("os.environ", {}, clear=True)
    def test_real_upload_requires_env_flag(self):
        with self.assertRaises(ToolError):
            conversions.upload_click_conversions(
                customer_id="1234567890",
                conversion_action="111",
                conversions=[
                    {
                        "gclid": "abc",
                        "conversion_date_time": "2026-06-08 12:00:00+00:00",
                        "conversion_value": 12,
                        "currency_code": "USD",
                    }
                ],
                validate_only=False,
            )

    @patch("ads_mcp.tools.conversions.utils.get_googleads_service")
    def test_validate_only_upload_builds_request(self, mock_get_service):
        fake_service = _FakeConversionUploadService()
        mock_get_service.return_value = fake_service

        result = conversions.upload_click_conversions(
            customer_id="123-456-7890",
            conversion_action="111",
            conversions=[
                {
                    "gclid": "abc",
                    "conversion_date_time": "2026-06-08 12:00:00+00:00",
                    "conversion_value": "12.5",
                    "currency_code": "usd",
                    "order_id": "order_1",
                }
            ],
        )

        self.assertTrue(result["validate_only"])
        self.assertTrue(fake_service.request.validate_only)
        self.assertEqual(fake_service.request.customer_id, "1234567890")
        upload = fake_service.request.conversions[0]
        self.assertEqual(upload.gclid, "abc")
        self.assertEqual(
            upload.conversion_action,
            "customers/1234567890/conversionActions/111",
        )
        self.assertEqual(upload.conversion_value, 12.5)
        self.assertEqual(upload.currency_code, "USD")
