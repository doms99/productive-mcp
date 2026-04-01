from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

from productive_mcp.models import ProductiveAPIError, ProductiveConfig, ProductiveConfigError, resolve_default_config_path
from productive_mcp.query import build_query_params


ERROR_HINTS = {
    401: "Unauthorized. Verify PRODUCTIVE_API_TOKEN.",
    403: "Forbidden. Verify organization access for PRODUCTIVE_ORGANIZATION_ID.",
    404: "Resource not found.",
    422: "Validation error. Verify request payload and supported fields.",
    429: "Rate limit exceeded. Retry later.",
}


def _resolve_setting(
    explicit_value: str | None,
    env_key: str,
    file_payload: dict[str, Any],
) -> str | None:
    if isinstance(explicit_value, str) and explicit_value.strip():
        return explicit_value.strip()

    env_value = os.getenv(env_key)
    if isinstance(env_value, str) and env_value.strip():
        return env_value.strip()

    file_value = file_payload.get(env_key)
    if isinstance(file_value, str) and file_value.strip():
        return file_value.strip()

    return None


def _resolve_explicit_or_env(explicit_value: str | None, env_key: str) -> str | None:
    if isinstance(explicit_value, str) and explicit_value.strip():
        return explicit_value.strip()

    env_value = os.getenv(env_key)
    if isinstance(env_value, str) and env_value.strip():
        return env_value.strip()

    return None


