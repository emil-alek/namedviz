"""Tests for the loader module."""

import os
import pytest
from namedviz.parser.loader import discover_configs, load_and_parse

CONFDATA = os.path.join(os.path.dirname(__file__), "confdata")


def test_discover_subdirectory_mode():
    configs = discover_configs(CONFDATA)
    assert len(configs) >= 1
    # All confdata dirs should be found
    assert "basic" in configs
    assert "with_views" in configs


def test_discover_single_file():
    path = os.path.join(CONFDATA, "basic", "named.conf")
    configs = discover_configs(path)
    assert "named" in configs  # stem of named.conf


def test_discover_nonexistent_path():
    with pytest.raises(FileNotFoundError):
        discover_configs("/nonexistent/path")


def test_load_and_parse_basic():
    path = os.path.join(CONFDATA, "basic", "named.conf")
    results, warnings = load_and_parse(path)
    # Should have parsed zones
    zones = [r for r in results if hasattr(r, "getName") and r.getName() == "zone"]
    assert len(zones) == 3


def test_load_and_parse_with_include():
    path = os.path.join(CONFDATA, "with_include", "named.conf")
    results, warnings = load_and_parse(path)
    zones = [r for r in results if hasattr(r, "getName") and r.getName() == "zone"]
    # Should include zones from both files
    assert len(zones) == 2
    zone_names = {z["zone_name"] for z in zones}
    assert "example.com" in zone_names
    assert "example.org" in zone_names


def test_load_and_parse_views_with_includes():
    path = os.path.join(CONFDATA, "views_with_includes", "named.conf")
    results, warnings = load_and_parse(path)

    # Should find zones from included files inside views
    zones = [r for r in results if hasattr(r, "getName") and r.getName() == "zone"]
    # Top-level zone count is 0 — zones are inside views
    # Instead check views contain zones
    views = [r for r in results if hasattr(r, "getName") and r.getName() == "view"]
    assert len(views) == 2

    # Collect all zones from views
    all_zones = []
    for view in views:
        for item in view:
            if hasattr(item, "getName") and item.getName() == "zone":
                all_zones.append(item)
    assert len(all_zones) == 3

    zone_names = {z["zone_name"] for z in all_zones}
    assert "example.com" in zone_names
    assert "internal.example.com" in zone_names


def test_load_and_parse_with_absolute_include():
    path = os.path.join(CONFDATA, "with_abs_include", "named.conf")
    results, warnings = load_and_parse(path)
    zones = [r for r in results if hasattr(r, "getName") and r.getName() == "zone"]
    assert len(zones) == 1
    zone_names = {z["zone_name"] for z in zones}
    assert "absolute.example.com" in zone_names


def test_load_and_parse_with_missing_include():
    path = os.path.join(CONFDATA, "with_missing_include", "named.conf")
    results, warnings = load_and_parse(path)
    # Should still parse the zone that's in the main file
    zones = [r for r in results if hasattr(r, "getName") and r.getName() == "zone"]
    assert len(zones) == 1
    assert zones[0]["zone_name"] == "example.com"
    # Should have a warning about the missing include
    warn_logs = [w for w in warnings if w["level"] == "warn"]
    include_warns = [w for w in warn_logs if "Include file not found" in w["message"]]
    assert len(include_warns) == 1
    assert "missing-zones.conf" in include_warns[0]["message"]


def test_discover_sample_configs():
    sample_path = os.path.join(os.path.dirname(__file__), "..", "sample_configs")
    if not os.path.isdir(sample_path):
        pytest.skip("sample_configs not found")

    configs = discover_configs(sample_path)
    assert len(configs) == 4
    assert set(configs.keys()) == {"server1", "server2", "server3", "server4"}
