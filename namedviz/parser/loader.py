"""File discovery and loading for named.conf files."""

from __future__ import annotations

import os
from pathlib import Path

from .grammar import parse_named_conf


def discover_configs(config_path: str) -> dict[str, str]:
    """Discover named.conf files and return {server_name: file_path}.

    Supports two modes:
    - Subdirectory mode: path/server1/named.conf -> server name = dir name
    - Flat file mode: path/server1.conf -> server name = filename stem
    """
    p = Path(config_path)
    if not p.exists():
        raise FileNotFoundError(f"Config path not found: {config_path}")

    configs: dict[str, str] = {}

    if p.is_file():
        # Single file
        configs[p.stem] = str(p)
        return configs

    # Check for subdirectory mode first
    for entry in sorted(p.iterdir()):
        if entry.is_dir():
            for conf_name in ("named.conf", "named.conf.local"):
                conf_file = entry / conf_name
                if conf_file.is_file():
                    configs[entry.name] = str(conf_file)
                    break

    # If no subdirs found, try flat file mode
    if not configs:
        for entry in sorted(p.iterdir()):
            if entry.is_file() and entry.suffix == ".conf":
                configs[entry.stem] = str(entry)

    return configs


def load_and_parse(file_path: str) -> tuple[dict, list[dict]]:
    """Load a named.conf, resolve includes, parse, and return (results, logs).

    Each log entry is a dict with 'level' ('info' or 'warn') and 'message'.
    """
    logs: list[dict] = []
    root_dir = os.path.dirname(os.path.realpath(file_path))
    text = _resolve_includes(file_path, root_dir=root_dir, logs=logs)
    results = parse_named_conf(text)
    return results, logs


def _resolve_includes(
    file_path: str,
    root_dir: str,
    seen: set[str] | None = None,
    logs: list[dict] | None = None,
) -> str:
    """Read a file and inline any include directives."""
    if seen is None:
        seen = set()
    if logs is None:
        logs = []

    real = os.path.realpath(file_path)
    if real in seen:
        logs.append({"level": "warn", "message": f"Circular include skipped: {file_path}"})
        return ""
    seen.add(real)

    base_dir = os.path.dirname(real)
    lines: list[str] = []

    with open(file_path, "r") as f:
        content = f.read()

    # Simple include resolution: find include "path"; directives
    # We do this at the text level before parsing so the parser
    # sees a single unified file.
    import re
    include_pattern = re.compile(
        r'include\s+["\']([^"\']+)["\']\s*;', re.IGNORECASE
    )

    pos = 0
    for match in include_pattern.finditer(content):
        lines.append(content[pos:match.start()])
        inc_path = match.group(1)
        original_inc_path = inc_path
        # Resolve relative to the including file's directory
        if not os.path.isabs(inc_path):
            inc_path = os.path.join(base_dir, inc_path)
        if not os.path.isfile(inc_path):
            # Absolute path from the original server — try basename in local dir
            inc_path = os.path.join(base_dir, os.path.basename(inc_path))
        if not os.path.isfile(inc_path):
            # Try matching path suffixes against the server root directory.
            # e.g. "/etc/bind/zones/named.conf.internal-zones" tries
            # "zones/named.conf.internal-zones" relative to root_dir.
            inc_path = _find_by_suffix(original_inc_path, root_dir)
        if not (inc_path and os.path.isfile(inc_path)):
            # Last resort: recursive basename search in root_dir
            inc_path = _find_recursive(original_inc_path, root_dir)
        if inc_path and os.path.isfile(inc_path):
            logs.append({"level": "info", "message": f"Resolved include: {original_inc_path}"})
            lines.append(_resolve_includes(inc_path, root_dir, seen, logs))
        else:
            logs.append({"level": "warn", "message": f"Include file not found: {original_inc_path}"})
        pos = match.end()

    lines.append(content[pos:])
    return "".join(lines)


def _find_recursive(inc_path: str, root_dir: str) -> str | None:
    """Search root_dir recursively for a file matching the basename."""
    target = os.path.basename(inc_path)
    for dirpath, _, filenames in os.walk(root_dir):
        if target in filenames:
            return os.path.join(dirpath, target)
    return None


def _find_by_suffix(inc_path: str, root_dir: str) -> str | None:
    """Try progressively longer path suffixes against root_dir.

    For "/etc/bind/zones/file.conf", tries:
      root_dir/file.conf
      root_dir/zones/file.conf
      root_dir/bind/zones/file.conf
      ...
    Returns the first match or None.
    """
    parts = Path(inc_path.replace("\\", "/")).parts
    # Skip any root component (e.g. "/" on Unix)
    parts = [p for p in parts if p != "/"]
    for i in range(len(parts) - 1, -1, -1):
        candidate = os.path.join(root_dir, *parts[i:])
        if os.path.isfile(candidate):
            return candidate
    return None
