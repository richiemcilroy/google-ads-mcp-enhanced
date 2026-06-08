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

"""Offline conversion upload tools for Google Ads."""

from typing import Any, Dict, List
import os

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v24.services.types import conversion_upload_service
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils

conversions_mcp = FastMCP("conversions")

_ENABLE_MUTATIONS_ENV_VAR = "GOOGLE_ADS_MCP_ENABLE_MUTATIONS"
_TRUE_VALUES = {"1", "true", "yes", "on"}


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
            "validate_only=false after reviewing the upload."
        )


def _conversion_action_resource_name(customer_id: str, conversion_action: str) -> str:
    cleaned = conversion_action.strip()
    if not cleaned:
        raise ToolError("conversion_action must not be empty.")
    if "/" in cleaned:
        return cleaned
    return f"customers/{_clean_customer_id(customer_id)}/conversionActions/{cleaned}"


def _format_google_ads_exception(ex: GoogleAdsException) -> str:
    error_msgs = [
        f"Google Ads API Error: {error.message}" for error in ex.failure.errors
    ]
    return f"Request ID: {ex.request_id}\n" + "\n".join(error_msgs)


def _get_required_string(conversion: Dict[str, Any], field_name: str) -> str:
    value = str(conversion.get(field_name) or "").strip()
    if not value:
        raise ToolError(f"Each conversion must include {field_name}.")
    return value


def _get_float(conversion: Dict[str, Any], field_name: str) -> float:
    value = conversion.get(field_name)
    if value is None:
        raise ToolError(f"Each conversion must include {field_name}.")
    try:
        return float(value)
    except (TypeError, ValueError) as ex:
        raise ToolError(f"{field_name} must be numeric.") from ex


def _apply_click_id(upload: Any, conversion: Dict[str, Any]) -> None:
    click_id_fields = [
        field_name
        for field_name in ["gclid", "gbraid", "wbraid"]
        if conversion.get(field_name)
    ]
    if len(click_id_fields) != 1:
        raise ToolError(
            "Each conversion must include exactly one of gclid, gbraid, or wbraid."
        )

    field_name = click_id_fields[0]
    setattr(upload, field_name, str(conversion[field_name]).strip())


@conversions_mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    )
)
def upload_click_conversions(
    customer_id: str,
    conversion_action: str,
    conversions: List[Dict[str, Any]],
    validate_only: bool = True,
    partial_failure: bool = True,
    job_id: int | None = None,
) -> Dict[str, Any]:
    """Uploads offline click conversions using gclid, gbraid, or wbraid.

    Each conversion object must include exactly one click ID field (`gclid`,
    `gbraid`, or `wbraid`), plus `conversion_date_time`, `conversion_value`, and
    `currency_code`. `order_id` is optional but recommended for deduplication.

    Args:
        customer_id: The Google Ads customer ID without punctuation.
        conversion_action: Conversion action ID or full resource name.
        conversions: Conversion objects to upload.
        validate_only: Whether Google Ads should validate without applying the upload.
        partial_failure: Whether valid conversions should upload when some rows fail.
        job_id: Optional upload job ID.
    """

    _require_real_mutation_enabled(validate_only)
    if not conversions:
        raise ToolError("At least one conversion is required.")
    if len(conversions) > 2000:
        raise ToolError("At most 2000 conversions can be sent in one upload.")

    cleaned_customer_id = _clean_customer_id(customer_id)
    action_resource_name = _conversion_action_resource_name(
        cleaned_customer_id, conversion_action
    )
    request = conversion_upload_service.UploadClickConversionsRequest()
    request.customer_id = cleaned_customer_id
    request.partial_failure = partial_failure
    request.validate_only = validate_only
    if job_id is not None:
        request.job_id = job_id

    for conversion in conversions:
        upload = conversion_upload_service.ClickConversion()
        _apply_click_id(upload, conversion)
        upload.conversion_action = action_resource_name
        upload.conversion_date_time = _get_required_string(
            conversion, "conversion_date_time"
        )
        upload.conversion_value = _get_float(conversion, "conversion_value")
        upload.currency_code = _get_required_string(conversion, "currency_code").upper()
        if conversion.get("order_id"):
            upload.order_id = str(conversion["order_id"]).strip()
        request.conversions.append(upload)

    service = utils.get_googleads_service("ConversionUploadService")

    try:
        response = service.upload_click_conversions(request=request)
        return {
            "validate_only": validate_only,
            "job_id": response.job_id,
            "partial_failure_error": utils.format_output_value(
                response.partial_failure_error
            ),
            "results": utils.format_output_value(response.results),
        }
    except GoogleAdsException as ex:
        raise ToolError(_format_google_ads_exception(ex)) from ex
