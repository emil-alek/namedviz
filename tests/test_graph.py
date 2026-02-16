"""Tests for the graph builder."""

import os
import pytest
from namedviz.models import ServerConfig, Zone
from namedviz.graph import build_graph


def test_build_graph_basic():
    server1 = ServerConfig(name="server1", zones=[
        Zone(name="example.com", zone_type="master", server_name="server1",
             also_notify=["10.0.0.2"], allow_transfer=["10.0.0.2"]),
    ])
    server2 = ServerConfig(name="server2", zones=[
        Zone(name="example.com", zone_type="slave", server_name="server2",
             masters=["10.0.0.1"]),
    ])

    graph = build_graph([server1, server2])

    assert len(graph.servers) == 2
    assert "server1" in graph.servers
    assert "server2" in graph.servers

    # Should have nodes for both servers
    node_ids = {n["id"] for n in graph.nodes}
    assert "server1" in node_ids
    assert "server2" in node_ids


def test_build_graph_links_aggregated():
    server1 = ServerConfig(name="server1", zones=[
        Zone(name="a.com", zone_type="master", server_name="server1",
             also_notify=["10.0.0.2"]),
        Zone(name="b.com", zone_type="master", server_name="server1",
             also_notify=["10.0.0.2"]),
    ])
    server2 = ServerConfig(name="server2", zones=[])

    graph = build_graph([server1, server2])

    # also_notify links to 10.0.0.2 should be aggregated into one link
    notify_links = [l for l in graph.links if l["rel_type"] == "also_notify"]
    assert len(notify_links) == 1
    assert notify_links[0]["count"] == 2
    assert len(notify_links[0]["zones"]) == 2


def test_build_graph_external_nodes():
    server1 = ServerConfig(name="server1", zones=[
        Zone(name="cdn.com", zone_type="forward", server_name="server1",
             forwarders=["203.0.113.10"]),
    ])

    graph = build_graph([server1])

    external = [n for n in graph.nodes if n["type"] == "external"]
    assert len(external) == 1
    assert external[0]["id"] == "203.0.113.10"


def test_build_graph_zone_summaries():
    server1 = ServerConfig(name="server1", zones=[
        Zone(name="example.com", zone_type="master", server_name="server1"),
        Zone(name="example.org", zone_type="slave", server_name="server1",
             masters=["10.0.0.5"]),
    ])

    graph = build_graph([server1])
    assert len(graph.zones) == 2
    zone_names = {z["name"] for z in graph.zones}
    assert "example.com" in zone_names
    assert "example.org" in zone_names


def test_build_graph_from_sample_configs():
    from namedviz.parser.extractor import extract_all

    sample_path = os.path.join(os.path.dirname(__file__), "..", "sample_configs")
    if not os.path.isdir(sample_path):
        pytest.skip("sample_configs not found")

    servers = extract_all(sample_path)
    graph = build_graph(servers)

    assert len(graph.servers) == 3
    assert len(graph.nodes) > 3  # servers + external IPs
    assert len(graph.links) > 0

    # Verify link types exist
    rel_types = {l["rel_type"] for l in graph.links}
    assert "master_slave" in rel_types
