"""Tests for the Flask API."""

import io
import os
import json
import pytest
from namedviz.app import create_app

SAMPLE_CONFIGS = os.path.join(os.path.dirname(__file__), "..", "sample_configs")
CONFDATA = os.path.join(os.path.dirname(__file__), "confdata")


@pytest.fixture
def client():
    app = create_app(SAMPLE_CONFIGS)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_index(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"namedviz" in resp.data


def test_get_graph(client):
    resp = client.get("/api/graph")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "nodes" in data
    assert "links" in data
    assert "servers" in data
    assert "zones" in data
    assert len(data["servers"]) == 4


def test_get_graph_has_links(client):
    resp = client.get("/api/graph")
    data = json.loads(resp.data)
    assert len(data["links"]) > 0
    # Each link should have required fields
    for link in data["links"]:
        assert "source" in link
        assert "target" in link
        assert "rel_type" in link
        assert "zones" in link
        assert "count" in link


def test_get_server_detail(client):
    resp = client.get("/api/server/server1")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["name"] == "server1"
    assert "zones" in data
    assert data["zone_count"] > 0


def test_get_server_detail_has_listen_on(client):
    resp = client.get("/api/server/server1")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "listen_on" in data
    assert "10.0.0.1" in data["listen_on"]


def test_get_server_not_found(client):
    resp = client.get("/api/server/nonexistent")
    assert resp.status_code == 404


def test_get_zones(client):
    resp = client.get("/api/zones")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert len(data) > 0
    for zone in data:
        assert "name" in zone
        assert "type" in zone
        assert "server" in zone


def test_get_zones_filter_by_server(client):
    resp = client.get("/api/zones?server=server1")
    data = json.loads(resp.data)
    assert all(z["server"] == "server1" for z in data)


def test_get_zones_filter_by_type(client):
    resp = client.get("/api/zones?type=master")
    data = json.loads(resp.data)
    assert all(z["type"] == "master" for z in data)


def test_get_zones_filter_by_name(client):
    resp = client.get("/api/zones?name=example")
    data = json.loads(resp.data)
    assert all("example" in z["name"].lower() for z in data)


def test_reparse(client):
    resp = client.post("/api/parse",
                       data=json.dumps({"path": SAMPLE_CONFIGS}),
                       content_type="application/json")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["status"] == "ok"
    assert len(data["servers"]) == 4


def test_reset(client):
    # Verify data exists before reset
    resp = client.get("/api/graph")
    data = json.loads(resp.data)
    assert len(data["servers"]) > 0

    # Reset
    resp = client.post("/api/reset")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["status"] == "ok"

    # Verify graph is now empty
    resp = client.get("/api/graph")
    data = json.loads(resp.data)
    assert data["servers"] == []
    assert data["nodes"] == []
    assert data["links"] == []


def test_upload_configs(client):
    # Reset first to start clean
    client.post("/api/reset")

    # Read a fixture config file
    conf_path = os.path.join(CONFDATA, "basic", "named.conf")
    with open(conf_path, "rb") as f:
        conf_content = f.read()

    # Upload as multipart form data with server name as field name
    data = {
        "testserver": (io.BytesIO(conf_content), "named.conf"),
    }
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    result = json.loads(resp.data)
    assert result["status"] == "ok"
    assert "testserver" in result["servers"]
    assert result["node_count"] > 0
    assert "logs" in result


def test_upload_multi_file_server(client):
    """Upload multiple config files for a single server (multi-file include)."""
    client.post("/api/reset")

    # Read the views_with_includes fixture (main conf + include files)
    fixture_dir = os.path.join(CONFDATA, "views_with_includes")
    files = {}
    for fname in ("named.conf", "internal-zones.conf", "external-zones.conf"):
        with open(os.path.join(fixture_dir, fname), "rb") as f:
            files[fname] = f.read()

    # Upload all files under the same server name
    data = {}
    for i, (fname, content) in enumerate(files.items()):
        data[f"myserver"] = (io.BytesIO(content), f"myserver/{fname}")

    # Use the werkzeug MultiDict approach for multiple files with same field name
    from werkzeug.datastructures import FileStorage, MultiDict
    items = []
    for fname, content in files.items():
        items.append(("myserver", (io.BytesIO(content), f"myserver/{fname}")))

    resp = client.post("/api/upload", data=MultiDict(items),
                       content_type="multipart/form-data")
    assert resp.status_code == 200
    result = json.loads(resp.data)
    assert result["status"] == "ok"
    assert "myserver" in result["servers"]


def test_upload_returns_logs(client):
    """Upload with a missing include should return warnings in logs."""
    client.post("/api/reset")

    conf_path = os.path.join(CONFDATA, "with_missing_include", "named.conf")
    with open(conf_path, "rb") as f:
        conf_content = f.read()

    data = {"testserver": (io.BytesIO(conf_content), "named.conf")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    result = json.loads(resp.data)
    assert result["status"] == "ok"
    assert len(result["logs"]) > 0
    assert any("missing-zones.conf" in log["message"]
               for log in result["logs"] if log["level"] == "warn")
