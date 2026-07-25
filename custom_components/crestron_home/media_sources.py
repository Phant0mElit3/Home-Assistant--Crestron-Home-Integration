"""Media room source helpers for Crestron Home."""

from __future__ import annotations

from typing import Any

SOURCE_LIST_KEYS = (
    "availableProviders",
    "availableSources",
    "sources",
    "inputs",
    "sourceList",
    "inputSources",
)
CURRENT_SOURCE_ID_KEYS = (
    "currentProviderId",
    "currentSourceId",
    "providerId",
    "sourceId",
)
SOURCE_ID_KEYS = (
    "id",
    "providerId",
    "sourceId",
)
SOURCE_NAME_KEYS = (
    "name",
    "sourceName",
    "providerName",
    "displayName",
    "label",
)
FALLBACK_SOURCE_COUNT = 12


def source_id(item: dict[str, Any]) -> Any:
    """Return the selected source id from a media room payload."""
    for key in CURRENT_SOURCE_ID_KEYS:
        if item.get(key) is not None:
            return item[key]
    return None


def source_options(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Return source ids and names from a media room payload."""
    source_values = _source_values(item)
    result: list[dict[str, Any]] = []
    for index, source in enumerate(source_values, start=1):
        if isinstance(source, dict):
            name = source_name(source)
            item_id = _first_value(source, SOURCE_ID_KEYS, index)
        else:
            name = str(source)
            item_id = index
        if name:
            result.append({"id": item_id, "name": name})
    if result:
        return result
    return _fallback_source_options(item)


def source_name(source: Any) -> str | None:
    """Return a display name for a media source payload."""
    if isinstance(source, dict):
        value = _first_value(source, SOURCE_NAME_KEYS)
        return str(value) if value is not None else None
    return str(source) if source is not None else None


def source_map(item: dict[str, Any]) -> dict[str, Any]:
    """Return a source name-to-id map for diagnostics."""
    return {source["name"]: source["id"] for source in source_options(item)}


def raw_source_keys(item: dict[str, Any]) -> dict[str, Any]:
    """Return the source-related keys Crestron provided."""
    keys = set(SOURCE_LIST_KEYS + CURRENT_SOURCE_ID_KEYS)
    keys.update(("currentProvider", "currentSource", "source"))
    return {key: item.get(key) for key in sorted(keys) if key in item}


def payload_keys(item: dict[str, Any]) -> list[str]:
    """Return top-level media room payload keys for diagnostics."""
    return sorted(str(key) for key in item)


def _source_values(item: dict[str, Any]) -> list[Any]:
    """Return the raw source list from known Crestron payload keys."""
    for key in SOURCE_LIST_KEYS:
        value = item.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for nested_key in ("items", "providers", "sources", "inputs"):
                nested_value = value.get(nested_key)
                if isinstance(nested_value, list):
                    return nested_value
    return []


def _first_value(item: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    """Return the first non-empty value from a dict."""
    for key in keys:
        value = item.get(key)
        if value is not None and value != "":
            return value
    return default


def _fallback_source_options(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Return manual provider-id options when Crestron withholds source names."""
    return [
        {"id": source_index, "name": f"Source {source_index}"}
        for source_index in range(0, FALLBACK_SOURCE_COUNT + 1)
    ]
