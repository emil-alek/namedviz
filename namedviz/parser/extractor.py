"""Extract ServerConfig objects from parsed named.conf results."""

from __future__ import annotations

from ..models import ServerConfig, Zone, Relationship
from .loader import discover_configs, load_and_parse


def extract_server_config(server_name: str, parse_results) -> ServerConfig:
    """Walk parse results and build a ServerConfig."""
    config = ServerConfig(name=server_name)

    _extract_from_results(config, parse_results, view_name=None)
    return config


def _extract_from_results(config: ServerConfig, results, view_name: str | None):
    """Recursively extract data from parse results."""
    for item in results:
        name = item.getName() if hasattr(item, "getName") else ""

        if name == "zone":
            zone = _extract_zone(config.name, item, view_name)
            if zone:
                config.zones.append(zone)

        elif name == "options":
            _extract_options(config, item)

        elif name == "acl":
            acl_name = item.get("acl_name", "")
            entries = list(item.get("entries", []))
            if acl_name:
                config.acls[acl_name] = entries

        elif name == "view":
            vname = item.get("view_name", "")
            _extract_from_results(config, item, view_name=vname)


def _extract_zone(server_name: str, item, view_name: str | None) -> Zone | None:
    """Extract a Zone from a parsed zone block."""
    zone_name = item.get("zone_name", "")
    if not zone_name:
        return None

    zone_type_item = item.get("zone_type")
    zone_type = ""
    if zone_type_item is not None:
        zone_type = zone_type_item.get("value", "") if hasattr(zone_type_item, "get") else str(zone_type_item)

    file_item = item.get("file")
    file_path = None
    if file_item is not None:
        file_path = file_item.get("value", "") if hasattr(file_item, "get") else str(file_item)

    masters = list(item.get("masters", []))
    forwarders = list(item.get("forwarders", []))
    allow_transfer = list(item.get("allow_transfer", []))
    also_notify = list(item.get("also_notify", []))

    return Zone(
        name=zone_name,
        zone_type=zone_type,
        server_name=server_name,
        view=view_name,
        masters=masters,
        forwarders=forwarders,
        allow_transfer=allow_transfer,
        also_notify=also_notify,
        file=file_path,
    )


def _extract_options(config: ServerConfig, item):
    """Extract global options."""
    forwarders = list(item.get("forwarders", []))
    if forwarders:
        config.global_forwarders = forwarders

    also_notify = list(item.get("also_notify", []))
    if also_notify:
        config.global_also_notify = also_notify

    allow_transfer = list(item.get("allow_transfer", []))
    if allow_transfer:
        config.global_allow_transfer = allow_transfer

    for key in ("listen_on", "listen_on_v6"):
        ips = list(item.get(key, []))
        config.listen_on.extend(
            ip for ip in ips if ip not in ("any", "none", "localhost")
        )


def extract_all(config_path: str) -> tuple[list[ServerConfig], list[dict]]:
    """Discover, parse, and extract all server configs from a path.

    Returns (servers, logs).  Each log entry is a dict with 'level' and 'message'.
    """
    configs = discover_configs(config_path)
    servers = []
    all_logs: list[dict] = []
    for server_name, file_path in configs.items():
        results, logs = load_and_parse(file_path)
        server = extract_server_config(server_name, results)
        servers.append(server)
        for entry in logs:
            all_logs.append({
                "level": entry["level"],
                "message": f"[{server_name}] {entry['message']}",
            })
        all_logs.append({
            "level": "info",
            "message": f"[{server_name}] Parsed {len(server.zones)} zone(s)",
        })
    return servers, all_logs


def resolve_relationships(servers: list[ServerConfig]) -> list[Relationship]:
    """Build relationships between servers by cross-referencing IPs and zones.

    For slave zones, maps the masters IPs back to known servers.
    Also extracts also-notify, allow-transfer, and forward relationships.
    """
    # Build IP-to-server mapping: find IPs that servers are known by
    # A server is "known by" the IPs listed as masters in other servers' slave zones
    # But more directly, we map: for each master zone on server X,
    # if server Y has a slave zone with masters containing IP,
    # then IP -> server X (if we can determine it)
    #
    # Simpler approach: build a map of (zone_name, zone_type=master) -> server_name
    master_zones: dict[str, str] = {}
    for server in servers:
        for zone in server.zones:
            if zone.zone_type in ("master", "primary"):
                master_zones[zone.name] = server.name

    # Build IP-to-server map from listen-on declarations
    ip_to_server: dict[str, str] = {}
    for server in servers:
        for ip in server.listen_on:
            if ip not in ip_to_server:
                ip_to_server[ip] = server.name

    server_names = {s.name for s in servers}
    relationships: list[Relationship] = []

    for server in servers:
        for zone in server.zones:
            # Slave -> Master relationships
            if zone.zone_type in ("slave", "secondary"):
                for ip in zone.masters:
                    # Try to resolve IP to a known server that masters this zone
                    target = master_zones.get(zone.name)
                    if target is None:
                        target = _resolve_ip(ip, servers, server_names, ip_to_server)
                    relationships.append(Relationship(
                        source=server.name,
                        target=target,
                        rel_type="master_slave",
                        zone_name=zone.name,
                    ))

            # Also-notify relationships (master notifies others)
            if zone.zone_type in ("master", "primary"):
                notify_list = zone.also_notify or server.global_also_notify
                for ip in notify_list:
                    target = _resolve_ip(ip, servers, server_names, ip_to_server)
                    relationships.append(Relationship(
                        source=server.name,
                        target=target,
                        rel_type="also_notify",
                        zone_name=zone.name,
                    ))

            # Allow-transfer relationships
            if zone.zone_type in ("master", "primary"):
                transfer_list = zone.allow_transfer or server.global_allow_transfer
                for ip in transfer_list:
                    if ip in ("any", "none", "localhost"):
                        continue
                    target = _resolve_ip(ip, servers, server_names, ip_to_server)
                    relationships.append(Relationship(
                        source=server.name,
                        target=target,
                        rel_type="allow_transfer",
                        zone_name=zone.name,
                    ))

            # Forward relationships
            if zone.zone_type == "forward":
                fwd_list = zone.forwarders or server.global_forwarders
                for ip in fwd_list:
                    target = _resolve_ip(ip, servers, server_names, ip_to_server)
                    relationships.append(Relationship(
                        source=server.name,
                        target=target,
                        rel_type="forward",
                        zone_name=zone.name,
                    ))

    return relationships


def _resolve_ip(ip: str, servers: list[ServerConfig], server_names: set[str],
                ip_to_server: dict[str, str] | None = None) -> str:
    """Try to resolve an IP to a known server name. Return IP if unresolvable."""
    if ip in server_names:
        return ip
    if ip_to_server and ip in ip_to_server:
        return ip_to_server[ip]
    return ip
