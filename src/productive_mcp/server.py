from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import FastMCP

from productive_mcp.client import ProductiveAPIError, ProductiveClient, ProductiveConfigError
from productive_mcp.models import normalize_comment, normalize_jsonapi_document

mcp = FastMCP("productive-mcp")

DEFAULT_CONFIG_PATH = "./.productive-mcp.json"

@dataclass(frozen=True)
class RuntimeConfigOverrides:
    api_token: str | None = None
    organization_id: str | None = None
    project_id: str | None = None
    base_url: str | None = None
    config_path: str | None = DEFAULT_CONFIG_PATH


_RUNTIME_OVERRIDES = RuntimeConfigOverrides()


def _set_runtime_overrides(overrides: RuntimeConfigOverrides) -> None:
    global _RUNTIME_OVERRIDES
    _RUNTIME_OVERRIDES = overrides


def _resolve_config_path(config_path: str | None) -> str | None:
    return config_path if config_path else _RUNTIME_OVERRIDES.config_path


def _create_client(config_path: str | None) -> ProductiveClient:
    return ProductiveClient.from_config_path(
        _resolve_config_path(config_path),
        api_token=_RUNTIME_OVERRIDES.api_token,
        organization_id=_RUNTIME_OVERRIDES.organization_id,
        project_id=_RUNTIME_OVERRIDES.project_id,
        base_url=_RUNTIME_OVERRIDES.base_url,
    )


def _split_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    parts = [item.strip() for item in value.split(",")]
    return [item for item in parts if item]


def _normalize_comments_document(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    comments: list[dict[str, Any]] = []
    if isinstance(data, list):
        comments = [normalize_comment(item) for item in data if isinstance(item, dict)]
    elif isinstance(data, dict):
        comments = [normalize_comment(data)]
    return {
        "items": comments,
        "meta": payload.get("meta") or {},
        "links": payload.get("links") or {},
        "included": payload.get("included") or [],
    }


def _handle_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ProductiveConfigError):
        return {"ok": False, "error": str(exc), "error_type": "config_error"}
    if isinstance(exc, ProductiveAPIError):
        return {
            "ok": False,
            "error": str(exc),
            "error_type": "api_error",
            "status_code": exc.status_code,
            "details": exc.details,
        }
    return {"ok": False, "error": f"Unexpected error: {exc}", "error_type": "unexpected_error"}


def _parse_server_args() -> RuntimeConfigOverrides:
    parser = argparse.ArgumentParser(description="Productive MCP server")
    parser.add_argument("--api-token", dest="api_token", help="Productive API token")
    parser.add_argument("--organization-id", dest="organization_id", help="Productive organization ID")
    parser.add_argument("--project-id", dest="project_id", help="Default Productive project ID")
    parser.add_argument("--base-url", dest="base_url", help="Productive API base URL")
    parser.add_argument(
        "--config-path",
        dest="config_path",
        default=DEFAULT_CONFIG_PATH,
        help="Path to .productive-mcp.json",
    )
    args, _unknown = parser.parse_known_args()
    return RuntimeConfigOverrides(
        api_token=args.api_token,
        organization_id=args.organization_id,
        project_id=args.project_id,
        base_url=args.base_url,
        config_path=args.config_path,
    )