def load_config(
    config_path: str | None = None,
    *,
    api_token: str | None = None,
    organization_id: str | None = None,
    project_id: str | None = None,
    base_url: str | None = None,
) -> ProductiveConfig:
    path = Path(config_path) if config_path else resolve_default_config_path()
    payload: dict[str, Any] = {}
    path_exists = path.exists()
    try:
        if path_exists:
            payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProductiveConfigError(f"Invalid JSON in config file {path}: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise ProductiveConfigError(f"Config file {path} must contain a JSON object")

    resolved_api_token = _resolve_explicit_or_env(api_token, "PRODUCTIVE_API_TOKEN")
    if resolved_api_token is None:
        raise ProductiveConfigError(
            "Missing Productive API token. Pass --api-token or set PRODUCTIVE_API_TOKEN environment variable."
        )

    merged_payload: dict[str, Any] = {
        "PRODUCTIVE_API_TOKEN": resolved_api_token,
        "PRODUCTIVE_ORGANIZATION_ID": _resolve_setting(organization_id, "PRODUCTIVE_ORGANIZATION_ID", payload),
        "PRODUCTIVE_PROJECT_ID": _resolve_setting(project_id, "PRODUCTIVE_PROJECT_ID", payload),
        "PRODUCTIVE_BASE_URL": _resolve_setting(base_url, "PRODUCTIVE_BASE_URL", payload),
    }

    if not path_exists and (
        merged_payload["PRODUCTIVE_API_TOKEN"] is None or merged_payload["PRODUCTIVE_ORGANIZATION_ID"] is None
    ):
        raise ProductiveConfigError(
            (
                f"Config file not found: {path}. "
                "Pass credentials via server arguments, set PRODUCTIVE_API_TOKEN / PRODUCTIVE_ORGANIZATION_ID env vars, "
                "or create .productive-mcp.json."
            )
        )

    return ProductiveConfig.from_dict(merged_payload)


class ProductiveClient:
    def __init__(self, config: ProductiveConfig) -> None:
        self._config = config
        self._client = httpx.AsyncClient(
            base_url=self._config.base_url,
            timeout=httpx.Timeout(30.0),
            headers={
                "X-Auth-Token": self._config.api_token,
                "X-Organization-Id": self._config.organization_id,
                "Accept": "application/vnd.api+json",
                "Content-Type": "application/vnd.api+json",
            },
        )

    @classmethod
    def from_config_path(
        cls,
        config_path: str | None = None,
        *,
        api_token: str | None = None,
        organization_id: str | None = None,
        project_id: str | None = None,
        base_url: str | None = None,
    ) -> "ProductiveClient":
        return cls(
            load_config(
                config_path,
                api_token=api_token,
                organization_id=organization_id,
                project_id=project_id,
                base_url=base_url,
            )
        )

    async def __aenter__(self) -> "ProductiveClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._client.request(method, path, params=params, json=json_body)
        except httpx.HTTPError as exc:
            raise ProductiveAPIError(f"HTTP request failed: {exc}") from exc

        if response.is_error:
            raise self._to_api_error(response)

        if not response.content:
            return {}
        try:
            decoded = response.json()
        except ValueError as exc:
            raise ProductiveAPIError("Productive API response is not valid JSON", response.status_code) from exc

        if not isinstance(decoded, dict):
            raise ProductiveAPIError("Productive API response JSON is not an object", response.status_code, decoded)
        return decoded

    def _to_api_error(self, response: httpx.Response) -> ProductiveAPIError:
        status_code = response.status_code
        hint = ERROR_HINTS.get(status_code, "Request failed.")

        message = hint
        details: Any = None
        try:
            body = response.json()
            details = body
            if isinstance(body, dict):
                errors = body.get("errors")
                if isinstance(errors, list) and errors:
                    first = errors[0]
                    if isinstance(first, dict):
                        detail = first.get("detail") or first.get("title")
                        if detail:
                            message = f"{hint} {detail}"
        except ValueError:
            details = response.text

        return ProductiveAPIError(message, status_code=status_code, details=details)

    async def test_connection(self) -> dict[str, Any]:
        return await self._request("GET", "/api/v2/people", params={"page[size]": 1})

    async def list_tasks(
        self,
        *,
        filters: dict[str, Any] | None = None,
        filter_ops: dict[str, dict[str, Any]] | None = None,
        sort: str | None = None,
        page_number: int | None = None,
        page_size: int | None = None,
        include: list[str] | None = None,
        fields: dict[str, list[str] | str] | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        effective_filters: dict[str, Any] = {}
        if self._config.project_id:
            effective_filters["project_id"] = self._config.project_id
        if filters:
            effective_filters.update(filters)

        params = build_query_params(
            filters=effective_filters or None,
            filter_ops=filter_ops,
            sort=sort,
            page_number=page_number,
            page_size=page_size,
            include=include,
            fields=fields,
        )
        if extra_params:
            params.update(extra_params)
        return await self._request("GET", "/api/v2/tasks", params=params)

    async def get_task(
        self,
        task_reference: str,
        *,
        lookup_by: str = "task_number",
        include: list[str] | None = None,
        fields: dict[str, list[str] | str] | None = None,
    ) -> dict[str, Any]:
        params = build_query_params(include=include, fields=fields)
        if lookup_by == "id":
            return await self._request("GET", f"/api/v2/tasks/{task_reference}", params=params)

        if lookup_by != "task_number":
            raise ProductiveAPIError("lookup_by must be either 'task_number' or 'id'", status_code=422)

        list_payload = await self.list_tasks(
            filters={"task_number": task_reference},
            include=include,
            fields=fields,
            page_size=2,
        )
        data = list_payload.get("data")
        if not isinstance(data, list) or not data:
            raise ProductiveAPIError(
                f"Resource not found. Task with task_number '{task_reference}' was not found.",
                status_code=404,
                details=list_payload,
            )

        if len(data) > 1:
            raise ProductiveAPIError(
                (
                    f"Multiple tasks found for task_number '{task_reference}'. "
                    "Refine context (for example with PRODUCTIVE_PROJECT_ID) or fetch by id."
                ),
                status_code=422,
                details=list_payload,
            )

        return {
            "data": data[0],
            "included": list_payload.get("included") or [],
            "links": list_payload.get("links") or {},
            "meta": list_payload.get("meta") or {},
        }

    async def list_task_comments(
        self,
        task_id: str,
        *,
        sort: str | None = "created_at",
        page_number: int | None = None,
        page_size: int | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        params = build_query_params(
            filters={"task_id": task_id},
            sort=sort,
            page_number=page_number,
            page_size=page_size,
            include=include,
        )
        return await self._request("GET", "/api/v2/comments", params=params)


    async def list_projects(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str | None = None,
        page_number: int | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        params = build_query_params(filters=filters, sort=sort, page_number=page_number, page_size=page_size)
        return await self._request("GET", "/api/v2/projects", params=params)

    async def list_task_lists(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str | None = None,
        page_number: int | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        effective_filters: dict[str, Any] = {}
        if self._config.project_id:
            effective_filters["project_id"] = self._config.project_id
        if filters:
            effective_filters.update(filters)
        params = build_query_params(filters=effective_filters or None, sort=sort, page_number=page_number, page_size=page_size)
        return await self._request("GET", "/api/v2/task_lists", params=params)

    async def _resolve_project_workflow_id(self) -> str | None:
        if not self._config.project_id:
            return None
        payload = await self._request("GET", f"/api/v2/projects/{self._config.project_id}")
        data = payload.get("data") or {}
        workflow_rel = (data.get("relationships") or {}).get("workflow") or {}
        workflow_data = workflow_rel.get("data") or {}
        return workflow_data.get("id")

    async def list_workflow_statuses(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str | None = None,
        page_number: int | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        effective_filters: dict[str, Any] = {}
        workflow_id = await self._resolve_project_workflow_id()
        if workflow_id:
            effective_filters["workflow_id"] = workflow_id
        if filters:
            effective_filters.update(filters)
        params = build_query_params(filters=effective_filters or None, sort=sort, page_number=page_number, page_size=page_size)
        return await self._request("GET", "/api/v2/workflow_statuses", params=params)

    async def _paginate_all(self, path: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        all_data: list[dict[str, Any]] = []
        page = 1
        while True:
            params = build_query_params(filters=filters, page_number=page, page_size=200)
            payload = await self._request("GET", path, params=params)
            all_data.extend(payload.get("data") or [])
            total_pages = (payload.get("meta") or {}).get("total_pages", 1)
            if page >= total_pages:
                break
            page += 1
        return all_data

    async def list_all_custom_fields(self) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {"customizable_type": "tasks"}
        if self._config.project_id:
            filters["project_id"] = self._config.project_id
        return await self._paginate_all("/api/v2/custom_fields", filters)

    async def list_all_custom_field_options(self, custom_field_id: str) -> list[dict[str, Any]]:
        return await self._paginate_all(
            "/api/v2/custom_field_options",
            {"custom_field_id": custom_field_id},
        )

    async def list_people(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str | None = None,
        page_number: int | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        effective_filters: dict[str, Any] = {}
        if self._config.project_id:
            effective_filters["project_id"] = self._config.project_id
        if filters:
            effective_filters.update(filters)
        params = build_query_params(filters=effective_filters or None, sort=sort, page_number=page_number, page_size=page_size)
        return await self._request("GET", "/api/v2/people", params=params)
