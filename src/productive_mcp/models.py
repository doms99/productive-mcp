from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://api.productive.io"
DEFAULT_CONFIG_FILE = ".productive-mcp.json"


class ProductiveConfigError(ValueError):
    """Raised when local Productive MCP config is missing or invalid."""


class ProductiveAPIError(RuntimeError):
    """Raised when Productive API returns an error response."""

    def __init__(self, message: str, status_code: int | None = None, details: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.details = details


@dataclass(frozen=True)
class ProductiveConfig:
    api_token: str
    organization_id: str
    base_url: str = DEFAULT_BASE_URL
    project_id: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProductiveConfig":
        token = payload.get("PRODUCTIVE_API_TOKEN")
        organization_id = payload.get("PRODUCTIVE_ORGANIZATION_ID")
        base_url = payload.get("PRODUCTIVE_BASE_URL") or DEFAULT_BASE_URL
        project_id = payload.get("PRODUCTIVE_PROJECT_ID")

        if not isinstance(token, str) or not token.strip():
            raise ProductiveConfigError("Missing required key: PRODUCTIVE_API_TOKEN")
        if not isinstance(organization_id, str) or not organization_id.strip():
            raise ProductiveConfigError("Missing required key: PRODUCTIVE_ORGANIZATION_ID")
        if not isinstance(base_url, str) or not base_url.strip():
            raise ProductiveConfigError("PRODUCTIVE_BASE_URL must be a non-empty string when provided")
        if project_id is not None and (not isinstance(project_id, str) or not project_id.strip()):
            raise ProductiveConfigError("PRODUCTIVE_PROJECT_ID must be a non-empty string when provided")

        return cls(
            api_token=token.strip(),
            organization_id=organization_id.strip(),
            base_url=base_url.strip().rstrip("/"),
            project_id=project_id.strip() if isinstance(project_id, str) else None,
        )


def resolve_default_config_path() -> Path:
    local_path = Path.cwd() / DEFAULT_CONFIG_FILE
    if local_path.exists():
        return local_path
    return Path.home() / DEFAULT_CONFIG_FILE


def normalize_relationship(relationship_payload: dict[str, Any]) -> Any:
    data = relationship_payload.get("data")
    if data is None:
        return None
    if isinstance(data, dict):
        return {"id": data.get("id"), "type": data.get("type")}
    if isinstance(data, list):
        normalized_items: list[dict[str, Any]] = []
        for item in data:
            if isinstance(item, dict):
                normalized_items.append({"id": item.get("id"), "type": item.get("type")})
        return normalized_items
    return None


def normalize_resource(resource: dict[str, Any]) -> dict[str, Any]:
    relationships = resource.get("relationships") or {}
    normalized_relationships = {
        key: normalize_relationship(value)
        for key, value in relationships.items()
        if isinstance(value, dict)
    }
    attrs = resource.get("attributes") or {}
    result: dict[str, Any] = {
        "id": resource.get("id"),
        "type": resource.get("type"),
    }
    if attrs.get("task_number") is not None:
        result["task_number"] = attrs["task_number"]
    result["attributes"] = attrs
    result["relationships"] = normalized_relationships
    return result


def normalize_jsonapi_document(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    included = payload.get("included") or []
    links = payload.get("links") or {}
    meta = payload.get("meta") or {}

    if isinstance(data, list):
        normalized_data: Any = [normalize_resource(item) for item in data if isinstance(item, dict)]
    elif isinstance(data, dict):
        normalized_data = normalize_resource(data)
    else:
        normalized_data = data

    normalized_included = [normalize_resource(item) for item in included if isinstance(item, dict)]
    return {
        "items" if isinstance(normalized_data, list) else "item": normalized_data,
        "included": normalized_included,
        "links": links,
        "meta": meta,
    }


def normalize_comment(resource: dict[str, Any]) -> dict[str, Any]:
    base = normalize_resource(resource)
    attributes = base["attributes"]
    return {
        "id": base["id"],
        "type": base["type"],
        "body": attributes.get("body"),
        "created_at": attributes.get("created_at"),
        "updated_at": attributes.get("updated_at"),
        "relationships": base["relationships"],
        "attributes": attributes,
    }
