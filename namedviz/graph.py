"""Build a visualization graph from parsed server configs."""

from __future__ import annotations

from .models import GraphData, ServerConfig, Relationship
from .parser.extractor import resolve_relationships


def build_graph(servers: list[ServerConfig]) -> GraphData:
    """Build a D3-ready graph from server configs."""
    relationships = resolve_relationships(servers)

    server_names = {s.name for s in servers}

    # Collect all node IDs (servers + external IPs)
    all_endpoints = {r.target for r in relationships} | {r.source for r in relationships}
    external_nodes = all_endpoints - server_names

    # Build nodes
    nodes = []
    for server in servers:
        zone_count = len(server.zones)
        role = _server_role(server)
        nodes.append({
            "id": server.name,
            "type": "server",
            "role": role,
            "zone_count": zone_count,
            "zone_counts": _zone_type_counts(server),
            "zones": [_zone_summary(z) for z in server.zones],
            "listen_on": server.listen_on,
        })

    # Collect views referencing each external node
    ext_views: dict[str, set[str]] = {}
    for rel in relationships:
        if rel.view_name:
            if rel.target in external_nodes:
                ext_views.setdefault(rel.target, set()).add(rel.view_name)
            if rel.source in external_nodes:
                ext_views.setdefault(rel.source, set()).add(rel.view_name)

    for ext in sorted(external_nodes):
        nodes.append({
            "id": ext,
            "type": "external",
            "zone_count": 0,
            "zones": [],
            "views": sorted(ext_views.get(ext, [])),
        })

    # Aggregate links: one per (source, target, rel_type)
    link_key_map: dict[tuple[str, str, str], dict] = {}
    for rel in relationships:
        key = (rel.source, rel.target, rel.rel_type)
        if key not in link_key_map:
            link_key_map[key] = {
                "source": rel.source,
                "target": rel.target,
                "rel_type": rel.rel_type,
                "zones": [],
                "count": 0,
            }
        link_key_map[key]["zones"].append(rel.zone_name)
        link_key_map[key]["count"] += 1

    links = list(link_key_map.values())

    # Zone summaries for the API
    zone_list = []
    for server in servers:
        for z in server.zones:
            zone_list.append(_zone_summary(z))

    return GraphData(
        nodes=nodes,
        links=links,
        zones=zone_list,
        servers=[s.name for s in servers],
    )


def _zone_type_counts(server: ServerConfig) -> dict[str, int]:
    """Count zones by type, normalizing primary→master and secondary→slave."""
    counts: dict[str, int] = {}
    for z in server.zones:
        zt = z.zone_type
        if zt == "primary":
            zt = "master"
        if zt == "secondary":
            zt = "slave"
        counts[zt] = counts.get(zt, 0) + 1
    return counts


def _server_role(server: ServerConfig) -> str:
    """Determine the primary role of a server: master, slave, or mixed."""
    has_master = any(z.zone_type in ("master", "primary") for z in server.zones)
    has_slave = any(z.zone_type in ("slave", "secondary") for z in server.zones)
    if has_master and has_slave:
        return "mixed"
    if has_master:
        return "master"
    if has_slave:
        return "slave"
    return "other"


def _zone_summary(zone) -> dict:
    return {
        "name": zone.name,
        "type": zone.zone_type,
        "server": zone.server_name,
        "view": zone.view,
    }
