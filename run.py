#!/usr/bin/env python3
"""Entry point for namedviz.

Usage:
    python run.py                   # Start with upload UI (no pre-loaded configs)
    python run.py /path/to/configs  # Pre-load configs from a directory
"""

import sys

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

    print("Starting server at http://localhost:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)


if __name__ == "__main__":
    main()
