"""Deployment configuration checks for ``Dockerfile`` and ``compose.yaml``.

Uses the Python standard library only (``PyYAML`` is not a project dependency).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "Dockerfile"
COMPOSE_FILE = ROOT / "compose.yaml"

BACKEND_PACKAGES = (
    "adapters",
    "api",
    "contracts",
    "decision",
    "economics",
    "engine",
    "kinds_of_year",
    "params",
)


def parse_dockerfile(text: str) -> list[tuple[str, str]]:
    """Return ``(INSTRUCTION, argument)`` pairs from a Dockerfile."""
    instructions: list[tuple[str, str]] = []
    buffer = ""
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not buffer and (not stripped or stripped.startswith("#")):
            continue
        if stripped.endswith("\\"):
            buffer = f"{buffer} {stripped[:-1].strip()}".strip()
            continue
        logical = f"{buffer} {stripped}".strip() if buffer else stripped
        buffer = ""
        if logical.startswith("#"):
            continue
        parts = logical.split(None, 1)
        instructions.append((parts[0].upper(), parts[1] if len(parts) > 1 else ""))
    if buffer:
        raise AssertionError(f"Dangling line continuation in Dockerfile: {buffer!r}")
    return instructions


def _strip_yaml_comment(line: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    for index, ch in enumerate(line):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_double:
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif (
            ch == "#"
            and not in_single
            and not in_double
            and (index == 0 or line[index - 1].isspace())
        ):
            return line[:index]
    return line


def _unquote_scalar(value: str) -> Any:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    return text


def _split_key_value(text: str) -> tuple[str, str | None] | None:
    match = re.match(r"^([^'\"]+):(?:\s+(.*))?$", text)
    if not match:
        return None
    key = match.group(1).strip()
    if not key:
        raise ValueError(f"Empty mapping key in {text!r}")
    rest = (match.group(2) or "").strip()
    return key, rest if rest else None


def _tokenize_yaml_lines(text: str) -> list[tuple[int, str]]:
    tokens: list[tuple[int, str]] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw[: len(raw) - len(raw.lstrip(" \t"))]:
            raise ValueError(f"Tab indentation on line {line_no} of compose.yaml")
        cleaned = _strip_yaml_comment(raw).rstrip()
        if not cleaned.strip():
            continue
        indent = len(cleaned) - len(cleaned.lstrip(" "))
        tokens.append((indent, cleaned.lstrip(" ")))
    return tokens


def parse_yaml_subset(text: str) -> Any:
    """Parse the block mappings and sequences used by ``compose.yaml``."""
    tokens = _tokenize_yaml_lines(text)

    def parse_block(index: int, expected_indent: int) -> tuple[Any, int]:
        if index >= len(tokens):
            return {}, index
        if tokens[index][1].startswith("- "):
            return parse_sequence(index, expected_indent)
        return parse_mapping(index, expected_indent)

    def parse_mapping(index: int, indent: int) -> tuple[dict[str, Any], int]:
        mapping: dict[str, Any] = {}
        while index < len(tokens):
            cur_indent, content = tokens[index]
            if cur_indent < indent or content.startswith("- "):
                break
            if cur_indent > indent:
                raise ValueError(f"Unexpected indentation at {content!r}")
            kv = _split_key_value(content)
            if kv is None:
                raise ValueError(
                    f"Expected 'key: value' mapping entry, got {content!r}"
                )
            key, value = kv
            if key in mapping:
                raise ValueError(f"Duplicate mapping key {key!r}")
            index += 1
            if value is not None:
                mapping[key] = _unquote_scalar(value)
            elif index < len(tokens) and tokens[index][0] > indent:
                nested, index = parse_block(index, tokens[index][0])
                mapping[key] = nested
            else:
                mapping[key] = None
        return mapping, index

    def parse_sequence(index: int, indent: int) -> tuple[list[Any], int]:
        items: list[Any] = []
        while index < len(tokens):
            cur_indent, content = tokens[index]
            if cur_indent < indent or not content.startswith("- "):
                break
            if cur_indent > indent:
                raise ValueError(f"Unexpected sequence indentation at {content!r}")
            after_dash = content[2:].strip()
            index += 1
            kv = _split_key_value(after_dash)
            if kv is not None:
                item_indent = cur_indent + 2
                first_key, first_val = kv
                item: dict[str, Any] = {}
                if first_val is not None:
                    item[first_key] = _unquote_scalar(first_val)
                elif index < len(tokens) and tokens[index][0] > item_indent:
                    nested, index = parse_block(index, tokens[index][0])
                    item[first_key] = nested
                else:
                    item[first_key] = None
                if index < len(tokens) and tokens[index][0] >= item_indent:
                    rest, index = parse_mapping(index, item_indent)
                    item.update(rest)
                items.append(item)
            else:
                items.append(_unquote_scalar(after_dash))
        return items, index

    if not tokens:
        return {}
    result, next_index = parse_block(0, tokens[0][0])
    assert next_index == len(tokens), f"Unparsed trailing YAML at token {next_index}"
    return result


def _instructions_by_name(instructions: list[tuple[str, str]], name: str) -> list[str]:
    return [arg for instr, arg in instructions if instr == name]


def test_dockerfile_runtime_and_port_fallback():
    instructions = parse_dockerfile(DOCKERFILE.read_text(encoding="utf-8"))

    assert _instructions_by_name(instructions, "FROM") == ["python:3.12-slim"]
    assert _instructions_by_name(instructions, "WORKDIR") == ["/app"]
    assert _instructions_by_name(instructions, "EXPOSE") == ["8000"]

    runs = _instructions_by_name(instructions, "RUN")
    assert "uv sync --frozen --no-dev --no-install-project" in runs

    cache_runs = [
        idx
        for idx, (instr, arg) in enumerate(instructions)
        if instr == "RUN"
        and "useradd" in arg
        and "app" in arg
        and "/data/climate-cache" in arg
        and re.search(r"chown\s+-R\s+app\b.*\s/data\b", arg)
    ]
    assert cache_runs, "Dockerfile must create user 'app' and own /data/climate-cache"

    user_indices = [
        idx
        for idx, (instr, arg) in enumerate(instructions)
        if instr == "USER" and arg == "app"
    ]
    assert user_indices, "Dockerfile must switch to non-root USER app"
    assert cache_runs[0] < user_indices[0]

    cmd_indices = [idx for idx, (instr, _) in enumerate(instructions) if instr == "CMD"]
    assert len(cmd_indices) == 1
    assert user_indices[0] < cmd_indices[0]

    cmd_args = json.loads(instructions[cmd_indices[0]][1])
    assert isinstance(cmd_args, list)
    assert cmd_args[:2] == ["sh", "-c"]
    shell_cmd = cmd_args[2]
    assert "exec uvicorn api.main:app" in shell_cmd
    assert "--host 0.0.0.0" in shell_cmd
    assert "--port ${PORT:-8000}" in shell_cmd


def test_compose_yaml_valid_and_watches_all_backend_packages():
    compose = parse_yaml_subset(COMPOSE_FILE.read_text(encoding="utf-8"))
    assert isinstance(compose, dict)

    services = compose["services"]
    api = services["api"]
    assert api["build"] == "."
    assert api["environment"]["CLIMATE_CACHE_DIR"] == "/data/climate-cache"

    assert "climate_cache:/data" in api["volumes"]
    assert "climate_cache" in compose["volumes"]

    watch_entries = api["develop"]["watch"]
    synced_by_target = {
        entry["target"]: entry
        for entry in watch_entries
        if isinstance(entry, dict) and entry.get("action") in ("sync", "sync+restart")
    }

    for package in BACKEND_PACKAGES:
        assert (ROOT / package / "__init__.py").is_file()
        target = f"/app/{package}"
        assert target in synced_by_target, f"Missing watch entry for {package}"
        assert synced_by_target[target]["path"] == f"./{package}"

    rebuild_paths = {
        entry["path"]
        for entry in watch_entries
        if isinstance(entry, dict) and entry.get("action") == "rebuild"
    }
    assert {"pyproject.toml", "uv.lock"} <= rebuild_paths
