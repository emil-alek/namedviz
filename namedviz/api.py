"""API routes for namedviz."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import traceback
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_from_directory

log = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)


def _save_logs(logs):
    """Write log entries to a timestamped file in the logs/ directory."""
    if not logs:
        return
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_file = log_dir / f"{timestamp}.log"
    lines = []
    for entry in logs:
        level = entry.get("level", "info").upper()
        message = entry.get("message", str(entry))
        lines.append(f"[{level}] {message}")
    log_file.write_text("\n".join(lines), encoding="utf-8")


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
                "listen_on": server.listen_on,
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
        warnings = _parse_configs(current_app)
        _save_logs(warnings)
        graph_data = current_app.config.get("GRAPH_DATA")
        return jsonify({
            "status": "ok",
            "servers": graph_data.servers if graph_data else [],
            "node_count": len(graph_data.nodes) if graph_data else 0,
            "link_count": len(graph_data.links) if graph_data else 0,
            "logs": warnings,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/reset", methods=["POST"])
def reset():
    """Clear all parsed data and clean up temp upload directory."""
    upload_dir = current_app.config.get("UPLOAD_DIR")
    if upload_dir and os.path.isdir(upload_dir):
        shutil.rmtree(upload_dir, ignore_errors=True)

    current_app.config.pop("CONFIG_PATH", None)
    current_app.config.pop("UPLOAD_DIR", None)
    current_app.config.pop("SERVERS", None)
    current_app.config.pop("GRAPH_DATA", None)

    return jsonify({"status": "ok"})


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

    # Group files by server name
    server_files: dict[str, list] = {}
    auto_count = 0
    for field_name, file in request.files.items(multi=True):
        server_name = field_name
        if server_name.startswith("file") or server_name == "configs":
            # Generic field name — derive from filename path
            # e.g. "server1/named.conf" -> "server1"
            parts = Path(file.filename).parts
            if len(parts) >= 2:
                server_name = parts[-2]
            else:
                server_name = Path(file.filename).stem
                if server_name in ("named", "named.conf"):
                    auto_count += 1
                    server_name = f"server{auto_count}"

        server_files.setdefault(server_name, []).append(file)

    if not server_files:
        return jsonify({"error": "No valid config files found"}), 400

    try:
        for server_name, files in server_files.items():
            server_dir = os.path.join(upload_dir, server_name)
            os.makedirs(server_dir, exist_ok=True)
            log.info("Saving %d file(s) for server %r -> %s", len(files), server_name, server_dir)
            for file in files:
                # Preserve subdirectory structure (e.g. "zones/example.com.zone")
                # so that include directives resolve correctly
                raw_name = (file.filename or "").replace("\\", "/")
                parts = [p for p in raw_name.split("/") if p and p != ".."]
                log.info("  field=%r  filename=%r  parts=%r", file.name if hasattr(file, 'name') else '?', file.filename, parts)
                if not parts:
                    log.warning("  Skipping file with empty path (field=%r)", file.filename)
                    continue
                rel_path = os.path.join(*parts)
                file_path = os.path.join(server_dir, rel_path)
                log.info("  -> saving to: %s", file_path)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                file.save(file_path)
                log.info("  saved OK")

        log.info("All files saved. Running _parse_configs on %s", upload_dir)
        from .app import _parse_configs
        current_app.config["CONFIG_PATH"] = upload_dir
        warnings = _parse_configs(current_app)
        _save_logs(warnings)
        graph_data = current_app.config.get("GRAPH_DATA")
        return jsonify({
            "status": "ok",
            "servers": graph_data.servers if graph_data else [],
            "node_count": len(graph_data.nodes) if graph_data else 0,
            "link_count": len(graph_data.links) if graph_data else 0,
            "logs": warnings,
        })
    except Exception as e:
        tb = traceback.format_exc()
        log.exception("Upload failed")
        return jsonify({"error": str(e), "traceback": tb}), 500
