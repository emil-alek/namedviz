"""API routes for namedviz."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
import traceback
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_from_directory

from .models import SessionData

log = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)


def _prune_logs(log_dir: Path) -> None:
    """Delete old log files by age and count.

    Reads LOG_MAX_FILES (default 50) and LOG_MAX_DAYS (default 30) from
    environment variables. Both rules are applied on every call; whichever
    removes more files wins.
    """
    max_files = int(os.environ.get("LOG_MAX_FILES", "50"))
    max_days = int(os.environ.get("LOG_MAX_DAYS", "7"))
    cutoff = datetime.now().timestamp() - max_days * 86400
    files = sorted(log_dir.glob("*.log"), key=lambda f: f.stat().st_mtime)
    # Delete by age first; unlink() returns None so the expression is True only
    # when the file is old, removing it from the list at the same time.
    files = [f for f in files if not (f.stat().st_mtime < cutoff and f.unlink() is None)]
    # Delete by count (oldest first, already sorted ascending by mtime)
    for f in files[:-max_files] if len(files) > max_files else []:
        f.unlink(missing_ok=True)


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
    _prune_logs(log_dir)


def _session_registry_path(sid: str) -> Path:
    return Path(current_app.config["SESSION_REGISTRY_DIR"]) / f"{sid}.json"


def _persist_session(sid: str, sd) -> None:
    """Write upload_dir to the shared registry so other workers can find this session."""
    if not sd.upload_dir:
        return
    path = _session_registry_path(sid)
    path.write_text(json.dumps({"upload_dir": sd.upload_dir}))
    try:
        sd.registry_mtime = path.stat().st_mtime
    except OSError:
        pass


def _forget_session(sid: str) -> None:
    _session_registry_path(sid).unlink(missing_ok=True)


def _load_session_from_disk(sid: str):
    """Check the filesystem registry; re-parse upload_dir into a fresh SessionData."""
    path = _session_registry_path(sid)
    if not path.exists():
        return None
    try:
        meta = json.loads(path.read_text())
    except Exception:
        return None
    upload_dir = meta.get("upload_dir")
    if not upload_dir or not os.path.isdir(upload_dir):
        path.unlink(missing_ok=True)
        return None
    from .app import _parse_configs_for_session
    try:
        servers, graph_data, _ = _parse_configs_for_session(upload_dir)
    except Exception:
        return None
    return SessionData(servers=servers, graph_data=graph_data, upload_dir=upload_dir)


def _get_or_create_session():
    """Read cookie or create new session. Returns (sid, SessionData)."""
    store = current_app.config["SESSION_STORE"]
    lock = current_app.config["SESSION_LOCK"]
    sid = request.cookies.get("namedviz_session")
    with lock:
        if sid and sid in store:
            sd = store[sid]
            sd.last_access = time.time()
            try:
                reg_path = _session_registry_path(sid)
                if reg_path.stat().st_mtime > sd.registry_mtime:
                    fresh = _load_session_from_disk(sid)
                    if fresh:
                        store[sid] = fresh
                        return sid, fresh
                    # reload failed (transient) — keep stale rather than returning nothing
                else:
                    reg_path.touch(exist_ok=True)
            except OSError:
                pass
            return sid, store[sid]
        # Cache miss — check filesystem (different worker may have created this session)
        if sid:
            sd = _load_session_from_disk(sid)
            if sd:
                store[sid] = sd
                return sid, sd
        # Brand new session
        sid = str(uuid.uuid4())
        sd = SessionData()
        store[sid] = sd
        return sid, sd


def _get_session_data():
    """Read-only lookup, no creation. Returns (sid|None, SessionData|None)."""
    store = current_app.config["SESSION_STORE"]
    lock = current_app.config["SESSION_LOCK"]
    sid = request.cookies.get("namedviz_session")
    if not sid:
        return None, None
    with lock:
        if sid in store:
            sd = store[sid]
            sd.last_access = time.time()
            try:
                reg_path = _session_registry_path(sid)
                if reg_path.stat().st_mtime > sd.registry_mtime:
                    fresh = _load_session_from_disk(sid)
                    if fresh:
                        store[sid] = fresh
                        return sid, fresh
                    # reload failed (transient) — keep stale rather than returning nothing
                else:
                    reg_path.touch(exist_ok=True)
            except OSError:
                pass
            return sid, store[sid]
        sd = _load_session_from_disk(sid)
        if sd:
            store[sid] = sd
            return sid, sd
    return None, None


def _set_session_cookie(response, session_id):
    response.set_cookie("namedviz_session", session_id,
                        max_age=3600, httponly=True, samesite="Lax")
    return response


def _effective_data(sd):
    """Return (servers, graph_data) — session's own if present, else defaults."""
    if sd and sd.servers:
        return sd.servers, sd.graph_data
    return (current_app.config.get("DEFAULT_SERVERS", []),
            current_app.config.get("DEFAULT_GRAPH_DATA"))


