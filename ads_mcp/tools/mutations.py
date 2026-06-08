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

"""Guarded mutation tools for managing Google Ads accounts."""

from typing import Any, Dict, List, Literal
import os

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v24.common.types import ad_asset
from google.ads.googleads.v24.enums.types import (
    ad_group_criterion_status,
    ad_group_ad_status,
    ad_group_status,
    ad_group_type,
    advertising_channel_type,
    budget_delivery_method,
    campaign_status,
    keyword_match_type,
)
from google.ads.googleads.v24.services.types import (
    ad_group_ad_service as ad_group_ad_service_types,
    ad_group_criterion_service as ad_group_criterion_service_types,
    ad_group_service as ad_group_service_types,
    campaign_budget_service as campaign_budget_service_types,
    campaign_criterion_service as campaign_criterion_service_types,
    campaign_service as campaign_service_types,
)
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils

mutations_mcp = FastMCP("mutations")

_ENABLE_MUTATIONS_ENV_VAR = "GOOGLE_ADS_MCP_ENABLE_MUTATIONS"
_TRUE_VALUES = {"1", "true", "yes", "on"}

AdGroupAdStatus = Literal["ENABLED", "PAUSED"]
AdGroupCriterionStatus = Literal["ENABLED", "PAUSED"]
AdGroupStatus = Literal["ENABLED", "PAUSED"]
CampaignStatus = Literal["ENABLED", "PAUSED"]
KeywordMatchType = Literal["BROAD", "PHRASE", "EXACT"]


def _clean_customer_id(customer_id: str) -> str:
    return customer_id.replace("-", "").strip()


def _require_real_mutation_enabled(validate_only: bool) -> None:
    if validate_only:
        return

    enabled = os.environ.get(_ENABLE_MUTATIONS_ENV_VAR, "").lower()
    if enabled not in _TRUE_VALUES:
        raise ToolError(
            f"Real Google Ads mutations are disabled. Set "
            f"{_ENABLE_MUTATIONS_ENV_VAR}=true and call the tool with "
            "validate_only=false after reviewing the proposed change."
        )


def _validate_non_empty(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ToolError(f"{field_name} must not be empty.")
    return cleaned


def _validate_positive_micros(value: int, field_name: str) -> int:
    if value <= 0:
        raise ToolError(f"{field_name} must be greater than zero.")
    return value


def _validate_keywords(keywords: List[str]) -> List[str]:
    cleaned = [keyword.strip() for keyword in keywords if keyword.strip()]
    if not cleaned:
        raise ToolError("At least one keyword is required.")
    if len(cleaned) > 200:
        raise ToolError("At most 200 keywords can be sent in one call.")
    return cleaned


def _format_google_ads_exception(ex: GoogleAdsException) -> str:
    error_msgs = [
        f"Google Ads API Error: {error.message}" for error in ex.failure.errors
    ]
    return f"Request ID: {ex.request_id}\n" + "\n".join(error_msgs)


def _format_mutate_response(
    response: Any, validate_only: bool, operation_count: int
) -> Dict[str, Any]:
    return {
        "validate_only": validate_only,
        "operation_count": operation_count,
        "resource_names": [
            result.resource_name for result in getattr(response, "results", [])
        ],
    }


def _execute_mutate(
    service: Any,
    method_name: str,
    customer_id: str,
    operations: List[Any],
    validate_only: bool,
) -> Dict[str, Any]:
    _require_real_mutation_enabled(validate_only)
    method = getattr(service, method_name)
    request = {
        "customer_id": _clean_customer_id(customer_id),
        "operations": operations,
        "validate_only": validate_only,
    }

    try:
        response = method(request=request)
        return _format_mutate_response(response, validate_only, len(operations))
    except GoogleAdsException as ex:
        raise ToolError(_format_google_ads_exception(ex)) from ex


@mutations_mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    )
)
def create_campaign_budget(
    customer_id: str,
    name: str,
    amount_micros: int,
    explicitly_shared: bool = False,
    validate_only: bool = True,
) -> Dict[str, Any]:
    """Creates a campaign budget.

    The default validate_only=true sends the request to Google Ads validation
    without creating anything. Set validate_only=false only after review and
    with GOOGLE_ADS_MCP_ENABLE_MUTATIONS=true.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        name: The budget name.
        amount_micros: The daily budget amount in account currency micros.
        explicitly_shared: Whether the budget can be shared by multiple campaigns.
        validate_only: Whether Google Ads should validate without applying the mutation.
    """

    _require_real_mutation_enabled(validate_only)
    cleaned_name = _validate_non_empty(name, "name")
    cleaned_amount_micros = _validate_positive_micros(amount_micros, "amount_micros")

    budget_service = utils.get_googleads_service("CampaignBudgetService")
    operation = campaign_budget_service_types.CampaignBudgetOperation()
    budget = operation.create
    budget.name = cleaned_name
    budget.amount_micros = cleaned_amount_micros
    budget.delivery_method = (
        budget_delivery_method.BudgetDeliveryMethodEnum.BudgetDeliveryMethod.STANDARD
    )
    budget.explicitly_shared = explicitly_shared

    return _execute_mutate(
        budget_service,
        "mutate_campaign_budgets",
        customer_id,
        [operation],
        validate_only,
    )


