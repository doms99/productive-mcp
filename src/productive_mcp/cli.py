from __future__ import annotations

import asyncio
import json
from typing import Any

import typer
from markdownify import markdownify
from rich.console import Console
from rich.markdown import Markdown

from productive_mcp.client import ProductiveAPIError, ProductiveClient, ProductiveConfigError
from productive_mcp.models import normalize_comment, normalize_jsonapi_document

app = typer.Typer(help="Productive MCP companion CLI.")
_console = Console()


def _render_html(html: str) -> None:
    """Convert HTML to markdown, then render with rich."""
    md = markdownify(html).strip()
    if md:
        _console.print(Markdown(md))
    else:
        typer.echo("<empty>")


def _html_to_plain(html: str) -> str:
    """Convert HTML to a plain-text one-liner for summaries."""
    return markdownify(html).strip()

def _print_json(payload: Any) -> None:
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=True))


def _parse_filters(entries: list[str] | None) -> dict[str, str] | None:
    if not entries:
        return None
    parsed: dict[str, str] = {}
    for entry in entries:
        if "=" not in entry:
            raise typer.BadParameter(f"Invalid --filter value '{entry}'. Expected key=value.")
        key, value = entry.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed or None


def _parse_filter_ops(entries: list[str] | None) -> dict[str, dict[str, str]] | None:
    if not entries:
        return None
    parsed: dict[str, dict[str, str]] = {}
    for entry in entries:
        if ":" not in entry:
            raise typer.BadParameter(f"Invalid --filter-op value '{entry}'. Expected field:operator:value.")
        first_split = entry.split(":", 2)
        if len(first_split) != 3:
            raise typer.BadParameter(f"Invalid --filter-op value '{entry}'. Expected field:operator:value.")
        field_name, operator, value = [part.strip() for part in first_split]
        parsed.setdefault(field_name, {})[operator] = value
    return parsed or None


def _parse_fields(entries: list[str] | None) -> dict[str, list[str]] | None:
    if not entries:
        return None
    parsed: dict[str, list[str]] = {}
    for entry in entries:
        if ":" not in entry:
            raise typer.BadParameter(f"Invalid --field value '{entry}'. Expected resource:field1,field2.")
        resource, values = entry.split(":", 1)
        parsed[resource.strip()] = [item.strip() for item in values.split(",") if item.strip()]
    return parsed or None


def _summarize_items(payload: dict[str, Any]) -> None:
    items = payload.get("items") or []
    included = payload.get("included") or []

    # Build lookup: (type, id) → resource
    included_lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for inc in included:
        if isinstance(inc, dict):
            included_lookup[(inc.get("type", ""), inc.get("id", ""))] = inc

    typer.echo(f"Items: {len(items)}")
    for item in items:
        if not isinstance(item, dict):
            continue
        attrs = item.get("attributes") or {}
        name = attrs.get("name") or attrs.get("title") or attrs.get("email") or "<no-name>"
        task_number = item.get("task_number")
        prefix = f"#{task_number} " if task_number else ""
        typer.echo(f"- {item.get('type')}:{item.get('id')}  {prefix}{name}")

        # Print resolved included relationships
        relationships = item.get("relationships") or {}
        for rel_name, rel_data in relationships.items():
            if rel_data is None:
                continue
            refs = rel_data if isinstance(rel_data, list) else [rel_data]
            for ref in refs:
                if not isinstance(ref, dict):
                    continue
                inc = included_lookup.get((ref.get("type", ""), ref.get("id", "")))
                if not inc:
                    continue
                inc_attrs = inc.get("attributes") or {}
                label = inc_attrs.get("name") or inc_attrs.get("title") or inc_attrs.get("email") or ref.get("id")
                typer.echo(f"    {rel_name}: {label}")


async def _run_with_client(config_path: str | None, runner):
    async with ProductiveClient.from_config_path(config_path) as client:
        return await runner(client)


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, ProductiveConfigError):
        typer.echo(f"Config error: {exc}", err=True)
        raise typer.Exit(code=2)
    if isinstance(exc, ProductiveAPIError):
        typer.echo(f"API error ({exc.status_code}): {exc}", err=True)
        if exc.details is not None:
            _print_json(exc.details)
        raise typer.Exit(code=1)
    typer.echo(f"Unexpected error: {exc}", err=True)
    raise typer.Exit(code=1)


