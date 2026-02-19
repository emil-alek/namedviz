#!/usr/bin/env python3
"""Entry point for namedviz.

Usage:
    python run.py                   # Start with upload UI (no pre-loaded configs)
    python run.py /path/to/configs  # Pre-load configs from a directory
"""

import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from namedviz.app import create_app


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else None

    if config_path:
        print(f"Parsing configs from: {config_path}")
    else:
        print("Starting in upload mode (no configs pre-loaded)")

    app = create_app(config_path)

    servers = app.config.get("SERVERS", [])
    graph = app.config.get("GRAPH_DATA")
    if servers:
        print(f"Found {len(servers)} server(s)")
    if graph:
        print(f"Graph: {len(graph.nodes)} nodes, {len(graph.links)} links")

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print(f"Starting server at http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