@mutations_mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    )
)
def create_paused_search_campaign(
    customer_id: str,
    name: str,
    campaign_budget_resource_name: str,
    target_google_search: bool = True,
    target_search_network: bool = False,
    target_partner_search_network: bool = False,
    target_content_network: bool = False,
    validate_only: bool = True,
) -> Dict[str, Any]:
    """Creates a paused Search campaign attached to an existing campaign budget.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        name: The campaign name.
        campaign_budget_resource_name: Full resource name from campaign budget creation or search.
        target_google_search: Whether to target Google Search.
        target_search_network: Whether to target the Search Network.
        target_partner_search_network: Whether to target search partners.
        target_content_network: Whether to target Display Network content.
        validate_only: Whether Google Ads should validate without applying the mutation.
    """

    _require_real_mutation_enabled(validate_only)
    cleaned_name = _validate_non_empty(name, "name")
    cleaned_campaign_budget_resource_name = _validate_non_empty(
        campaign_budget_resource_name, "campaign_budget_resource_name"
    )

    campaign_service = utils.get_googleads_service("CampaignService")
    operation = campaign_service_types.CampaignOperation()
    campaign = operation.create
    campaign.name = cleaned_name
    campaign.status = campaign_status.CampaignStatusEnum.CampaignStatus.PAUSED
    campaign.advertising_channel_type = (
        advertising_channel_type.AdvertisingChannelTypeEnum.AdvertisingChannelType.SEARCH
    )
    campaign.campaign_budget = cleaned_campaign_budget_resource_name
    campaign.manual_cpc.enhanced_cpc_enabled = True
    campaign.network_settings.target_google_search = target_google_search
    campaign.network_settings.target_search_network = target_search_network
    campaign.network_settings.target_partner_search_network = (
        target_partner_search_network
    )
    campaign.network_settings.target_content_network = target_content_network

    return _execute_mutate(
        campaign_service,
        "mutate_campaigns",
        customer_id,
        [operation],
        validate_only,
    )


@mutations_mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    )
)
def create_ad_group(
    customer_id: str,
    campaign_id: str,
    name: str,
    cpc_bid_micros: int | None = None,
    status: AdGroupStatus = "PAUSED",
    validate_only: bool = True,
) -> Dict[str, Any]:
    """Creates a Search ad group in a campaign.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        campaign_id: Numeric campaign ID.
        name: The ad group name.
        cpc_bid_micros: Optional CPC bid in account currency micros.
        status: ENABLED or PAUSED.
        validate_only: Whether Google Ads should validate without applying the mutation.
    """

    _require_real_mutation_enabled(validate_only)
    cleaned_campaign_id = _validate_non_empty(campaign_id, "campaign_id")
    cleaned_name = _validate_non_empty(name, "name")
    cleaned_cpc_bid_micros = (
        _validate_positive_micros(cpc_bid_micros, "cpc_bid_micros")
        if cpc_bid_micros is not None
        else None
    )

    ad_group_service = utils.get_googleads_service("AdGroupService")
    operation = ad_group_service_types.AdGroupOperation()
    ad_group = operation.create
    ad_group.name = cleaned_name
    ad_group.campaign = ad_group_service.campaign_path(
        _clean_customer_id(customer_id), cleaned_campaign_id
    )
    ad_group.status = getattr(ad_group_status.AdGroupStatusEnum.AdGroupStatus, status)
    ad_group.type_ = ad_group_type.AdGroupTypeEnum.AdGroupType.SEARCH_STANDARD

    if cleaned_cpc_bid_micros is not None:
        ad_group.cpc_bid_micros = cleaned_cpc_bid_micros

    return _execute_mutate(
        ad_group_service,
        "mutate_ad_groups",
        customer_id,
        [operation],
        validate_only,
    )


