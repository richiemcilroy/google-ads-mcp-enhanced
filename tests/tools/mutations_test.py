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

"""Tests for guarded Google Ads mutation tools."""

import unittest
from unittest.mock import patch

from fastmcp.exceptions import ToolError
from ads_mcp.tools import mutations


class _FakeResult:
    def __init__(self, resource_name):
        self.resource_name = resource_name


class _FakeResponse:
    results = [_FakeResult("customers/123/campaigns/456")]


class _FakeCampaignService:
    def __init__(self):
        self.request = None

    def campaign_path(self, customer_id, campaign_id):
        return f"customers/{customer_id}/campaigns/{campaign_id}"

    def mutate_campaigns(self, request):
        self.request = request
        return _FakeResponse()


class TestMutationTools(unittest.TestCase):
    """Tests mutation guardrails and request construction."""

    @patch.dict("os.environ", {}, clear=True)
    def test_real_mutation_requires_env_flag(self):
        """Real mutations fail before touching Google Ads services when disabled."""
        with self.assertRaises(ToolError):
            mutations.set_campaign_status(
                customer_id="123-456-7890",
                campaign_id="456",
                status="PAUSED",
                validate_only=False,
            )

    @patch("ads_mcp.tools.mutations.utils.get_googleads_service")
    def test_validate_only_builds_campaign_status_update(self, mock_get_service):
        """Validate-only mutations build the same request without requiring the env flag."""
        fake_service = _FakeCampaignService()
        mock_get_service.return_value = fake_service

        result = mutations.set_campaign_status(
            customer_id="123-456-7890",
            campaign_id="456",
            status="PAUSED",
        )

        self.assertTrue(result["validate_only"])
        self.assertEqual(result["operation_count"], 1)
        self.assertEqual(result["resource_names"], ["customers/123/campaigns/456"])
        self.assertTrue(fake_service.request["validate_only"])
        self.assertEqual(fake_service.request["customer_id"], "1234567890")

        operation = fake_service.request["operations"][0]
        self.assertEqual(
            operation.update.resource_name, "customers/1234567890/campaigns/456"
        )
        self.assertEqual(list(operation.update_mask.paths), ["status"])

    def test_empty_keywords_are_rejected(self):
        """Keyword mutation tools require at least one non-empty keyword."""
        with self.assertRaises(ToolError):
            mutations.add_campaign_negative_keywords(
                customer_id="1234567890",
                campaign_id="456",
                keywords=["", "  "],
            )

    @patch.dict(
        "os.environ",
        {"GOOGLE_ADS_MCP_MAX_DAILY_BUDGET_MICROS": "1000"},
        clear=True,
    )
    def test_budget_cap_blocks_oversized_budget_before_credentials(self):
        """Budget caps fail locally before Google Ads credentials are needed."""
        with self.assertRaises(ToolError):
            mutations.create_campaign_budget(
                customer_id="1234567890",
                name="Too high",
                amount_micros=1001,
            )

    @patch.dict(
        "os.environ",
        {"GOOGLE_ADS_MCP_ENABLE_MUTATIONS": "true"},
        clear=True,
    )
    def test_real_enable_requires_enable_flag(self):
        """Real enable operations require an extra launch approval flag."""
        with self.assertRaises(ToolError):
            mutations.set_campaign_status(
                customer_id="1234567890",
                campaign_id="456",
                status="ENABLED",
                validate_only=False,
            )
