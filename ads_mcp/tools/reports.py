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

"""Reporting tools for common Google Ads management workflows."""

from typing import Any, Dict, List
from datetime import date

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils

reports_mcp = FastMCP("reports")


def _clean_customer_id(customer_id: str) -> str:
    return customer_id.replace("-", "").strip()


def _format_google_ads_exception(ex: GoogleAdsException) -> str:
    error_msgs = [
        f"Google Ads API Error: {error.message}" for error in ex.failure.errors
    ]
    return f"Request ID: {ex.request_id}\n" + "\n".join(error_msgs)


def _run_gaql(customer_id: str, query: str) -> List[Dict[str, Any]]:
    ga_service = utils.get_googleads_service("GoogleAdsService")
    utils.logger.info(f"ads_mcp.reports query {query}")

    try:
        query_result = ga_service.search_stream(
            customer_id=_clean_customer_id(customer_id), query=query
        )
        rows = []
        for batch in query_result:
            for row in batch.results:
                rows.append(utils.format_output_row(row, batch.field_mask.paths))
        return rows
    except GoogleAdsException as ex:
        raise ToolError(_format_google_ads_exception(ex)) from ex


def _validate_date(value: str, field_name: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as ex:
        raise ToolError(f"{field_name} must be in YYYY-MM-DD format.") from ex


def _date_condition(start_date: str, end_date: str) -> str:
    start = _validate_date(start_date, "start_date")
    end = _validate_date(end_date, "end_date")
    return f"segments.date BETWEEN '{start}' AND '{end}'"


def _optional_id_condition(field_name: str, value: str | None) -> List[str]:
    if value:
        cleaned = value.strip()
        if not cleaned.isdigit():
            raise ToolError(f"{field_name} filter must be numeric.")
        return [f"{field_name} = {cleaned}"]
    return []


def _build_where(conditions: List[str]) -> str:
    if not conditions:
        return ""
    return " WHERE " + " AND ".join(conditions)


def _cost_micros(row: Dict[str, Any]) -> int:
    return int(row.get("metrics.cost_micros") or 0)


def _conversions(row: Dict[str, Any]) -> float:
    return float(row.get("metrics.conversions") or 0)


@reports_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def search_terms_report(
    customer_id: str,
    start_date: str,
    end_date: str,
    campaign_id: str | None = None,
    ad_group_id: str | None = None,
    min_cost_micros: int = 0,
    zero_conversions_only: bool = False,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Returns search terms with spend, clicks, conversions, and value.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        start_date: Inclusive start date in YYYY-MM-DD format.
        end_date: Inclusive end date in YYYY-MM-DD format.
        campaign_id: Optional numeric campaign ID filter.
        ad_group_id: Optional numeric ad group ID filter.
        min_cost_micros: Local post-filter minimum cost.
        zero_conversions_only: Whether to return only terms with zero conversions.
        limit: Maximum rows to request.
    """

    if limit <= 0 or limit > 10000:
        raise ToolError("limit must be between 1 and 10000.")

    conditions = [
        _date_condition(start_date, end_date),
        *_optional_id_condition("campaign.id", campaign_id),
        *_optional_id_condition("ad_group.id", ad_group_id),
    ]
    query = (
        "SELECT search_term_view.search_term, campaign.id, campaign.name, "
        "ad_group.id, ad_group.name, metrics.impressions, metrics.clicks, "
        "metrics.cost_micros, metrics.conversions, metrics.conversions_value "
        f"FROM search_term_view{_build_where(conditions)} "
        f"ORDER BY metrics.cost_micros DESC LIMIT {limit} "
        "PARAMETERS omit_unselected_resource_names=true"
    )
    rows = _run_gaql(customer_id, query)

    return [
        row
        for row in rows
        if _cost_micros(row) >= min_cost_micros
        and (not zero_conversions_only or _conversions(row) == 0)
    ]


@reports_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def negative_keyword_recommendations(
    customer_id: str,
    start_date: str,
    end_date: str,
    campaign_id: str | None = None,
    ad_group_id: str | None = None,
    min_cost_micros: int = 5000000,
    max_conversions: float = 0,
    protected_terms: List[str] | None = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Suggests negative keywords from costly low-conversion search terms.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        start_date: Inclusive start date in YYYY-MM-DD format.
        end_date: Inclusive end date in YYYY-MM-DD format.
        campaign_id: Optional numeric campaign ID filter.
        ad_group_id: Optional numeric ad group ID filter.
        min_cost_micros: Minimum cost before a term is considered.
        max_conversions: Maximum conversions before a term is considered waste.
        protected_terms: Terms that should never be recommended as negatives.
        limit: Maximum rows to inspect.
    """

    protected = [term.lower() for term in protected_terms or [] if term.strip()]
    rows = search_terms_report(
        customer_id=customer_id,
        start_date=start_date,
        end_date=end_date,
        campaign_id=campaign_id,
        ad_group_id=ad_group_id,
        min_cost_micros=min_cost_micros,
        zero_conversions_only=False,
        limit=limit,
    )
    recommendations = []

    for row in rows:
        term = str(row.get("search_term_view.search_term") or "").strip()
        if not term:
            continue
        lowered = term.lower()
        if any(protected_term in lowered for protected_term in protected):
            continue
        if _conversions(row) <= max_conversions:
            recommendations.append(
                {
                    "keyword": term,
                    "match_type": "EXACT",
                    "campaign_id": row.get("campaign.id"),
                    "ad_group_id": row.get("ad_group.id"),
                    "cost_micros": _cost_micros(row),
                    "conversions": _conversions(row),
                    "reason": "Cost threshold met with low or zero conversions.",
                }
            )

    return recommendations


@reports_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def change_history(
    customer_id: str,
    start_date: str,
    end_date: str,
    campaign_id: str | None = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """Returns recent Google Ads account changes.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        start_date: Inclusive start date in YYYY-MM-DD format.
        end_date: Inclusive end date in YYYY-MM-DD format.
        campaign_id: Optional numeric campaign ID filter.
        limit: Maximum rows to return. Google Ads requires change_event limits <= 10000.
    """

    if limit <= 0 or limit > 10000:
        raise ToolError("limit must be between 1 and 10000.")

    start = _validate_date(start_date, "start_date")
    end = _validate_date(end_date, "end_date")
    conditions = [
        f"change_event.change_date_time BETWEEN '{start} 00:00:00' AND '{end} 23:59:59'",
        *_optional_id_condition("campaign.id", campaign_id),
    ]
    query = (
        "SELECT change_event.change_date_time, change_event.user_email, "
        "change_event.client_type, change_event.resource_type, "
        "change_event.resource_change_operation, change_event.changed_fields, "
        "change_event.change_resource_name, campaign.id, campaign.name "
        f"FROM change_event{_build_where(conditions)} "
        f"ORDER BY change_event.change_date_time DESC LIMIT {limit} "
        "PARAMETERS omit_unselected_resource_names=true"
    )
    return _run_gaql(customer_id, query)


@reports_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def ad_policy_and_strength_report(
    customer_id: str,
    campaign_id: str | None = None,
    ad_group_id: str | None = None,
    include_removed: bool = False,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """Returns ad status, policy summary, ad strength, and action items.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        campaign_id: Optional numeric campaign ID filter.
        ad_group_id: Optional numeric ad group ID filter.
        include_removed: Whether to include removed ads.
        limit: Maximum rows to return.
    """

    if limit <= 0 or limit > 10000:
        raise ToolError("limit must be between 1 and 10000.")

    conditions = [
        *_optional_id_condition("campaign.id", campaign_id),
        *_optional_id_condition("ad_group.id", ad_group_id),
    ]
    if not include_removed:
        conditions.append("ad_group_ad.status != 'REMOVED'")

    query = (
        "SELECT campaign.id, campaign.name, ad_group.id, ad_group.name, "
        "ad_group_ad.ad.id, ad_group_ad.status, ad_group_ad.primary_status, "
        "ad_group_ad.primary_status_reasons, ad_group_ad.ad_strength, "
        "ad_group_ad.action_items, ad_group_ad.policy_summary.approval_status, "
        "ad_group_ad.policy_summary.policy_topic_entries "
        f"FROM ad_group_ad{_build_where(conditions)} "
        f"ORDER BY campaign.name ASC LIMIT {limit} "
        "PARAMETERS omit_unselected_resource_names=true"
    )
    return _run_gaql(customer_id, query)


@reports_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def budget_pacing_report(
    customer_id: str,
    start_date: str,
    end_date: str,
    campaign_id: str | None = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """Returns campaign spend, conversions, and budget fields for pacing checks.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        start_date: Inclusive start date in YYYY-MM-DD format.
        end_date: Inclusive end date in YYYY-MM-DD format.
        campaign_id: Optional numeric campaign ID filter.
        limit: Maximum rows to return.
    """

    if limit <= 0 or limit > 10000:
        raise ToolError("limit must be between 1 and 10000.")

    conditions = [
        _date_condition(start_date, end_date),
        *_optional_id_condition("campaign.id", campaign_id),
    ]
    query = (
        "SELECT campaign.id, campaign.name, campaign.status, "
        "campaign_budget.id, campaign_budget.name, campaign_budget.amount_micros, "
        "metrics.impressions, metrics.clicks, metrics.cost_micros, "
        "metrics.conversions, metrics.conversions_value "
        f"FROM campaign{_build_where(conditions)} "
        f"ORDER BY metrics.cost_micros DESC LIMIT {limit} "
        "PARAMETERS omit_unselected_resource_names=true"
    )
    return _run_gaql(customer_id, query)
