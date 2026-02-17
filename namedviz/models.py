from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Zone:
    name: str
    zone_type: str  # master/slave/forward/stub/hint
    server_name: str
    view: str | None = None
    masters: list[str] = field(default_factory=list)
    forwarders: list[str] = field(default_factory=list)
    allow_transfer: list[str] = field(default_factory=list)
    also_notify: list[str] = field(default_factory=list)
    file: str | None = None


@dataclass
class ServerConfig:
    name: str
    zones: list[Zone] = field(default_factory=list)
    listen_on: list[str] = field(default_factory=list)
    acls: dict[str, list[str]] = field(default_factory=dict)
    global_forwarders: list[str] = field(default_factory=list)
    global_also_notify: list[str] = field(default_factory=list)
    global_allow_transfer: list[str] = field(default_factory=list)
    view_server_ips: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class Relationship:
    source: str
    target: str
    rel_type: str  # master_slave / also_notify / allow_transfer / forward
    zone_name: str


@dataclass
class GraphData:
    nodes: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    zones: list[dict] = field(default_factory=list)
    servers: list[str] = field(default_factory=list)
