"""Flask app factory."""

from __future__ import annotations

from dataclasses import asdict
from flask import Flask, Request as FlaskRequest

from .api import api_bp


class _UnlimitedRequest(FlaskRequest):
    """Override Werkzeug 3.x form-data limits for large BIND config uploads."""
    max_form_memory_size: int | None = None   # non-file field names only; negligible
    max_form_parts: int | None = 2000         # was 1000 (caused 413 with 1069 files)


def create_app(config_path: str | None = None) -> Flask:
    """Create and configure the Flask app.

    If config_path is provided, configs are parsed on startup.
    """
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.request_class = _UnlimitedRequest

    app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB

    # Store config path and parsed data in app config
    app.config["CONFIG_PATH"] = config_path
    app.config["SERVERS"] = []
    app.config["GRAPH_DATA"] = None

    app.register_blueprint(api_bp)

    if config_path:
        with app.app_context():
            _parse_configs(app)

    return app


def _parse_configs(app: Flask) -> list[str]:
    """Parse configs and store results in app config. Returns warnings."""
    from .parser.extractor import extract_all
    from .graph import build_graph

    config_path = app.config["CONFIG_PATH"]
    if not config_path:
        return []

    servers, warnings = extract_all(config_path)
    graph_data = build_graph(servers)

    app.config["SERVERS"] = servers
    app.config["GRAPH_DATA"] = graph_data
    return warnings
