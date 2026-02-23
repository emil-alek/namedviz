"""Flask app factory."""

from __future__ import annotations

import threading
import time
from flask import Flask, Request as FlaskRequest

from .api import api_bp


class _UnlimitedRequest(FlaskRequest):
    """Override Werkzeug 3.x form-data limits for large BIND config uploads."""
    max_form_memory_size: int | None = 500 * 1024 * 1024  # 500 MB, matches MAX_CONTENT_LENGTH
    max_form_parts: int | None = 5000         # was 1000 (caused 413 with 1069 files)


def create_app(config_path: str | None = None) -> Flask:
    """Create and configure the Flask app.

    If config_path is provided, configs are parsed on startup into DEFAULT_*.
    """
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.request_class = _UnlimitedRequest

    app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB

    # Store config path and parsed data in app config
    app.config["CONFIG_PATH"] = config_path
    app.config["SESSION_STORE"] = {}       # {str: SessionData}
    app.config["DEFAULT_SERVERS"] = []
    app.config["DEFAULT_GRAPH_DATA"] = None

    # Protects in-memory SESSION_STORE mutations within a single worker process
    app.config["SESSION_LOCK"] = threading.RLock()

    app.register_blueprint(api_bp)

    if config_path:
        with app.app_context():
            _load_default_configs(app)

    t = threading.Thread(target=_session_cleanup_loop, args=(app,), daemon=True)
    t.start()

    return app


def _load_default_configs(app: Flask) -> list[str]:
    """Parse startup configs into DEFAULT_* keys. Returns warnings."""
    from .parser.extractor import extract_all
    from .graph import build_graph

    config_path = app.config.get("CONFIG_PATH")
    if not config_path:
        return []

    servers, warnings = extract_all(config_path)
    app.config["DEFAULT_SERVERS"] = servers
    app.config["DEFAULT_GRAPH_DATA"] = build_graph(servers)
    return warnings


def _parse_configs_for_session(config_path: str):
    """Pure function: parse configs at path and return (servers, graph_data, warnings)."""
    from .parser.extractor import extract_all
    from .graph import build_graph

    servers, warnings = extract_all(config_path)
    return servers, build_graph(servers), warnings


def _session_cleanup_loop(app: Flask) -> None:
    while True:
        time.sleep(600)   # sweep every 10 minutes
        cutoff = time.time() - 3600
        store = app.config["SESSION_STORE"]
        lock = app.config["SESSION_LOCK"]
        with lock:
            stale = [sid for sid, sd in store.items() if sd.last_access < cutoff]
            for sid in stale:
                del store[sid]