@mutations_mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    )
)
def add_ad_group_keywords(
    customer_id: str,
    ad_group_id: str,
    keywords: List[str],
    match_type: KeywordMatchType = "EXACT",
    status: AdGroupCriterionStatus = "PAUSED",
    validate_only: bool = True,
) -> Dict[str, Any]:
    """Adds keywords to an ad group.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        ad_group_id: Numeric ad group ID.
        keywords: Keyword texts to add.
        match_type: BROAD, PHRASE, or EXACT.
        status: ENABLED or PAUSED.
        validate_only: Whether Google Ads should validate without applying the mutation.
    """

    _require_real_mutation_enabled(validate_only)
    cleaned_ad_group_id = _validate_non_empty(ad_group_id, "ad_group_id")
    cleaned_keywords = _validate_keywords(keywords)

    ad_group_criterion_service = utils.get_googleads_service("AdGroupCriterionService")
    operations = []

    for keyword in cleaned_keywords:
        operation = ad_group_criterion_service_types.AdGroupCriterionOperation()
        criterion = operation.create
        criterion.ad_group = ad_group_criterion_service.ad_group_path(
            _clean_customer_id(customer_id),
            cleaned_ad_group_id,
        )
        criterion.status = getattr(
            ad_group_criterion_status.AdGroupCriterionStatusEnum.AdGroupCriterionStatus,
            status,
        )
        criterion.keyword.text = keyword
        criterion.keyword.match_type = getattr(
            keyword_match_type.KeywordMatchTypeEnum.KeywordMatchType,
            match_type,
        )
        operations.append(operation)

    return _execute_mutate(
        ad_group_criterion_service,
        "mutate_ad_group_criteria",
        customer_id,
        operations,
        validate_only,
    )


@mutations_mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    )
)
def create_responsive_search_ad(
    customer_id: str,
    ad_group_id: str,
    final_urls: List[str],
    headlines: List[str],
    descriptions: List[str],
    path1: str | None = None,
    path2: str | None = None,
    status: AdGroupAdStatus = "PAUSED",
    validate_only: bool = True,
) -> Dict[str, Any]:
    """Creates a responsive search ad in an ad group.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        ad_group_id: Numeric ad group ID.
        final_urls: Final URLs for the ad.
        headlines: Responsive search ad headlines, minimum 3 and maximum 15.
        descriptions: Responsive search ad descriptions, minimum 2 and maximum 4.
        path1: Optional first display URL path.
        path2: Optional second display URL path.
        status: ENABLED or PAUSED.
        validate_only: Whether Google Ads should validate without applying the mutation.
    """

    _require_real_mutation_enabled(validate_only)
    cleaned_ad_group_id = _validate_non_empty(ad_group_id, "ad_group_id")

    cleaned_final_urls = [
        final_url.strip() for final_url in final_urls if final_url.strip()
    ]
    if not cleaned_final_urls:
        raise ToolError("At least one final URL is required.")

    cleaned_headlines = [headline.strip() for headline in headlines if headline.strip()]
    if len(cleaned_headlines) < 3 or len(cleaned_headlines) > 15:
        raise ToolError("Responsive search ads require 3 to 15 headlines.")

    cleaned_descriptions = [
        description.strip() for description in descriptions if description.strip()
    ]
    if len(cleaned_descriptions) < 2 or len(cleaned_descriptions) > 4:
        raise ToolError("Responsive search ads require 2 to 4 descriptions.")

    ad_group_ad_service = utils.get_googleads_service("AdGroupAdService")
    operation = ad_group_ad_service_types.AdGroupAdOperation()
    ad_group_ad = operation.create
    ad_group_ad.ad_group = ad_group_ad_service.ad_group_path(
        _clean_customer_id(customer_id),
        cleaned_ad_group_id,
    )
    ad_group_ad.status = getattr(
        ad_group_ad_status.AdGroupAdStatusEnum.AdGroupAdStatus, status
    )
    ad_group_ad.ad.final_urls.extend(cleaned_final_urls)

    if path1:
        ad_group_ad.ad.responsive_search_ad.path1 = path1.strip()
    if path2:
        ad_group_ad.ad.responsive_search_ad.path2 = path2.strip()

    for headline in cleaned_headlines:
        asset = ad_asset.AdTextAsset()
        asset.text = headline
        ad_group_ad.ad.responsive_search_ad.headlines.append(asset)

    for description in cleaned_descriptions:
        asset = ad_asset.AdTextAsset()
        asset.text = description
        ad_group_ad.ad.responsive_search_ad.descriptions.append(asset)

    return _execute_mutate(
        ad_group_ad_service,
        "mutate_ad_group_ads",
        customer_id,
        [operation],
        validate_only,
    )


