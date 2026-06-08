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

"""Tests for reporting tools."""

import unittest
from unittest.mock import patch

from fastmcp.exceptions import ToolError

from ads_mcp.tools import reports


class TestReportingTools(unittest.TestCase):
    """Tests report post-processing helpers."""

    @patch("ads_mcp.tools.reports.search_terms_report")
    def test_negative_keyword_recommendations_filters_rows(self, mock_report):
        mock_report.return_value = [
            {
                "search_term_view.search_term": "free screen recorder",
                "campaign.id": 1,
                "ad_group.id": 2,
                "metrics.cost_micros": 9000000,
                "metrics.conversions": 0,
            },
            {
                "search_term_view.search_term": "cap screen recorder",
                "campaign.id": 1,
                "ad_group.id": 2,
                "metrics.cost_micros": 9000000,
                "metrics.conversions": 0,
            },
            {
                "search_term_view.search_term": "paid screen recorder",
                "campaign.id": 1,
                "ad_group.id": 2,
                "metrics.cost_micros": 9000000,
                "metrics.conversions": 2,
            },
        ]

        result = reports.negative_keyword_recommendations(
            customer_id="1234567890",
            start_date="2026-06-01",
            end_date="2026-06-08",
            protected_terms=["cap"],
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["keyword"], "free screen recorder")

    def test_search_terms_report_rejects_invalid_date_before_credentials(self):
        with self.assertRaises(ToolError):
            reports.search_terms_report(
                customer_id="1234567890",
                start_date="2026-06-XX",
                end_date="2026-06-08",
            )

    def test_search_terms_report_rejects_non_numeric_campaign_id(self):
        with self.assertRaises(ToolError):
            reports.search_terms_report(
                customer_id="1234567890",
                start_date="2026-06-01",
                end_date="2026-06-08",
                campaign_id="1 OR 1=1",
            )