@app.command("test-connection")
def test_connection(
    config_path: str | None = typer.Option(None, help="Path to .productive-mcp.json"),
    raw: bool = typer.Option(False, "--raw", help="Print raw JSON"),
) -> None:
    async def _runner(client: ProductiveClient) -> dict[str, Any]:
        return await client.test_connection()

    try:
        payload = asyncio.run(_run_with_client(config_path, _runner))
        if raw:
            _print_json(payload)
            return
        count = len(payload.get("data") or [])
        typer.echo(f"Connection successful. Sample people records: {count}")
    except Exception as exc:
        _handle_error(exc)


@app.command("list-tasks")
def list_tasks(
    config_path: str | None = typer.Option(None, help="Path to .productive-mcp.json"),
    filter: list[str] | None = typer.Option(None, "--filter", help="Repeat key=value filters"),
    filter_op: list[str] | None = typer.Option(
        None,
        "--filter-op",
        help="Repeat field:operator:value filters, ex: completed_at:not_exists:true",
    ),
    include: list[str] | None = typer.Option(None, "--include", help="Repeat include relationship names"),
    field: list[str] | None = typer.Option(None, "--field", help="Repeat resource:field1,field2"),
    sort: str | None = typer.Option(None, help="Sort expression"),
    page_number: int | None = typer.Option(None, help="Page number"),
    page_size: int | None = typer.Option(None, help="Page size"),
    raw: bool = typer.Option(False, "--raw", help="Print raw JSON"),
) -> None:
    async def _runner(client: ProductiveClient) -> dict[str, Any]:
        return await client.list_tasks(
            filters=_parse_filters(filter),
            filter_ops=_parse_filter_ops(filter_op),
            include=include,
            fields=_parse_fields(field),
            sort=sort,
            page_number=page_number,
            page_size=page_size,
        )

    try:
        payload = asyncio.run(_run_with_client(config_path, _runner))
        normalized = normalize_jsonapi_document(payload)
        if raw:
            _print_json(normalized)
            return
        _summarize_items(normalized)
    except Exception as exc:
        _handle_error(exc)


@app.command("find-tasks")
def find_tasks(
    config_path: str | None = typer.Option(None, help="Path to .productive-mcp.json"),
    status: str | None = typer.Option(None, "--status", help="Workflow status name, e.g. 'In Progress'"),
    cf: list[str] | None = typer.Option(None, "--cf", help="Custom field filter as Name=Value, repeatable"),
    page_number: int | None = typer.Option(None, help="Page number"),
    page_size: int | None = typer.Option(50, help="Page size"),
    include: list[str] | None = typer.Option(None, "--include", help="Repeat include relationship names"),
    field: list[str] | None = typer.Option(None, "--field", help="Repeat resource:field1,field2"),
    raw: bool = typer.Option(False, "--raw", help="Print raw JSON"),
) -> None:
    """Find tasks by workflow status and/or custom field values."""
    def _parse_cf(entries: list[str] | None) -> dict[str, str] | None:
        if not entries:
            return None
        parsed: dict[str, str] = {}
        for entry in entries:
            if "=" not in entry:
                raise typer.BadParameter(f"Invalid --cf value '{entry}'. Expected Name=Value.")
            key, value = entry.split("=", 1)
            parsed[key.strip()] = value.strip()
        return parsed or None

    cf_filters = _parse_cf(cf)

    async def _runner(client: ProductiveClient) -> dict[str, Any]:
        task_filters: dict[str, Any] = {}
        custom_field_params: dict[str, str] = {}

        if status:
            ws_payload = await client.list_workflow_statuses(page_size=200)
            ws_data = ws_payload.get("data") or []
            matched_ids: list[str] = []
            for ws in ws_data:
                if not isinstance(ws, dict):
                    continue
                attrs = ws.get("attributes") or {}
                name = attrs.get("name") or ""
                if name.lower() == status.lower():
                    matched_ids.append(ws["id"])
            if not matched_ids:
                raise ProductiveAPIError(f"No workflow status found matching '{status}'.", status_code=404)
            task_filters["workflow_status_id"] = ",".join(matched_ids)

        if cf_filters:
            cf_data = await client.list_all_custom_fields()
            cf_lookup: dict[str, tuple[str, int]] = {}
            for cf_item in cf_data:
                if not isinstance(cf_item, dict):
                    continue
                attrs = cf_item.get("attributes") or {}
                cf_name = attrs.get("name") or ""
                cf_lookup[cf_name.lower()] = (cf_item["id"], attrs.get("data_type_id", 0))

            for field_name, field_value in cf_filters.items():
                cf_entry = cf_lookup.get(field_name.lower())
                if not cf_entry:
                    raise ProductiveAPIError(f"No custom field found matching '{field_name}'.", status_code=404)
                cf_id, data_type = cf_entry
                resolved_value = field_value

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
                        raise ProductiveAPIError(
                            f"No option '{field_value}' found for custom field '{field_name}'.", status_code=404
                        )
                    resolved_value = option_id

                custom_field_params[f"filter[custom_fields][{cf_id}][eq]"] = resolved_value

        return await client.list_tasks(
            filters=task_filters or None,
            page_number=page_number,
            page_size=page_size,
            include=include,
            fields=_parse_fields(field),
            extra_params=custom_field_params or None,
        )

    try:
        payload = asyncio.run(_run_with_client(config_path, _runner))
        normalized = normalize_jsonapi_document(payload)
        if raw:
            _print_json(normalized)
            return
        _summarize_items(normalized)
    except Exception as exc:
        _handle_error(exc)


