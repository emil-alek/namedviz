"""Flask app factory."""

from __future__ import annotations

from dataclasses import asdict
from flask import Flask

from .api import api_bp


def create_app(config_path: str | None = None) -> Flask:
    """Create and configure the Flask app.

    If config_path is provided, configs are parsed on startup.
    """
    app = Flask(__name__, static_folder="static", static_url_path="/static")

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
