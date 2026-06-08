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

"""Recommendation tools for Google Ads."""

from typing import Any, Dict, List, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v24.enums.types import (
    advertising_channel_type,
    recommendation_type,
)
from google.ads.googleads.v24.services.types import recommendation_service
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils

recommendations_mcp = FastMCP("recommendations")

AdvertisingChannelType = Literal[
    "SEARCH",
    "DISPLAY",
    "PERFORMANCE_MAX",
    "DEMAND_GEN",
    "VIDEO",
    "SHOPPING",
]


def _clean_customer_id(customer_id: str) -> str:
    return customer_id.replace("-", "").strip()


def _format_google_ads_exception(ex: GoogleAdsException) -> str:
    error_msgs = [
        f"Google Ads API Error: {error.message}" for error in ex.failure.errors
    ]
    return f"Request ID: {ex.request_id}\n" + "\n".join(error_msgs)


def _advertising_channel_type_value(channel_type: AdvertisingChannelType) -> int:
    return getattr(
        advertising_channel_type.AdvertisingChannelTypeEnum.AdvertisingChannelType,
        channel_type,
    )


def _recommendation_type_value(value: str) -> int:
    cleaned = value.strip().upper()
    if not cleaned:
        raise ToolError("recommendation_types cannot include empty values.")
    try:
        return getattr(
            recommendation_type.RecommendationTypeEnum.RecommendationType,
            cleaned,
        )
    except AttributeError as ex:
        raise ToolError(f"Unknown recommendation type: {value}") from ex


@recommendations_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def generate_recommendations(
    customer_id: str,
    recommendation_types: List[str] | None = None,
    advertising_channel_type: AdvertisingChannelType = "SEARCH",
    country_codes: List[str] | None = None,
    language_codes: List[str] | None = None,
    positive_location_ids: List[int] | None = None,
    negative_location_ids: List[int] | None = None,
    target_partner_search_network: bool = False,
    target_content_network: bool = False,
    is_new_customer: bool = False,
) -> List[Dict[str, Any]]:
    """Generates Google Ads recommendations for an account or proposed setup.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        recommendation_types: Optional recommendation type names to request.
        advertising_channel_type: Channel type for generated recommendations.
        country_codes: Optional ISO country codes.
        language_codes: Optional language codes.
        positive_location_ids: Optional positive geo target IDs.
        negative_location_ids: Optional negative geo target IDs.
        target_partner_search_network: Whether Search partners are targeted.
        target_content_network: Whether Display Network content is targeted.
        is_new_customer: Whether this is for a new customer setup.
    """

    service = utils.get_googleads_service("RecommendationService")
    request = recommendation_service.GenerateRecommendationsRequest()
    request.customer_id = _clean_customer_id(customer_id)
    request.advertising_channel_type = _advertising_channel_type_value(
        advertising_channel_type
    )
    request.target_partner_search_network = target_partner_search_network
    request.target_content_network = target_content_network
    request.is_new_customer = is_new_customer

    if recommendation_types:
        request.recommendation_types.extend(
            [_recommendation_type_value(value) for value in recommendation_types]
        )
    request.country_codes.extend(
        [value.strip().upper() for value in country_codes or []]
    )
    request.language_codes.extend([value.strip() for value in language_codes or []])
    request.positive_locations_ids.extend(positive_location_ids or [])
    request.negative_locations_ids.extend(negative_location_ids or [])

    try:
        response = service.generate_recommendations(request=request)
        return [
            utils.format_output_value(recommendation)
            for recommendation in response.recommendations
        ]
    except GoogleAdsException as ex:
        raise ToolError(_format_google_ads_exception(ex)) from ex
