import json
import os
from pathlib import Path

_SEVERITY_LABELS = {
    0: "Critical",
    1: "Error",
    2: "Warning",
    3: "Informational",
    4: "Verbose",
}

_MOCK_PATH = Path(__file__).parent.parent / "mock" / "alerts.json"


def get_alerts(
    resource_group: str | None = None,
    severity: int | None = None,
) -> list[dict]:
    """Fetch active alerts from Azure Monitor.

    Args:
        resource_group: Filter by resource group name.
        severity: Filter by severity level (0=Critical, 4=Verbose).

    Returns:
        List of Alert dicts, or a ToolError dict on Azure API failure.
    """
    if os.getenv("USE_MOCK", "").lower() == "true":
        return _get_mock_alerts(resource_group, severity)
    return _get_azure_alerts(resource_group, severity)


def _get_mock_alerts(
    resource_group: str | None,
    severity: int | None,
) -> list[dict]:
    alerts: list[dict] = json.loads(_MOCK_PATH.read_text())
    if resource_group is not None:
        alerts = [a for a in alerts if a["resource_group"] == resource_group]
    if severity is not None:
        alerts = [a for a in alerts if a["severity"] == severity]
    return alerts


def _get_azure_alerts(
    resource_group: str | None,
    severity: int | None,
) -> list[dict] | dict:
    try:
        from azure.identity import ManagedIdentityCredential
        from azure.mgmt.alertsmanagement import AlertsManagementClient
    except ImportError as e:
        return {
            "error": True,
            "tool": "get_alerts",
            "message": f"Required Azure SDK package not installed: {e}",
            "azure_error_code": None,
        }

    subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID", "")
    client_id = os.getenv("AZURE_CLIENT_ID") or None

    try:
        credential = ManagedIdentityCredential(client_id=client_id)
        client = AlertsManagementClient(credential, subscription_id)

        raw_alerts = list(client.alerts.get_all())
        alerts = []
        for alert in raw_alerts:
            props = alert.properties
            sev = int(props.severity.lstrip("Sev")) if props.severity else None
            rg = _extract_resource_group(alert.id or "")
            if resource_group is not None and rg != resource_group:
                continue
            if severity is not None and sev != severity:
                continue
            alerts.append(
                {
                    "id": alert.id or "",
                    "name": alert.name or "",
                    "severity": sev,
                    "severity_label": _SEVERITY_LABELS.get(sev, "Unknown") if sev is not None else "Unknown",
                    "state": props.alert_state or "",
                    "resource_id": props.target_resource or "",
                    "resource_group": rg,
                    "resource_type": (props.target_resource_type or "").lower(),
                    "description": props.description or "",
                    "fired_at": props.start_date_time.isoformat() if props.start_date_time else "",
                    "resolved_at": props.resolved_date_time.isoformat() if props.resolved_date_time else None,
                }
            )
        return alerts

    except Exception as e:
        azure_error_code = getattr(getattr(e, "error", None), "code", None)
        return {
            "error": True,
            "tool": "get_alerts",
            "message": f"Failed to fetch alerts: {e}",
            "azure_error_code": azure_error_code,
        }


def _extract_resource_group(resource_id: str) -> str:
    parts = resource_id.lower().split("/")
    try:
        idx = parts.index("resourcegroups")
        return resource_id.split("/")[idx + 1]
    except (ValueError, IndexError):
        return ""
