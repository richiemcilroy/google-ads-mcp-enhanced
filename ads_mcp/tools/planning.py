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

"""Keyword planning tools for Google Ads."""

from typing import Any, Dict, List, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v24.common.types import criteria
from google.ads.googleads.v24.enums.types import (
    keyword_match_type,
    keyword_plan_network,
)
from google.ads.googleads.v24.services.types import keyword_plan_idea_service
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils

planning_mcp = FastMCP("planning")

KeywordMatchType = Literal["BROAD", "PHRASE", "EXACT"]
KeywordPlanNetwork = Literal["GOOGLE_SEARCH", "GOOGLE_SEARCH_AND_PARTNERS"]
ForecastBiddingStrategy = Literal[
    "MANUAL_CPC", "MAXIMIZE_CLICKS", "MAXIMIZE_CONVERSIONS"
]


def _clean_customer_id(customer_id: str) -> str:
    return customer_id.replace("-", "").strip()


def _resource_name(prefix: str, value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ToolError(f"{prefix} value must not be empty.")
    if "/" in cleaned:
        return cleaned
    return f"{prefix}/{cleaned}"


def _resource_names(prefix: str, values: List[str] | None) -> List[str]:
    return [_resource_name(prefix, value) for value in values or []]


def _keyword_plan_network_value(network: KeywordPlanNetwork) -> int:
    return getattr(
        keyword_plan_network.KeywordPlanNetworkEnum.KeywordPlanNetwork,
        network,
    )


def _keyword_match_type_value(match_type: KeywordMatchType) -> int:
    return getattr(
        keyword_match_type.KeywordMatchTypeEnum.KeywordMatchType,
        match_type,
    )


def _format_google_ads_exception(ex: GoogleAdsException) -> str:
    error_msgs = [
        f"Google Ads API Error: {error.message}" for error in ex.failure.errors
    ]
    return f"Request ID: {ex.request_id}\n" + "\n".join(error_msgs)


def _format_message(message: Any) -> Dict[str, Any]:
    return utils.format_output_value(message)


def _clean_strings(values: List[str] | None, field_name: str) -> List[str]:
    cleaned = [value.strip() for value in values or [] if value.strip()]
    return cleaned


def _require_strings(values: List[str], field_name: str) -> List[str]:
    if not values:
        raise ToolError(f"{field_name} must include at least one non-empty value.")
    return values


def _apply_geo_language(
    request: Any,
    language_constant_id: str | None,
    geo_target_constant_ids: List[str] | None,
) -> None:
    if language_constant_id:
        request.language = _resource_name("languageConstants", language_constant_id)
    request.geo_target_constants.extend(
        _resource_names("geoTargetConstants", geo_target_constant_ids)
    )


@planning_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def generate_keyword_ideas(
    customer_id: str,
    seed_keywords: List[str] | None = None,
    page_url: str | None = None,
    site_url: str | None = None,
    language_constant_id: str | None = "1000",
    geo_target_constant_ids: List[str] | None = None,
    network: KeywordPlanNetwork = "GOOGLE_SEARCH",
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """Generates keyword ideas with volume, competition, and bid estimates.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        seed_keywords: Seed keyword texts.
        page_url: A page URL for URL or keyword-and-URL seeding.
        site_url: A site URL for site-wide seeding.
        language_constant_id: Language constant ID or resource name. Defaults to English.
        geo_target_constant_ids: Geo target constant IDs or resource names.
        network: GOOGLE_SEARCH or GOOGLE_SEARCH_AND_PARTNERS.
        page_size: Maximum keyword ideas to return.
    """

    cleaned_keywords = _clean_strings(seed_keywords, "seed_keywords")
    if page_size <= 0 or page_size > 10000:
        raise ToolError("page_size must be between 1 and 10000.")
    if not cleaned_keywords and not page_url and not site_url:
        raise ToolError("Provide seed_keywords, page_url, or site_url.")
    if site_url and (cleaned_keywords or page_url):
        raise ToolError("site_url cannot be combined with seed_keywords or page_url.")

    service = utils.get_googleads_service("KeywordPlanIdeaService")
    request = keyword_plan_idea_service.GenerateKeywordIdeasRequest()
    request.customer_id = _clean_customer_id(customer_id)
    request.keyword_plan_network = _keyword_plan_network_value(network)
    request.page_size = page_size
    _apply_geo_language(request, language_constant_id, geo_target_constant_ids)

    if cleaned_keywords and page_url:
        request.keyword_and_url_seed.keywords.extend(cleaned_keywords)
        request.keyword_and_url_seed.url = page_url.strip()
    elif cleaned_keywords:
        request.keyword_seed.keywords.extend(cleaned_keywords)
    elif page_url:
        request.url_seed.url = page_url.strip()
    elif site_url:
        request.site_seed.site = site_url.strip()

    try:
        results = []
        for result in service.generate_keyword_ideas(request=request):
            results.append(_format_message(result))
            if len(results) >= page_size:
                break
        return results
    except GoogleAdsException as ex:
        raise ToolError(_format_google_ads_exception(ex)) from ex


@planning_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_keyword_historical_metrics(
    customer_id: str,
    keywords: List[str],
    language_constant_id: str | None = "1000",
    geo_target_constant_ids: List[str] | None = None,
    network: KeywordPlanNetwork = "GOOGLE_SEARCH",
) -> Dict[str, Any]:
    """Returns historical search volume, competition, and bid estimates.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        keywords: Keyword texts to inspect.
        language_constant_id: Language constant ID or resource name. Defaults to English.
        geo_target_constant_ids: Geo target constant IDs or resource names.
        network: GOOGLE_SEARCH or GOOGLE_SEARCH_AND_PARTNERS.
    """

    cleaned_keywords = _require_strings(
        _clean_strings(keywords, "keywords"), "keywords"
    )
    service = utils.get_googleads_service("KeywordPlanIdeaService")
    request = keyword_plan_idea_service.GenerateKeywordHistoricalMetricsRequest()
    request.customer_id = _clean_customer_id(customer_id)
    request.keywords.extend(cleaned_keywords)
    request.keyword_plan_network = _keyword_plan_network_value(network)
    _apply_geo_language(request, language_constant_id, geo_target_constant_ids)

    try:
        response = service.generate_keyword_historical_metrics(request=request)
        return _format_message(response)
    except GoogleAdsException as ex:
        raise ToolError(_format_google_ads_exception(ex)) from ex


@planning_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def forecast_keyword_plan(
    customer_id: str,
    keywords: List[str],
    currency_code: str,
    daily_budget_micros: int,
    max_cpc_bid_micros: int | None = None,
    language_constant_ids: List[str] | None = None,
    geo_target_constant_ids: List[str] | None = None,
    match_type: KeywordMatchType = "EXACT",
    bidding_strategy: ForecastBiddingStrategy = "MANUAL_CPC",
) -> Dict[str, Any]:
    """Forecasts clicks, impressions, cost, and conversions for keywords.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        keywords: Keyword texts to forecast.
        currency_code: Account currency code, for example USD.
        daily_budget_micros: Daily spend target in currency micros.
        max_cpc_bid_micros: Optional max CPC ceiling for manual CPC or maximize clicks.
        language_constant_ids: Language constant IDs or resource names.
        geo_target_constant_ids: Geo target constant IDs or resource names.
        match_type: BROAD, PHRASE, or EXACT.
        bidding_strategy: MANUAL_CPC, MAXIMIZE_CLICKS, or MAXIMIZE_CONVERSIONS.
    """

    cleaned_keywords = _require_strings(
        _clean_strings(keywords, "keywords"), "keywords"
    )
    if daily_budget_micros <= 0:
        raise ToolError("daily_budget_micros must be greater than zero.")
    if max_cpc_bid_micros is not None and max_cpc_bid_micros <= 0:
        raise ToolError("max_cpc_bid_micros must be greater than zero when set.")

    service = utils.get_googleads_service("KeywordPlanIdeaService")
    request = keyword_plan_idea_service.GenerateKeywordForecastMetricsRequest()
    request.customer_id = _clean_customer_id(customer_id)
    request.currency_code = currency_code.strip().upper()
    request.campaign.language_constants.extend(
        _resource_names("languageConstants", language_constant_ids or ["1000"])
    )
    request.campaign.geo_target_constants.extend(
        _resource_names("geoTargetConstants", geo_target_constant_ids)
    )

    if bidding_strategy == "MANUAL_CPC":
        strategy = request.campaign.bidding_strategy.manual_cpc_bidding_strategy
        strategy.daily_budget_micros = daily_budget_micros
        if max_cpc_bid_micros is not None:
            strategy.max_cpc_bid_micros = max_cpc_bid_micros
    elif bidding_strategy == "MAXIMIZE_CLICKS":
        strategy = request.campaign.bidding_strategy.maximize_clicks_bidding_strategy
        strategy.daily_target_spend_micros = daily_budget_micros
        if max_cpc_bid_micros is not None:
            strategy.max_cpc_bid_ceiling_micros = max_cpc_bid_micros
    else:
        request.campaign.bidding_strategy.maximize_conversions_bidding_strategy.daily_target_spend_micros = (
            daily_budget_micros
        )

    ad_group = keyword_plan_idea_service.ForecastAdGroup()
    for keyword in cleaned_keywords:
        keyword_info = criteria.KeywordInfo()
        keyword_info.text = keyword
        keyword_info.match_type = _keyword_match_type_value(match_type)
        ad_group.keywords.append(keyword_info)
    request.campaign.ad_groups.append(ad_group)

    try:
        response = service.generate_keyword_forecast_metrics(request=request)
        return _format_message(response)
    except GoogleAdsException as ex:
        raise ToolError(_format_google_ads_exception(ex)) from ex
