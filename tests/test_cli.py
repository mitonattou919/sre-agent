"""Unit tests for CLI commands."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from cli.main import cli

_CHAT_RESPONSE = {
    "reply": "## Active Alerts\nNo active alerts.",
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "tool_calls": ["get_alerts"],
}
_COST_RESPONSE = {
    "reply": "## Cost Summary\nTotal: ¥12,453.",
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "tool_calls": ["get_cost_summary"],
}


@pytest.fixture(autouse=True)
def skip_auth_env(monkeypatch):
    monkeypatch.setenv("SKIP_AUTH", "true")
    monkeypatch.setenv("ORCHESTRATOR_URL", "http://localhost:8000")


@pytest.fixture()
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# sre-agent alerts
# ---------------------------------------------------------------------------


class TestAlerts:
    def test_calls_chat_endpoint(self, runner):
        with patch("cli.client.chat", return_value=_CHAT_RESPONSE) as mock_chat:
            result = runner.invoke(cli, ["alerts"])
        assert result.exit_code == 0
        mock_chat.assert_called_once()
        args, _ = mock_chat.call_args
        assert "alert" in args[0].lower()

    def test_with_resource_group_option(self, runner):
        with patch("cli.client.chat", return_value=_CHAT_RESPONSE) as mock_chat:
            result = runner.invoke(cli, ["alerts", "--resource-group", "rg-prod"])
        assert result.exit_code == 0
        args, _ = mock_chat.call_args
        assert "rg-prod" in args[0]

    def test_with_severity_option(self, runner):
        with patch("cli.client.chat", return_value=_CHAT_RESPONSE) as mock_chat:
            result = runner.invoke(cli, ["alerts", "--severity", "0"])
        assert result.exit_code == 0
        args, _ = mock_chat.call_args
        assert "0" in args[0]

    def test_renders_tool_call(self, runner):
        with patch("cli.client.chat", return_value=_CHAT_RESPONSE):
            result = runner.invoke(cli, ["alerts"])
        assert "get_alerts" in result.output

    def test_auth_error_exits_1(self, runner):
        with patch("cli.client.chat", side_effect=SystemExit(1)):
            result = runner.invoke(cli, ["alerts"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# sre-agent cost
# ---------------------------------------------------------------------------


class TestCost:
    def test_default_period_7d(self, runner):
        with patch("cli.client.chat", return_value=_COST_RESPONSE) as mock_chat:
            result = runner.invoke(cli, ["cost"])
        assert result.exit_code == 0
        args, _ = mock_chat.call_args
        assert "7d" in args[0]

    @pytest.mark.parametrize("period", ["today", "7d", "30d"])
    def test_valid_periods(self, runner, period):
        with patch("cli.client.chat", return_value=_COST_RESPONSE) as mock_chat:
            result = runner.invoke(cli, ["cost", "--period", period])
        assert result.exit_code == 0
        args, _ = mock_chat.call_args
        assert period in args[0]

    def test_invalid_period_exits_2(self, runner):
        result = runner.invoke(cli, ["cost", "--period", "monthly"])
        assert result.exit_code == 2
        assert "monthly" in result.output.lower() or "invalid" in result.output.lower()

    def test_renders_tool_call(self, runner):
        with patch("cli.client.chat", return_value=_COST_RESPONSE):
            result = runner.invoke(cli, ["cost"])
        assert "get_cost_summary" in result.output


# ---------------------------------------------------------------------------
# sre-agent login
# ---------------------------------------------------------------------------


class TestLogin:
    def test_skip_auth_prints_message(self, runner):
        result = runner.invoke(cli, ["login"])
        assert result.exit_code == 0
        assert "SKIP_AUTH" in result.output.upper() or "skipped" in result.output.lower()
