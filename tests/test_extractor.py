"""Tests for the extractor module."""

import os
import pytest
from namedviz.parser.extractor import extract_server_config, extract_all, resolve_relationships
from namedviz.parser.loader import load_and_parse
from namedviz.models import ServerConfig, Zone

CONFDATA = os.path.join(os.path.dirname(__file__), "confdata")


def test_extract_basic_config():
    results = load_and_parse(os.path.join(CONFDATA, "basic", "named.conf"))
    config = extract_server_config("test-server", results)

    assert config.name == "test-server"
    assert len(config.zones) == 3

    zone_names = {z.name for z in config.zones}
    assert "example.com" in zone_names
    assert "example.org" in zone_names
    assert "cdn.example.com" in zone_names


def test_extract_zone_types():
    results = load_and_parse(os.path.join(CONFDATA, "basic", "named.conf"))
    config = extract_server_config("test-server", results)

    by_name = {z.name: z for z in config.zones}
    assert by_name["example.com"].zone_type == "master"
    assert by_name["example.org"].zone_type == "slave"
    assert by_name["cdn.example.com"].zone_type == "forward"


def test_extract_masters_list():
    results = load_and_parse(os.path.join(CONFDATA, "basic", "named.conf"))
    config = extract_server_config("test-server", results)

    slave_zone = next(z for z in config.zones if z.name == "example.org")
    assert "10.0.0.5" in slave_zone.masters


def test_extract_also_notify():
    results = load_and_parse(os.path.join(CONFDATA, "basic", "named.conf"))
    config = extract_server_config("test-server", results)

    master_zone = next(z for z in config.zones if z.name == "example.com")
    assert "10.0.0.2" in master_zone.also_notify


def test_extract_allow_transfer():
    results = load_and_parse(os.path.join(CONFDATA, "basic", "named.conf"))
    config = extract_server_config("test-server", results)

    master_zone = next(z for z in config.zones if z.name == "example.com")
    assert "10.0.0.2" in master_zone.allow_transfer
    assert "10.0.0.3" in master_zone.allow_transfer


def test_extract_global_options():
    results = load_and_parse(os.path.join(CONFDATA, "basic", "named.conf"))
    config = extract_server_config("test-server", results)

    assert "8.8.8.8" in config.global_forwarders
    assert "10.0.0.2" in config.global_allow_transfer


def test_extract_views():
    results = load_and_parse(os.path.join(CONFDATA, "with_views", "named.conf"))
    config = extract_server_config("test-server", results)

    assert len(config.zones) == 2
    views = {z.view for z in config.zones}
    assert "internal" in views
    assert "external" in views


def test_extract_with_comments():
    results = load_and_parse(os.path.join(CONFDATA, "with_comments", "named.conf"))
    config = extract_server_config("test-server", results)

    assert len(config.zones) == 1
    assert config.zones[0].name == "example.com"


def test_extract_skips_logging():
    results = load_and_parse(os.path.join(CONFDATA, "with_logging", "named.conf"))
    config = extract_server_config("test-server", results)

    assert len(config.zones) == 1
    assert config.zones[0].name == "example.com"


def test_resolve_relationships_master_slave():
    server1 = ServerConfig(name="server1", zones=[
        Zone(name="example.com", zone_type="master", server_name="server1"),
    ])
    server2 = ServerConfig(name="server2", zones=[
        Zone(name="example.com", zone_type="slave", server_name="server2",
             masters=["10.0.0.1"]),
    ])

    rels = resolve_relationships([server1, server2])
    master_slave = [r for r in rels if r.rel_type == "master_slave"]
    assert len(master_slave) == 1
    assert master_slave[0].source == "server2"
    assert master_slave[0].target == "server1"  # resolved via zone name


def test_resolve_relationships_forward():
    server1 = ServerConfig(name="server1", zones=[
        Zone(name="cdn.example.com", zone_type="forward", server_name="server1",
             forwarders=["203.0.113.10"]),
    ])

    rels = resolve_relationships([server1])
    fwd = [r for r in rels if r.rel_type == "forward"]
    assert len(fwd) == 1
    assert fwd[0].target == "203.0.113.10"


def test_extract_all_sample_configs():
    sample_path = os.path.join(os.path.dirname(__file__), "..", "sample_configs")
    if not os.path.isdir(sample_path):
        pytest.skip("sample_configs not found")

    servers = extract_all(sample_path)
    assert len(servers) == 3
    names = {s.name for s in servers}
    assert names == {"server1", "server2", "server3"}
