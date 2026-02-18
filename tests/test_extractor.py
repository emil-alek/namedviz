"""Tests for the extractor module."""

import os
import pytest
from namedviz.parser.extractor import extract_server_config, extract_all, resolve_relationships
from namedviz.parser.loader import load_and_parse
from namedviz.models import ServerConfig, Zone

CONFDATA = os.path.join(os.path.dirname(__file__), "confdata")


def test_extract_basic_config():
    results, _ = load_and_parse(os.path.join(CONFDATA, "basic", "named.conf"))
    config = extract_server_config("test-server", results)

    assert config.name == "test-server"
    assert len(config.zones) == 3

    zone_names = {z.name for z in config.zones}
    assert "example.com" in zone_names
    assert "example.org" in zone_names
    assert "cdn.example.com" in zone_names


def test_extract_zone_types():
    results, _ = load_and_parse(os.path.join(CONFDATA, "basic", "named.conf"))
    config = extract_server_config("test-server", results)

    by_name = {z.name: z for z in config.zones}
    assert by_name["example.com"].zone_type == "master"
    assert by_name["example.org"].zone_type == "slave"
    assert by_name["cdn.example.com"].zone_type == "forward"


def test_extract_masters_list():
    results, _ = load_and_parse(os.path.join(CONFDATA, "basic", "named.conf"))
    config = extract_server_config("test-server", results)

    slave_zone = next(z for z in config.zones if z.name == "example.org")
    assert "10.0.0.5" in slave_zone.masters


def test_extract_also_notify():
    results, _ = load_and_parse(os.path.join(CONFDATA, "basic", "named.conf"))
    config = extract_server_config("test-server", results)

    master_zone = next(z for z in config.zones if z.name == "example.com")
    assert "10.0.0.2" in master_zone.also_notify


def test_extract_allow_transfer():
    results, _ = load_and_parse(os.path.join(CONFDATA, "basic", "named.conf"))
    config = extract_server_config("test-server", results)

    master_zone = next(z for z in config.zones if z.name == "example.com")
    assert "10.0.0.2" in master_zone.allow_transfer
    assert "10.0.0.3" in master_zone.allow_transfer


def test_extract_global_options():
    results, _ = load_and_parse(os.path.join(CONFDATA, "basic", "named.conf"))
    config = extract_server_config("test-server", results)

    assert "8.8.8.8" in config.global_forwarders
    assert "10.0.0.2" in config.global_allow_transfer


def test_extract_views():
    results, _ = load_and_parse(os.path.join(CONFDATA, "with_views", "named.conf"))
    config = extract_server_config("test-server", results)

    assert len(config.zones) == 2
    views = {z.view for z in config.zones}
    assert "internal" in views
    assert "external" in views


def test_extract_with_comments():
    results, _ = load_and_parse(os.path.join(CONFDATA, "with_comments", "named.conf"))
    config = extract_server_config("test-server", results)

    assert len(config.zones) == 1
    assert config.zones[0].name == "example.com"


def test_extract_skips_logging():
    results, _ = load_and_parse(os.path.join(CONFDATA, "with_logging", "named.conf"))
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
    assert master_slave[0].source == "server1"  # master (direction of authority)
    assert master_slave[0].target == "server2"  # slave


def test_resolve_relationships_forward():
    server1 = ServerConfig(name="server1", zones=[
        Zone(name="cdn.example.com", zone_type="forward", server_name="server1",
             forwarders=["203.0.113.10"]),
    ])

    rels = resolve_relationships([server1])
    fwd = [r for r in rels if r.rel_type == "forward"]
    assert len(fwd) == 1
    assert fwd[0].target == "203.0.113.10"


def test_extract_listen_on():
    results, _ = load_and_parse(os.path.join(CONFDATA, "views_with_includes", "named.conf"))
    config = extract_server_config("test-server", results)

    assert "10.0.0.1" in config.listen_on


def test_extract_listen_on_filters_special():
    """listen-on with 'any' should not include 'any' in listen_on list."""
    from namedviz.parser.grammar import parse_named_conf

    text = '''
    options {
        listen-on { any; };
    };
    '''
    results = parse_named_conf(text)
    config = extract_server_config("test-server", results)
    assert "any" not in config.listen_on


def test_extract_views_with_includes():
    results, _ = load_and_parse(os.path.join(CONFDATA, "views_with_includes", "named.conf"))
    config = extract_server_config("test-server", results)

    assert len(config.zones) == 3
    views = {z.view for z in config.zones}
    assert "internal" in views
    assert "external" in views

    # Internal view should have 2 zones
    internal_zones = [z for z in config.zones if z.view == "internal"]
    assert len(internal_zones) == 2

    # External view should have 1 zone
    external_zones = [z for z in config.zones if z.view == "external"]
    assert len(external_zones) == 1


