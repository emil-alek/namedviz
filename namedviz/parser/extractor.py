"""Extract ServerConfig objects from parsed named.conf results."""

from __future__ import annotations

from ..models import ServerConfig, Zone, Relationship
from .loader import discover_configs, load_and_parse


def extract_server_config(server_name: str, parse_results) -> ServerConfig:
    """Walk parse results and build a ServerConfig."""
    config = ServerConfig(name=server_name)

    _extract_from_results(config, parse_results, view_name=None)
    return config


def _extract_from_results(
    config: ServerConfig,
    results,
    view_name: str | None,
    view_also_notify: list[str] | None = None,
    view_allow_transfer: list[str] | None = None,
    view_forwarders: list[str] | None = None,
):  
    """Recursively extract data from parse results."""
    for item in results:
        name = item.getName() if hasattr(item, "getName") else ""

        if name == "zone":
            zone = _extract_zone(config.name, item, view_name)
            if zone:
                # Apply view-level fallbacks (zone > view > global)
                if not zone.also_notify and view_also_notify:
                    zone.also_notify = list(view_also_notify)
                if not zone.allow_transfer and view_allow_transfer:
                    zone.allow_transfer = list(view_allow_transfer)
                if not zone.forwarders and view_forwarders:
                    zone.forwarders = list(view_forwarders)
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
            # Extract view-level options
            v_also_notify = list(item.get("also_notify", []))
            v_allow_transfer = list(item.get("allow_transfer", []))
            v_forwarders = list(item.get("forwarders", []))
            # Extract view-level server statements
            v_servers = [s["ip"] for s in item.get("view_servers", [])]
            if v_servers and vname:
                config.view_server_ips[vname] = v_servers
            _extract_from_results(
                config, item, view_name=vname,
                view_also_notify=v_also_notify or None,
                view_allow_transfer=v_allow_transfer or None,
                view_forwarders=v_forwarders or None,
            )


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
            # Master → Slave relationships (arrow = direction of authority / data flow)
            if zone.zone_type in ("slave", "secondary"):
                # Phase 1: prefer zone-name match (reliable when master is loaded).
                master = master_zones.get(zone.name)
                if master is not None:
                    relationships.append(Relationship(
                        source=master,
                        target=server.name,
                        rel_type="master_slave",
                        zone_name=zone.name,
                        view_name=zone.view or "",
                    ))
                else:
                    # Phase 2: master not loaded; resolve each unique masters IP.
                    seen: set[str] = set()
                    for ip in zone.masters:
                        src = _resolve_ip(ip, servers, server_names, ip_to_server)
                        if src not in seen:
                            seen.add(src)
                            relationships.append(Relationship(
                                source=src,
                                target=server.name,
                                rel_type="master_slave",
                                zone_name=zone.name,
                                view_name=zone.view or "",
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
                        view_name=zone.view or "",
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
                        view_name=zone.view or "",
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
                        view_name=zone.view or "",
                    ))

    # View-level server statements → peer relationships
    for server in servers:
        for view_name, server_ips in server.view_server_ips.items():
            for ip in server_ips:
                peer_name = _resolve_ip(ip, servers, server_names, ip_to_server)
                relationships.append(Relationship(
                    source=server.name,
                    target=peer_name,
                    rel_type="peer",
                    zone_name="",
                    view_name=view_name,
                ))

    # Drop self-referential relationships (e.g. slave zone whose master IP
    # resolves back to the same server via listen-on)
    relationships = [r for r in relationships if r.source != r.target]

    return relationships


def _resolve_ip(ip: str, servers: list[ServerConfig], server_names: set[str],
                ip_to_server: dict[str, str] | None = None) -> str:
    """Try to resolve an IP to a known server name. Return IP if unresolvable."""
    if ip in server_names:
        return ip
    if ip_to_server and ip in ip_to_server:
        return ip_to_server[ip]
    return ip