@mcp.tool()
async def productive_test_connection(config_path: str | None = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Validate Productive credentials from args/env/config."""
    try:
        async with _create_client(config_path) as client:
            payload = await client.test_connection()
        return {
            "ok": True,
            "message": "Connection successful.",
            "meta": payload.get("meta") or {},
        }
    except Exception as exc:
        return _handle_error(exc)


@mcp.tool()
async def productive_list_tasks(
    filters: dict[str, Any] | None = None,
    filter_ops: dict[str, dict[str, Any]] | None = None,
    sort: str | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    include: str | None = None,
    fields: dict[str, list[str] | str] | None = None,
    config_path: str | None = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    """List Productive tasks with filter/sort/pagination/include/fields support."""
    try:
        async with _create_client(config_path) as client:
            payload = await client.list_tasks(
                filters=filters,
                filter_ops=filter_ops,
                sort=sort,
                page_number=page_number,
                page_size=page_size,
                include=_split_csv(include),
                fields=fields,
            )
        return {"ok": True, **normalize_jsonapi_document(payload)}
    except Exception as exc:
        return _handle_error(exc)


@mcp.tool()
async def productive_get_task(
    task_reference: str,
    lookup_by: str = "task_number",
    include: str | None = None,
    fields: dict[str, list[str] | str] | None = None,
    include_comments: bool = False,
    comments_page_size: int = 50,
    config_path: str | None = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    """Fetch one Productive task by task_number (default) or by id, with optional comments."""
    try:
        async with _create_client(config_path) as client:
            task_payload = await client.get_task(
                task_reference,
                lookup_by=lookup_by,
                include=_split_csv(include),
                fields=fields,
            )
            task = normalize_jsonapi_document(task_payload)

            if not include_comments:
                return {"ok": True, **task}

            item = task.get("item")
            resolved_task_id = item.get("id") if isinstance(item, dict) else None
            if not resolved_task_id:
                return {
                    "ok": False,
                    "error": "Unable to resolve task id for comments lookup.",
                    "error_type": "unexpected_error",
                }

            comments_payload = await client.list_task_comments(
                task_id=resolved_task_id,
                page_size=comments_page_size,
                include=["person"],
            )
            comments = _normalize_comments_document(comments_payload)
            return {"ok": True, **task, "comments": comments}
    except Exception as exc:
        return _handle_error(exc)


@mcp.tool()
async def productive_list_task_comments(
    task_id: str,
    sort: str | None = "created_at",
    page_number: int | None = None,
    page_size: int | None = None,
    include: str | None = "person",
    config_path: str | None = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    """List comments for a Productive task."""
    try:
        async with _create_client(config_path) as client:
            payload = await client.list_task_comments(
                task_id=task_id,
                sort=sort,
                page_number=page_number,
                page_size=page_size,
                include=_split_csv(include),
            )
        return {"ok": True, **_normalize_comments_document(payload)}
    except Exception as exc:
        return _handle_error(exc)


def _compact_lookup(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_jsonapi_document(payload)
    items = normalized.get("items") or []
    compact_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        attrs = item.get("attributes") or {}
        compact_items.append(
            {
                "id": item.get("id"),
                "type": item.get("type"),
                "name": attrs.get("name"),
                "code": attrs.get("code"),
                "email": attrs.get("email"),
                "state": attrs.get("state"),
            }
        )

    return {
        "items": compact_items,
        "meta": normalized.get("meta") or {},
        "links": normalized.get("links") or {},
    }


@mcp.tool()
async def productive_list_projects(
    filters: dict[str, Any] | None = None,
    sort: str | None = None,
    page_number: int | None = None,
    page_size: int | None = 50,
    config_path: str | None = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    """List projects for resolving Productive task relationship IDs."""
    try:
        async with _create_client(config_path) as client:
            payload = await client.list_projects(
                filters=filters,
                sort=sort,
                page_number=page_number,
                page_size=page_size,
            )
        return {"ok": True, **_compact_lookup(payload)}
    except Exception as exc:
        return _handle_error(exc)


@mcp.tool()
async def productive_list_task_lists(
    filters: dict[str, Any] | None = None,
    sort: str | None = None,
    page_number: int | None = None,
    page_size: int | None = 50,
    config_path: str | None = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    """List task lists for resolving Productive task relationship IDs."""
    try:
        async with _create_client(config_path) as client:
            payload = await client.list_task_lists(
                filters=filters,
                sort=sort,
                page_number=page_number,
                page_size=page_size,
            )
        return {"ok": True, **_compact_lookup(payload)}
    except Exception as exc:
        return _handle_error(exc)


@mcp.tool()
async def productive_list_workflow_statuses(
    filters: dict[str, Any] | None = None,
    sort: str | None = None,
    page_number: int | None = None,
    page_size: int | None = 50,
    config_path: str | None = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    """List workflow statuses for resolving Productive task relationship IDs."""
    try:
        async with _create_client(config_path) as client:
            payload = await client.list_workflow_statuses(
                filters=filters,
                sort=sort,
                page_number=page_number,
                page_size=page_size,
            )
        return {"ok": True, **_compact_lookup(payload)}
    except Exception as exc:
        return _handle_error(exc)

@mcp.tool()
async def productive_list_custom_fields(
    config_path: str | None = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    """List all custom fields for tasks in the configured project, with their available options.

    Returns each field's id, name, data_type_id, and options (for select/multi-select fields).
    Data types: 1=text, 2=number, 3=select, 4=date, 5=multi-select, 6=person, 7=attachment.
    """
    try:
        async with _create_client(config_path) as client:
            cf_data = await client.list_all_custom_fields()
            result: list[dict[str, Any]] = []
            for cf in cf_data:
                if not isinstance(cf, dict):
                    continue
                attrs = cf.get("attributes") or {}
                data_type = attrs.get("data_type_id")
                field_info: dict[str, Any] = {
                    "id": cf.get("id"),
                    "name": attrs.get("name"),
                    "data_type_id": data_type,
                }
                # Fetch options for select / multi-select fields
                if data_type in (3, 5):
                    options_data = await client.list_all_custom_field_options(cf["id"])
                    field_info["options"] = [
                        {"id": opt.get("id"), "name": (opt.get("attributes") or {}).get("name")}
                        for opt in options_data
                        if isinstance(opt, dict)
                    ]
                result.append(field_info)
        return {"ok": True, "items": result}
    except Exception as exc:
        return _handle_error(exc)


@mcp.tool()
async def productive_find_tasks(
    status_name: str | None = None,
    custom_field_filters: dict[str, str] | None = None,
    project_id: str | None = None,
    page_number: int | None = None,
    page_size: int | None = 50,
    include: str | None = None,
    fields: dict[str, list[str] | str] | None = None,
    config_path: str | None = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    """Find tasks by workflow status name and/or custom field values.

    Examples:
      - Find all 'In Progress' tasks: status_name="In Progress"
      - Find tasks in Sprint 4: custom_field_filters={"Sprint": "Sprint 4"}
      - Combine: status_name="In Progress", custom_field_filters={"Sprint": "Sprint 4", "Platform": "Flutter"}

    Status and custom field names are matched case-insensitively.
    """
    try:
        async with _create_client(config_path) as client:
            task_filters: dict[str, Any] = {}
            custom_field_params: dict[str, str] = {}

            if project_id:
                task_filters["project_id"] = project_id

            # Resolve status name → workflow_status_id
            if status_name:
                ws_payload = await client.list_workflow_statuses(page_size=200)
                ws_data = ws_payload.get("data") or []
                matched_ids: list[str] = []
                for ws in ws_data:
                    if not isinstance(ws, dict):
                        continue
                    attrs = ws.get("attributes") or {}
                    name = attrs.get("name") or ""
                    if name.lower() == status_name.lower():
                        matched_ids.append(ws["id"])
                if not matched_ids:
                    return {
                        "ok": False,
                        "error": f"No workflow status found matching '{status_name}'.",
                        "error_type": "not_found",
                    }
                task_filters["workflow_status_id"] = ",".join(matched_ids)

            # Resolve custom field names → filter[custom_fields][id][eq]=value
            # For select/multi-select fields, resolve option name → option id
            if custom_field_filters:
                cf_data = await client.list_all_custom_fields()
                cf_lookup: dict[str, tuple[str, int]] = {}  # lowercase name → (id, data_type_id)
                for cf in cf_data:
                    if not isinstance(cf, dict):
                        continue
                    attrs = cf.get("attributes") or {}
                    cf_name = attrs.get("name") or ""
                    cf_lookup[cf_name.lower()] = (cf["id"], attrs.get("data_type_id", 0))

                for field_name, field_value in custom_field_filters.items():
                    cf_entry = cf_lookup.get(field_name.lower())
                    if not cf_entry:
                        return {
                            "ok": False,
                            "error": f"No custom field found matching '{field_name}'.",
                            "error_type": "not_found",
                        }
                    cf_id, data_type = cf_entry
                    resolved_value = field_value

                    # Select (3) and multi-select (5) need option ID, not name
                    if data_type in (3, 5):
                        options = await client.list_all_custom_field_options(cf_id)
                        option_id: str | None = None
                        for opt in options:
                            if not isinstance(opt, dict):
                                continue
                            opt_name = (opt.get("attributes") or {}).get("name") or ""
                            if opt_name.lower() == field_value.lower():
                                option_id = opt["id"]
                                break
                        if not option_id:
                            return {
                                "ok": False,
                                "error": f"No option '{field_value}' found for custom field '{field_name}'.",
                                "error_type": "not_found",
                            }
                        resolved_value = option_id

                    custom_field_params[f"filter[custom_fields][{cf_id}][eq]"] = resolved_value

            payload = await client.list_tasks(
                filters=task_filters or None,
                page_number=page_number,
                page_size=page_size,
                include=_split_csv(include),
                fields=fields,
                extra_params=custom_field_params or None,
            )
        return {"ok": True, **normalize_jsonapi_document(payload)}
    except Exception as exc:
        return _handle_error(exc)


@mcp.tool()
async def productive_list_people(
    filters: dict[str, Any] | None = None,
    sort: str | None = None,
    page_number: int | None = None,
    page_size: int | None = 50,
    config_path: str | None = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    """List people for resolving Productive relationship IDs."""
    try:
        async with _create_client(config_path) as client:
            payload = await client.list_people(
                filters=filters,
                sort=sort,
                page_number=page_number,
                page_size=page_size,
            )
        return {"ok": True, **_compact_lookup(payload)}
    except Exception as exc:
        return _handle_error(exc)


def main() -> None:
    _set_runtime_overrides(_parse_server_args())
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
