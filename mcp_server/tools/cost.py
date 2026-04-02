import json
import os
from datetime import date, timedelta
from pathlib import Path

_MOCK_PATH = Path(__file__).parent.parent / "mock" / "cost.json"

_VALID_PERIODS = ("today", "7d", "30d")


def get_cost_summary(period: str = "7d") -> dict:
    """Fetch cost summary from Azure Cost Management.

    Args:
        period: Aggregation period — "today", "7d", or "30d".

    Returns:
        CostSummary dict, or a ToolError dict on Azure API failure.
    """
    if period not in _VALID_PERIODS:
        return {
            "error": True,
            "tool": "get_cost_summary",
            "message": f"Invalid period '{period}'. Must be one of: {', '.join(_VALID_PERIODS)}.",
            "azure_error_code": None,
        }

    if os.getenv("USE_MOCK", "").lower() == "true":
        return _get_mock_cost(period)
    return _get_azure_cost(period)


def _get_mock_cost(period: str) -> dict:
    base: dict = json.loads(_MOCK_PATH.read_text())
    start, end = _period_dates(period)
    return {**base, "period": period, "start_date": str(start), "end_date": str(end)}


def _get_azure_cost(period: str) -> dict:
    try:
        from azure.identity import ManagedIdentityCredential
        from azure.mgmt.costmanagement import CostManagementClient
        from azure.mgmt.costmanagement.models import (
            ExportType,
            GranularityType,
            QueryDataset,
            QueryDefinition,
            QueryGrouping,
            QueryTimePeriod,
            TimeframeType,
        )
    except ImportError as e:
        return {
            "error": True,
            "tool": "get_cost_summary",
            "message": f"Required Azure SDK package not installed: {e}",
            "azure_error_code": None,
        }

    subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID", "")
    client_id = os.getenv("AZURE_CLIENT_ID") or None
    start, end = _period_dates(period)

    try:
        credential = ManagedIdentityCredential(client_id=client_id)
        client = CostManagementClient(credential)
        scope = f"/subscriptions/{subscription_id}"

        def _query(group_by_column: str) -> list[dict]:
            query_def = QueryDefinition(
                type=ExportType.ACTUAL_COST,
                timeframe=TimeframeType.CUSTOM,
                time_period=QueryTimePeriod(from_property=start, to=end),
                dataset=QueryDataset(
                    granularity=GranularityType.NONE,
                    grouping=[QueryGrouping(type="Dimension", name=group_by_column)],
                ),
            )
            result = client.query.usage(scope=scope, parameters=query_def)
            rows = result.rows or []
            cols = [c.name.lower() for c in (result.columns or [])]
            return [dict(zip(cols, row)) for row in rows]

        service_rows = _query("ServiceName")
        rg_rows = _query("ResourceGroupName")

        currency = service_rows[0].get("currency", "USD") if service_rows else "USD"
        total_cost = sum(r.get("cost", r.get("pretaxcost", 0)) for r in service_rows)

        by_service = sorted(
            [
                {
                    "service_name": r.get("servicename", r.get("servicename", "")),
                    "cost": r.get("cost", r.get("pretaxcost", 0)),
                    "currency": r.get("currency", currency),
                }
                for r in service_rows
            ],
            key=lambda x: x["cost"],
            reverse=True,
        )
        by_rg = sorted(
            [
                {
                    "resource_group": r.get("resourcegroupname", ""),
                    "cost": r.get("cost", r.get("pretaxcost", 0)),
                    "currency": r.get("currency", currency),
                }
                for r in rg_rows
            ],
            key=lambda x: x["cost"],
            reverse=True,
        )

        return {
            "period": period,
            "start_date": str(start),
            "end_date": str(end),
            "total_cost": total_cost,
            "currency": currency,
            "by_service": by_service,
            "by_resource_group": by_rg,
        }

    except Exception as e:
        azure_error_code = getattr(getattr(e, "error", None), "code", None)
        return {
            "error": True,
            "tool": "get_cost_summary",
            "message": f"Failed to fetch cost summary: {e}",
            "azure_error_code": azure_error_code,
        }


def _period_dates(period: str) -> tuple[date, date]:
    today = date.today()
    if period == "today":
        return today, today
    if period == "7d":
        return today - timedelta(days=6), today
    # 30d
    return today - timedelta(days=29), today
