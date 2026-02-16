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


def load_and_parse(file_path: str) -> dict:
    """Load a named.conf, resolve includes, parse, and return results as dict."""
    text = _resolve_includes(file_path)
    results = parse_named_conf(text)
    return results


def _resolve_includes(file_path: str, seen: set[str] | None = None) -> str:
    """Read a file and inline any include directives."""
    if seen is None:
        seen = set()

    real = os.path.realpath(file_path)
    if real in seen:
        return ""  # avoid circular includes
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
        # Resolve relative to the including file's directory
        if not os.path.isabs(inc_path):
            inc_path = os.path.join(base_dir, inc_path)
        if os.path.isfile(inc_path):
            lines.append(_resolve_includes(inc_path, seen))
        pos = match.end()

    lines.append(content[pos:])
    return "".join(lines)