@app.command("get-task")
def get_task(
    task_reference: str = typer.Argument(..., help="Task number by default (or task ID with --by-id)"),
    config_path: str | None = typer.Option(None, help="Path to .productive-mcp.json"),
    include: list[str] | None = typer.Option(None, "--include", help="Repeat include relationship names"),
    field: list[str] | None = typer.Option(None, "--field", help="Repeat resource:field1,field2"),
    by_id: bool = typer.Option(False, "--by-id", help="Resolve the provided value as task ID"),
    include_comments: bool = typer.Option(False, help="Also fetch task comments"),
    comments_page_size: int = typer.Option(50, help="Comments page size when include-comments is enabled"),
    raw: bool = typer.Option(False, "--raw", help="Print raw JSON"),
) -> None:
    async def _runner(client: ProductiveClient) -> dict[str, Any]:
        task_payload = await client.get_task(
            task_reference,
            lookup_by="id" if by_id else "task_number",
            include=include,
            fields=_parse_fields(field),
        )
        result = normalize_jsonapi_document(task_payload)

        # Resolve custom field IDs → names and option IDs → option names
        item = result.get("item")
        cf_values = (item.get("attributes") or {}).get("custom_fields") if isinstance(item, dict) else None
        if cf_values and isinstance(cf_values, dict):
            cf_data = await client.list_all_custom_fields()
            cf_resolved: dict[str, Any] = {}
            for cf in cf_data:
                if not isinstance(cf, dict):
                    continue
                cf_id = cf.get("id")
                if cf_id not in cf_values:
                    continue
                cf_attrs = cf.get("attributes") or {}
                cf_name = cf_attrs.get("name") or cf_id
                data_type = cf_attrs.get("data_type_id", 0)
                raw_val = cf_values[cf_id]

                if data_type in (3, 5) and raw_val:
                    options = await client.list_all_custom_field_options(cf_id)
                    opt_lookup = {
                        opt["id"]: (opt.get("attributes") or {}).get("name", opt["id"])
                        for opt in options if isinstance(opt, dict)
                    }
                    if isinstance(raw_val, list):
                        cf_resolved[cf_name] = [opt_lookup.get(v, v) for v in raw_val]
                    else:
                        cf_resolved[cf_name] = opt_lookup.get(raw_val, raw_val)
                else:
                    cf_resolved[cf_name] = raw_val
            result["custom_fields_resolved"] = cf_resolved

        if include_comments:
            resolved_task_id = item.get("id") if isinstance(item, dict) else None
            if not resolved_task_id:
                raise ProductiveAPIError("Unable to resolve task id for comments lookup.")
            comments_payload = await client.list_task_comments(
                resolved_task_id,
                page_size=comments_page_size,
                include=["person"],
            )
            data = comments_payload.get("data")
            if isinstance(data, list):
                result["comments"] = [normalize_comment(item) for item in data if isinstance(item, dict)]
            elif isinstance(data, dict):
                result["comments"] = [normalize_comment(data)]
            else:
                result["comments"] = []
        return result

    try:
        payload = asyncio.run(_run_with_client(config_path, _runner))
        if raw:
            _print_json(payload)
            return
        item = payload.get("item")
        if isinstance(item, dict):
            attrs = item.get("attributes") or {}
            description = attrs.get("description")
            task_number = item.get("task_number")
            title = attrs.get("name") or attrs.get("title") or "<no-title>"
            tn_prefix = f"#{task_number} " if task_number else ""
            typer.echo(f"Task: {item.get('id')}  {tn_prefix}{title}")
            typer.echo(f"Type: {item.get('type')}")
            typer.echo("Description:\"\"\"")
            description = attrs.get("description")
            if isinstance(description, str) and description.strip():
                _render_html(description)
                typer.echo("\"\"\"")
            else:
                typer.echo("  <no-description>")

            # Print resolved included relationships
            included_list = payload.get("included") or []
            included_lookup: dict[tuple[str, str], dict[str, Any]] = {}
            for inc in included_list:
                if isinstance(inc, dict):
                    included_lookup[(inc.get("type", ""), inc.get("id", ""))] = inc
            relationships = item.get("relationships") or {}
            for rel_name, rel_data in relationships.items():
                if rel_data is None:
                    continue
                refs = rel_data if isinstance(rel_data, list) else [rel_data]
                for ref in refs:
                    if not isinstance(ref, dict):
                        continue
                    inc = included_lookup.get((ref.get("type", ""), ref.get("id", "")))
                    if not inc:
                        continue
                    inc_attrs = inc.get("attributes") or {}
                    label = inc_attrs.get("name") or inc_attrs.get("title") or inc_attrs.get("email") or ref.get("id")
                    typer.echo(f"    {rel_name}: {label}")

            # Print resolved custom fields
            cf_resolved = payload.get("custom_fields_resolved") or {}
            for cf_name, cf_val in cf_resolved.items():
                if cf_val is None:
                    continue
                if isinstance(cf_val, list):
                    typer.echo(f"    {cf_name}: {', '.join(str(v) for v in cf_val)}")
                else:
                    typer.echo(f"    {cf_name}: {cf_val}")

        if include_comments:
            comments = payload.get("comments") or []
            typer.echo(f"Comments: {len(comments)}")
            for comment in comments:
                if not isinstance(comment, dict):
                    continue
                raw_body = comment.get("body") or ""
                body = _html_to_plain(raw_body) if raw_body.strip() else ""
                snippet = body.replace("\n", " ")[:120] if body else "<empty-comment>"
                typer.echo(f"- comment:{comment.get('id')}  {snippet}")
    except Exception as exc:
        _handle_error(exc)