@api_bp.route("/")
def index():
    return send_from_directory(current_app.static_folder, "index.html")


@api_bp.route("/api/graph")
def get_graph():
    _, sd = _get_session_data()
    _, graph_data = _effective_data(sd)
    if graph_data is None:
        return jsonify({"nodes": [], "links": [], "zones": [], "servers": []})
    return jsonify(asdict(graph_data))


@api_bp.route("/api/server/<name>")
def get_server(name):
    _, sd = _get_session_data()
    servers, _ = _effective_data(sd)
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
    _, sd = _get_session_data()
    servers, _ = _effective_data(sd)
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
        from .app import _parse_configs_for_session
        sid, sd = _get_or_create_session()
        servers, graph_data, warnings = _parse_configs_for_session(config_path)
        sd.servers, sd.graph_data = servers, graph_data
        _save_logs(warnings)
        resp = jsonify({
            "status": "ok",
            "servers": graph_data.servers if graph_data else [],
            "node_count": len(graph_data.nodes) if graph_data else 0,
            "link_count": len(graph_data.links) if graph_data else 0,
            "logs": warnings,
        })
        return _set_session_cookie(resp, sid)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/api/reset", methods=["POST"])
def reset():
    """Clear session data; subsequent requests fall back to defaults."""
    sid, sd = _get_session_data()
    if sd:
        if sd.upload_dir and os.path.isdir(sd.upload_dir):
            shutil.rmtree(sd.upload_dir, ignore_errors=True)
        sd.upload_dir = None
        sd.servers = []
        sd.graph_data = None
        _forget_session(sid)
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

    sid, sd = _get_or_create_session()

    # Remember old dir — will delete AFTER new data is ready
    old_upload_dir = sd.upload_dir if (sd.upload_dir and os.path.isdir(sd.upload_dir)) else None

    # Create a temp directory with server subdirectories
    upload_dir = tempfile.mkdtemp(prefix="namedviz_")

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

        log.info("All files saved. Running _parse_configs_for_session on %s", upload_dir)
        from .app import _parse_configs_for_session
        servers, graph_data, warnings = _parse_configs_for_session(upload_dir)

        # Atomically swap in-memory state (old data stays live until new data is ready)
        sd.servers, sd.graph_data, sd.upload_dir = servers, graph_data, upload_dir

        # Persist to registry BEFORE removing old dir
        _persist_session(sid, sd)

        # Now safe to remove old dir
        if old_upload_dir:
            shutil.rmtree(old_upload_dir, ignore_errors=True)

        _save_logs(warnings)
        if not (graph_data and graph_data.servers):
            return jsonify({
                "error": "No named.conf found in the uploaded folder(s). "
                         "Make sure your BIND configuration folder contains a named.conf file."
            }), 400
        resp = jsonify({
            "status": "ok",
            "servers": graph_data.servers,
            "node_count": len(graph_data.nodes),
            "link_count": len(graph_data.links),
            "logs": warnings,
        })
        return _set_session_cookie(resp, sid)
    except Exception as e:
        tb = traceback.format_exc()
        log.exception("Upload failed")
        return jsonify({"error": str(e), "traceback": tb}), 500