def test_resolve_relationships_with_listen_on():
    """IPs in listen-on should resolve to the owning server."""
    server1 = ServerConfig(
        name="server1",
        listen_on=["10.0.0.1"],
        zones=[
            Zone(name="example.com", zone_type="master", server_name="server1",
                 also_notify=["10.0.0.2"], allow_transfer=["10.0.0.2"]),
        ],
    )
    server2 = ServerConfig(
        name="server2",
        listen_on=["10.0.0.2"],
        zones=[
            Zone(name="example.com", zone_type="slave", server_name="server2",
                 masters=["10.0.0.1"]),
        ],
    )

    rels = resolve_relationships([server1, server2])

    # All endpoints should be server names, not raw IPs
    endpoints = {r.source for r in rels} | {r.target for r in rels}
    assert "10.0.0.1" not in endpoints
    assert "10.0.0.2" not in endpoints
    assert "server1" in endpoints
    assert "server2" in endpoints


def test_extract_view_level_also_notify():
    """View-level also-notify should apply as fallback to zones in that view."""
    results, _ = load_and_parse(os.path.join(CONFDATA, "view_with_options", "named.conf"))
    config = extract_server_config("test-server", results)

    by_name_view = {(z.name, z.view): z for z in config.zones}

    # Zone without its own also-notify inherits from view
    zone1 = by_name_view[("example.com", "internal")]
    assert "10.0.0.5" in zone1.also_notify
    assert "10.0.0.6" in zone1.allow_transfer

    # Zone with its own also-notify keeps its own, not the view's
    zone2 = by_name_view[("example.org", "internal")]
    assert zone2.also_notify == ["10.0.0.7"]
    assert "10.0.0.5" not in zone2.also_notify

    # Zone in external view (no view-level options) has empty lists
    zone3 = by_name_view[("example.com", "external")]
    assert zone3.also_notify == []
    assert zone3.allow_transfer == []


def test_unknown_stmt_warnings():
    """Unknown statements should produce warning log entries."""
    results, logs = load_and_parse(os.path.join(CONFDATA, "view_with_options", "named.conf"))

    warn_msgs = [l["message"] for l in logs if l["level"] == "warn"]
    # match-clients and recursion are unknown statements inside views
    unknown_keywords = [m for m in warn_msgs if "Irrelevant statement skipped:" in m]
    assert len(unknown_keywords) > 0
    # match-clients should be among them
    assert any("match-clients" in m for m in unknown_keywords)
    assert any("recursion" in m for m in unknown_keywords)


def test_extract_view_server_ips():
    """View-level server statements should be captured in view_server_ips."""
    from namedviz.parser.grammar import parse_named_conf

    text = '''
    view "internal" {
        server 13.13.13.13;
        server 14.14.14.14;

        zone "example.com" {
            type master;
            file "db.example.com";
        };
    };
    '''
    results = parse_named_conf(text)
    config = extract_server_config("master-server", results)

    assert "internal" in config.view_server_ips
    assert config.view_server_ips["internal"] == ["13.13.13.13", "14.14.14.14"]


def test_resolve_relationships_view_servers():
    """View-level server IPs should generate peer relationships (one per IP)."""
    master = ServerConfig(
        name="master-server",
        listen_on=["10.0.0.1"],
        zones=[
            Zone(name="example.com", zone_type="master", server_name="master-server",
                 view="internal"),
            Zone(name="example.org", zone_type="master", server_name="master-server",
                 view="internal"),
        ],
        view_server_ips={"internal": ["10.0.0.2", "10.0.0.3"]},
    )
    slave1 = ServerConfig(name="slave1", listen_on=["10.0.0.2"])
    slave2 = ServerConfig(name="slave2", listen_on=["10.0.0.3"])

    rels = resolve_relationships([master, slave1, slave2])
    peer_rels = [r for r in rels if r.rel_type == "peer"]

    # 2 server IPs = 2 peer relationships (not multiplied by zones)
    assert len(peer_rels) == 2
    assert all(r.source == "master-server" for r in peer_rels)
    # Targets should be resolved to server names
    targets = {r.target for r in peer_rels}
    assert targets == {"slave1", "slave2"}
    # Peer relationships are not zone-specific
    assert all(r.zone_name == "" for r in peer_rels)


def test_extract_all_sample_configs():
    sample_path = os.path.join(os.path.dirname(__file__), "..", "sample_configs")
    if not os.path.isdir(sample_path):
        pytest.skip("sample_configs not found")

    servers, warnings = extract_all(sample_path)
    assert len(servers) == 4
    names = {s.name for s in servers}
    assert names == {"server1", "server2", "server3", "server4"}

    # server4 has missing includes — should produce warnings
    server4_warnings = [w for w in warnings
                        if w["level"] == "warn" and w["message"].startswith("[server4]")]
    assert len(server4_warnings) > 0