@app.command("list-task-comments")
def list_task_comments(
    task_id: str = typer.Argument(..., help="Task ID"),
    config_path: str | None = typer.Option(None, help="Path to .productive-mcp.json"),
    sort: str | None = typer.Option("created_at", help="Sort expression"),
    page_number: int | None = typer.Option(None, help="Page number"),
    page_size: int | None = typer.Option(None, help="Page size"),
    include: list[str] | None = typer.Option(["person"], "--include", help="Repeat include relationship names"),
    raw: bool = typer.Option(False, "--raw", help="Print raw JSON"),
) -> None:
    async def _runner(client: ProductiveClient) -> dict[str, Any]:
        return await client.list_task_comments(
            task_id=task_id,
            sort=sort,
            page_number=page_number,
            page_size=page_size,
            include=include,
        )

    try:
        payload = asyncio.run(_run_with_client(config_path, _runner))
        data = payload.get("data")
        if isinstance(data, list):
            normalized = [normalize_comment(item) for item in data if isinstance(item, dict)]
        elif isinstance(data, dict):
            normalized = [normalize_comment(data)]
        else:
            normalized = []

        result = {"items": normalized, "meta": payload.get("meta") or {}, "links": payload.get("links") or {}}
        if raw:
            _print_json(result)
            return
        typer.echo(f"Comments: {len(normalized)}")
        for item in normalized:
            raw_body = item.get("body") or ""
            body_text = _html_to_plain(raw_body) if raw_body.strip() else ""
            snippet = body_text.replace("\n", " ")[:120] if body_text else "<empty-comment>"
            typer.echo(f"- comment:{item.get('id')}  {snippet}")
    except Exception as exc:
        _handle_error(exc)


def _compact_lookup_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = normalize_jsonapi_document(payload)
    result: list[dict[str, Any]] = []
    for item in normalized.get("items") or []:
        if not isinstance(item, dict):
            continue
        attrs = item.get("attributes") or {}
        result.append(
            {
                "id": item.get("id"),
                "type": item.get("type"),
                "name": attrs.get("name"),
                "email": attrs.get("email"),
                "state": attrs.get("state"),
            }
        )
    return result


