"""API routes for namedviz."""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_from_directory

api_bp = Blueprint("api", __name__)


@api_bp.route("/")
def index():
    return send_from_directory(current_app.static_folder, "index.html")


@api_bp.route("/api/graph")
def get_graph():
    graph_data = current_app.config.get("GRAPH_DATA")
    if graph_data is None:
        return jsonify({"nodes": [], "links": [], "zones": [], "servers": []})
    return jsonify(asdict(graph_data))


@api_bp.route("/api/server/<name>")
def get_server(name):
    servers = current_app.config.get("SERVERS", [])
    for server in servers:
        if server.name == name:
            return jsonify({
                "name": server.name,
                "zone_count": len(server.zones),
                "zones": [
                    {
                        "name": z.name,
                        "type": z.zone_type,
                        "view": z.view,
                        "masters": z.masters,
                        "forwarders": z.forwarders,
                        "allow_transfer": z.allow_transfer,
                        "also_notify": z.also_notify,
                    }
                    for z in server.zones
                ],
                "acls": server.acls,
                "global_forwarders": server.global_forwarders,
                "global_also_notify": server.global_also_notify,
                "global_allow_transfer": server.global_allow_transfer,
            })
    return jsonify({"error": "Server not found"}), 404


@api_bp.route("/api/zones")
def get_zones():
    servers = current_app.config.get("SERVERS", [])
    zones = []
    for server in servers:
        for z in server.zones:
            zones.append({
                "name": z.name,
                "type": z.zone_type,
                "server": z.server_name,
                "view": z.view,
            })

    # Apply filters
    server_filter = request.args.get("server")
    type_filter = request.args.get("type")
    name_filter = request.args.get("name")

    if server_filter:
        zones = [z for z in zones if z["server"] == server_filter]
    if type_filter:
        zones = [z for z in zones if z["type"] == type_filter]
    if name_filter:
        zones = [z for z in zones if name_filter.lower() in z["name"].lower()]

    return jsonify(zones)


@api_bp.route("/api/parse", methods=["POST"])
def parse_configs():
    data = request.get_json(silent=True) or {}
    config_path = data.get("path", current_app.config.get("CONFIG_PATH"))
    if not config_path:
        return jsonify({"error": "No config path provided"}), 400

    try:
        from .app import _parse_configs
        current_app.config["CONFIG_PATH"] = config_path
        _parse_configs(current_app)
        graph_data = current_app.config.get("GRAPH_DATA")
        return jsonify({
            "status": "ok",
            "servers": graph_data.servers if graph_data else [],
            "node_count": len(graph_data.nodes) if graph_data else 0,
            "link_count": len(graph_data.links) if graph_data else 0,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/upload", methods=["POST"])
def upload_configs():
    """Accept uploaded named.conf files and parse them.

    Files are sent as multipart form data. Each file's form field name
    is used as the server name (e.g. "server1", "server2"). If the field
    name is generic ("file", "file0", etc.), the filename stem is used.
    """
    if not request.files:
        return jsonify({"error": "No files uploaded"}), 400

    # Create a temp directory with server subdirectories
    upload_dir = tempfile.mkdtemp(prefix="namedviz_")
    current_app.config["UPLOAD_DIR"] = upload_dir

    server_count = 0
    for field_name, file in request.files.items(multi=True):
        # Determine server name from the field name or filename
        server_name = field_name
        if server_name.startswith("file") or server_name == "configs":
            # Generic field name — derive from filename
            server_name = Path(file.filename).stem
            # If it's just "named" from named.conf, use parent-like naming
            if server_name in ("named", "named.conf"):
                server_name = f"server{server_count + 1}"

        server_dir = os.path.join(upload_dir, server_name)
        os.makedirs(server_dir, exist_ok=True)
        file.save(os.path.join(server_dir, "named.conf"))
        server_count += 1

    if server_count == 0:
        return jsonify({"error": "No valid config files found"}), 400

    try:
        from .app import _parse_configs
        current_app.config["CONFIG_PATH"] = upload_dir
        _parse_configs(current_app)
        graph_data = current_app.config.get("GRAPH_DATA")
        return jsonify({
            "status": "ok",
            "servers": graph_data.servers if graph_data else [],
            "node_count": len(graph_data.nodes) if graph_data else 0,
            "link_count": len(graph_data.links) if graph_data else 0,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
