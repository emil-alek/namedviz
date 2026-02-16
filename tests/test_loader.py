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
    results = load_and_parse(path)
    # Should have parsed zones
    zones = [r for r in results if hasattr(r, "getName") and r.getName() == "zone"]
    assert len(zones) == 3


def test_load_and_parse_with_include():
    path = os.path.join(CONFDATA, "with_include", "named.conf")
    results = load_and_parse(path)
    zones = [r for r in results if hasattr(r, "getName") and r.getName() == "zone"]
    # Should include zones from both files
    assert len(zones) == 2
    zone_names = {z["zone_name"] for z in zones}
    assert "example.com" in zone_names
    assert "example.org" in zone_names


def test_discover_sample_configs():
    sample_path = os.path.join(os.path.dirname(__file__), "..", "sample_configs")
    if not os.path.isdir(sample_path):
        pytest.skip("sample_configs not found")

    configs = discover_configs(sample_path)
    assert len(configs) == 3
    assert set(configs.keys()) == {"server1", "server2", "server3"}
