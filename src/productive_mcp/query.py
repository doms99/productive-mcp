from __future__ import annotations

from typing import Any


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _to_csv(values: list[str] | tuple[str, ...] | set[str]) -> str:
    return ",".join(item for item in values if item)


def build_query_params(
    *,
    filters: dict[str, Any] | None = None,
    filter_ops: dict[str, dict[str, Any]] | None = None,
    sort: str | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    include: list[str] | None = None,
    fields: dict[str, list[str] | str] | None = None,
) -> dict[str, str]:
    params: dict[str, str] = {}

    if filters:
        for key, value in filters.items():
            if value is None:
                continue
            params[f"filter[{key}]"] = _stringify(value)

    if filter_ops:
        for key, operators in filter_ops.items():
            if not isinstance(operators, dict):
                continue
            for operator, value in operators.items():
                if value is None:
                    continue
                params[f"filter[{key}][{operator}]"] = _stringify(value)

    if sort:
        params["sort"] = sort
    if page_number is not None:
        params["page[number]"] = str(page_number)
    if page_size is not None:
        params["page[size]"] = str(page_size)
    if include:
        params["include"] = _to_csv(include)
    if fields:
        for resource_type, selected in fields.items():
            if isinstance(selected, str):
                params[f"fields[{resource_type}]"] = selected
            else:
                params[f"fields[{resource_type}]"] = _to_csv(list(selected))

    return params
