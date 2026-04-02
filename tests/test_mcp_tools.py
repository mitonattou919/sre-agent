"""Unit tests for MCP Server tools (mock mode)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_server.tools.alerts import get_alerts
from mcp_server.tools.cost import get_cost_summary

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_ALERTS_PATH = Path(__file__).parent.parent / "mcp_server" / "mock" / "alerts.json"
_MOCK_COST_PATH = Path(__file__).parent.parent / "mcp_server" / "mock" / "cost.json"


@pytest.fixture(autouse=True)
def use_mock_mode(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "true")


# ---------------------------------------------------------------------------
# get_alerts
# ---------------------------------------------------------------------------


class TestGetAlerts:
    def test_returns_list(self):
        result = get_alerts()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_alert_schema(self):
        alerts = get_alerts()
        required = {
            "id", "name", "severity", "severity_label",
            "state", "resource_id", "resource_group",
            "resource_type", "description", "fired_at", "resolved_at",
        }
        for alert in alerts:
            assert required <= set(alert.keys()), f"Missing keys in {alert}"

    def test_filter_by_resource_group(self):
        all_alerts = get_alerts()
        rg = all_alerts[0]["resource_group"]
        filtered = get_alerts(resource_group=rg)
        assert all(a["resource_group"] == rg for a in filtered)

    def test_filter_by_nonexistent_resource_group(self):
        result = get_alerts(resource_group="rg-does-not-exist")
        assert result == []

    def test_filter_by_severity(self):
        all_alerts = get_alerts()
        sev = all_alerts[0]["severity"]
        filtered = get_alerts(severity=sev)
        assert all(a["severity"] == sev for a in filtered)

    def test_filter_by_nonexistent_severity(self):
        result = get_alerts(severity=4)
        # Mock data has no Verbose alerts — result may be empty
        assert isinstance(result, list)

    def test_severity_label_mapping(self):
        labels = {0: "Critical", 1: "Error", 2: "Warning", 3: "Informational", 4: "Verbose"}
        for alert in get_alerts():
            expected = labels.get(alert["severity"])
            assert alert["severity_label"] == expected

    def test_azure_api_failure_returns_tool_error(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "false")
        monkeypatch.setenv("AZURE_SUBSCRIPTION_ID", "fake-sub")

        mock_credential = MagicMock()
        mock_client = MagicMock()
        mock_client.alerts.get_all.side_effect = Exception("AuthorizationFailed")

        with patch("mcp_server.tools.alerts.ManagedIdentityCredential", return_value=mock_credential), \
             patch("mcp_server.tools.alerts.AlertsManagementClient", return_value=mock_client):
            result = get_alerts()

        assert isinstance(result, dict)
        assert result["error"] is True
        assert result["tool"] == "get_alerts"
        assert "message" in result


# ---------------------------------------------------------------------------
# get_cost_summary
# ---------------------------------------------------------------------------


class TestGetCostSummary:
    def test_returns_dict(self):
        result = get_cost_summary()
        assert isinstance(result, dict)

    def test_cost_summary_schema(self):
        result = get_cost_summary()
        required = {"period", "start_date", "end_date", "total_cost", "currency",
                    "by_service", "by_resource_group"}
        assert required <= set(result.keys())

    @pytest.mark.parametrize("period", ["today", "7d", "30d"])
    def test_valid_periods(self, period):
        result = get_cost_summary(period=period)
        assert result["period"] == period
        assert "start_date" in result
        assert "end_date" in result

    def test_today_start_equals_end(self):
        result = get_cost_summary(period="today")
        assert result["start_date"] == result["end_date"]

    def test_7d_date_range(self):
        from datetime import date, timedelta
        result = get_cost_summary(period="7d")
        start = date.fromisoformat(result["start_date"])
        end = date.fromisoformat(result["end_date"])
        assert (end - start).days == 6

    def test_30d_date_range(self):
        from datetime import date, timedelta
        result = get_cost_summary(period="30d")
        start = date.fromisoformat(result["start_date"])
        end = date.fromisoformat(result["end_date"])
        assert (end - start).days == 29

    def test_invalid_period_returns_tool_error(self):
        result = get_cost_summary(period="monthly")
        assert isinstance(result, dict)
        assert result["error"] is True
        assert result["tool"] == "get_cost_summary"

    def test_by_service_is_list(self):
        result = get_cost_summary()
        assert isinstance(result["by_service"], list)
        for item in result["by_service"]:
            assert {"service_name", "cost", "currency"} <= set(item.keys())

    def test_by_resource_group_is_list(self):
        result = get_cost_summary()
        assert isinstance(result["by_resource_group"], list)
        for item in result["by_resource_group"]:
            assert {"resource_group", "cost", "currency"} <= set(item.keys())

    def test_azure_api_failure_returns_tool_error(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "false")
        monkeypatch.setenv("AZURE_SUBSCRIPTION_ID", "fake-sub")

        mock_credential = MagicMock()
        mock_client = MagicMock()
        mock_client.query.usage.side_effect = Exception("AuthorizationFailed")

        with patch("mcp_server.tools.cost.ManagedIdentityCredential", return_value=mock_credential), \
             patch("mcp_server.tools.cost.CostManagementClient", return_value=mock_client):
            result = get_cost_summary()

        assert isinstance(result, dict)
        assert result["error"] is True
        assert result["tool"] == "get_cost_summary"