@mutations_mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=True,
    )
)
def set_campaign_status(
    customer_id: str,
    campaign_id: str,
    status: CampaignStatus,
    validate_only: bool = True,
) -> Dict[str, Any]:
    """Sets a campaign to ENABLED or PAUSED.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        campaign_id: Numeric campaign ID.
        status: ENABLED or PAUSED.
        validate_only: Whether Google Ads should validate without applying the mutation.
    """

    _require_real_mutation_enabled(validate_only)
    cleaned_campaign_id = _validate_non_empty(campaign_id, "campaign_id")

    campaign_service = utils.get_googleads_service("CampaignService")
    operation = campaign_service_types.CampaignOperation()
    campaign = operation.update
    campaign.resource_name = campaign_service.campaign_path(
        _clean_customer_id(customer_id),
        cleaned_campaign_id,
    )
    campaign.status = getattr(campaign_status.CampaignStatusEnum.CampaignStatus, status)
    operation.update_mask.paths.append("status")

    return _execute_mutate(
        campaign_service,
        "mutate_campaigns",
        customer_id,
        [operation],
        validate_only,
    )


@mutations_mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=True,
    )
)
def set_ad_group_status(
    customer_id: str,
    ad_group_id: str,
    status: AdGroupStatus,
    validate_only: bool = True,
) -> Dict[str, Any]:
    """Sets an ad group to ENABLED or PAUSED.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        ad_group_id: Numeric ad group ID.
        status: ENABLED or PAUSED.
        validate_only: Whether Google Ads should validate without applying the mutation.
    """

    _require_real_mutation_enabled(validate_only)
    cleaned_ad_group_id = _validate_non_empty(ad_group_id, "ad_group_id")

    ad_group_service = utils.get_googleads_service("AdGroupService")
    operation = ad_group_service_types.AdGroupOperation()
    ad_group = operation.update
    ad_group.resource_name = ad_group_service.ad_group_path(
        _clean_customer_id(customer_id),
        cleaned_ad_group_id,
    )
    ad_group.status = getattr(ad_group_status.AdGroupStatusEnum.AdGroupStatus, status)
    operation.update_mask.paths.append("status")

    return _execute_mutate(
        ad_group_service,
        "mutate_ad_groups",
        customer_id,
        [operation],
        validate_only,
    )


@mutations_mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=True,
    )
)
def set_campaign_budget_amount(
    customer_id: str,
    campaign_budget_id: str,
    amount_micros: int,
    validate_only: bool = True,
) -> Dict[str, Any]:
    """Updates a campaign budget amount.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        campaign_budget_id: Numeric campaign budget ID.
        amount_micros: The daily budget amount in account currency micros.
        validate_only: Whether Google Ads should validate without applying the mutation.
    """

    _require_real_mutation_enabled(validate_only)
    cleaned_campaign_budget_id = _validate_non_empty(
        campaign_budget_id, "campaign_budget_id"
    )
    cleaned_amount_micros = _validate_positive_micros(amount_micros, "amount_micros")

    budget_service = utils.get_googleads_service("CampaignBudgetService")
    operation = campaign_budget_service_types.CampaignBudgetOperation()
    budget = operation.update
    budget.resource_name = budget_service.campaign_budget_path(
        _clean_customer_id(customer_id),
        cleaned_campaign_budget_id,
    )
    budget.amount_micros = cleaned_amount_micros
    operation.update_mask.paths.append("amount_micros")

    return _execute_mutate(
        budget_service,
        "mutate_campaign_budgets",
        customer_id,
        [operation],
        validate_only,
    )


@mutations_mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    )
)
def add_campaign_negative_keywords(
    customer_id: str,
    campaign_id: str,
    keywords: List[str],
    match_type: KeywordMatchType = "EXACT",
    validate_only: bool = True,
) -> Dict[str, Any]:
    """Adds campaign-level negative keywords.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        campaign_id: Numeric campaign ID.
        keywords: Negative keyword texts to add.
        match_type: BROAD, PHRASE, or EXACT.
        validate_only: Whether Google Ads should validate without applying the mutation.
    """

    _require_real_mutation_enabled(validate_only)
    cleaned_campaign_id = _validate_non_empty(campaign_id, "campaign_id")
    cleaned_keywords = _validate_keywords(keywords)

    campaign_criterion_service = utils.get_googleads_service("CampaignCriterionService")
    operations = []

    for keyword in cleaned_keywords:
        operation = campaign_criterion_service_types.CampaignCriterionOperation()
        criterion = operation.create
        criterion.campaign = campaign_criterion_service.campaign_path(
            _clean_customer_id(customer_id),
            cleaned_campaign_id,
        )
        criterion.negative = True
        criterion.keyword.text = keyword
        criterion.keyword.match_type = getattr(
            keyword_match_type.KeywordMatchTypeEnum.KeywordMatchType,
            match_type,
        )
        operations.append(operation)

    return _execute_mutate(
        campaign_criterion_service,
        "mutate_campaign_criteria",
        customer_id,
        operations,
        validate_only,
    )