def _lookup_command(
    list_method: str,
    config_path: str | None,
    filter: list[str] | None,
    sort: str | None,
    page_number: int | None,
    page_size: int | None,
    raw: bool,
) -> None:
    async def _runner(client: ProductiveClient) -> list[dict[str, Any]]:
        method = getattr(client, list_method)
        payload = await method(
            filters=_parse_filters(filter),
            sort=sort,
            page_number=page_number,
            page_size=page_size,
        )
        return _compact_lookup_items(payload)

    try:
        items = asyncio.run(_run_with_client(config_path, _runner))
        if raw:
            _print_json({"items": items})
            return
        typer.echo(f"Items: {len(items)}")
        for item in items:
            label = item.get("name") or item.get("email") or "<no-label>"
            typer.echo(f"- {item.get('type')}:{item.get('id')}  {label}")
    except Exception as exc:
        _handle_error(exc)


@app.command("list-projects")
def list_projects(
    config_path: str | None = typer.Option(None, help="Path to .productive-mcp.json"),
    filter: list[str] | None = typer.Option(None, "--filter", help="Repeat key=value filters"),
    sort: str | None = typer.Option(None, help="Sort expression"),
    page_number: int | None = typer.Option(None, help="Page number"),
    page_size: int | None = typer.Option(50, help="Page size"),
    raw: bool = typer.Option(False, "--raw", help="Print raw JSON"),
) -> None:
    _lookup_command("list_projects", config_path, filter, sort, page_number, page_size, raw)


@app.command("list-task-lists")
def list_task_lists(
    config_path: str | None = typer.Option(None, help="Path to .productive-mcp.json"),
    filter: list[str] | None = typer.Option(None, "--filter", help="Repeat key=value filters"),
    sort: str | None = typer.Option(None, help="Sort expression"),
    page_number: int | None = typer.Option(None, help="Page number"),
    page_size: int | None = typer.Option(50, help="Page size"),
    raw: bool = typer.Option(False, "--raw", help="Print raw JSON"),
) -> None:
    _lookup_command("list_task_lists", config_path, filter, sort, page_number, page_size, raw)


@app.command("list-workflow-statuses")
def list_workflow_statuses(
    config_path: str | None = typer.Option(None, help="Path to .productive-mcp.json"),
    filter: list[str] | None = typer.Option(None, "--filter", help="Repeat key=value filters"),
    sort: str | None = typer.Option(None, help="Sort expression"),
    page_number: int | None = typer.Option(None, help="Page number"),
    page_size: int | None = typer.Option(50, help="Page size"),
    raw: bool = typer.Option(False, "--raw", help="Print raw JSON"),
) -> None:
    _lookup_command("list_workflow_statuses", config_path, filter, sort, page_number, page_size, raw)


@app.command("list-custom-fields")
def list_custom_fields(
    config_path: str | None = typer.Option(None, help="Path to .productive-mcp.json"),
    raw: bool = typer.Option(False, "--raw", help="Print raw JSON"),
) -> None:
    """List all task custom fields and their options for the configured project."""
    DATA_TYPES = {1: "text", 2: "number", 3: "select", 4: "date", 5: "multi-select", 6: "person", 7: "attachment"}

    async def _runner(client: ProductiveClient) -> list[dict[str, Any]]:
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
                "data_type": DATA_TYPES.get(data_type, "unknown"),
            }
            if data_type in (3, 5):
                options_data = await client.list_all_custom_field_options(cf["id"])
                field_info["options"] = [
                    {"id": opt.get("id"), "name": (opt.get("attributes") or {}).get("name")}
                    for opt in options_data
                    if isinstance(opt, dict)
                ]
            result.append(field_info)
        return result

    try:
        items = asyncio.run(_run_with_client(config_path, _runner))
        if raw:
            _print_json({"items": items})
            return
        typer.echo(f"Custom fields: {len(items)}")
        for item in items:
            typer.echo(f"- {item['name']} (id={item['id']}, type={item.get('data_type', '?')})")
            options = item.get("options")
            if options:
                for opt in options:
                    typer.echo(f"    {opt['name']} (id={opt['id']})")
    except Exception as exc:
        _handle_error(exc)


@app.command("list-people")
def list_people(
    config_path: str | None = typer.Option(None, help="Path to .productive-mcp.json"),
    filter: list[str] | None = typer.Option(None, "--filter", help="Repeat key=value filters"),
    sort: str | None = typer.Option(None, help="Sort expression"),
    page_number: int | None = typer.Option(None, help="Page number"),
    page_size: int | None = typer.Option(50, help="Page size"),
    raw: bool = typer.Option(False, "--raw", help="Print raw JSON"),
) -> None:
    _lookup_command("list_people", config_path, filter, sort, page_number, page_size, raw)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
