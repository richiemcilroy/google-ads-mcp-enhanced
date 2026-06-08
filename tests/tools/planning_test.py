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

"""Tests for keyword planning tools."""

import unittest
from unittest.mock import patch

from google.ads.googleads.v24.services.types import keyword_plan_idea_service

from ads_mcp.tools import planning


class _FakeKeywordPlanIdeaService:
    def __init__(self):
        self.request = None

    def generate_keyword_ideas(self, request):
        self.request = request
        result = keyword_plan_idea_service.GenerateKeywordIdeaResult()
        result.text = "screen recorder"
        return [result]


class TestPlanningTools(unittest.TestCase):
    """Tests request construction for planning tools."""

    @patch("ads_mcp.tools.planning.utils.get_googleads_service")
    def test_generate_keyword_ideas_builds_seed_request(self, mock_get_service):
        fake_service = _FakeKeywordPlanIdeaService()
        mock_get_service.return_value = fake_service

        result = planning.generate_keyword_ideas(
            customer_id="123-456-7890",
            seed_keywords=["loom alternative"],
            page_url="https://cap.so/loom-alternative",
            geo_target_constant_ids=["2840"],
        )

        self.assertEqual(result[0]["text"], "screen recorder")
        self.assertEqual(fake_service.request.customer_id, "1234567890")
        self.assertEqual(fake_service.request.language, "languageConstants/1000")
        self.assertEqual(
            list(fake_service.request.geo_target_constants),
            ["geoTargetConstants/2840"],
        )
        self.assertEqual(
            list(fake_service.request.keyword_and_url_seed.keywords),
            ["loom alternative"],
        )
        self.assertEqual(
            fake_service.request.keyword_and_url_seed.url,
            "https://cap.so/loom-alternative",
        )

    def test_generate_keyword_ideas_requires_seed(self):
        with self.assertRaises(Exception):
            planning.generate_keyword_ideas(customer_id="1234567890")
