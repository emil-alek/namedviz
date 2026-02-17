"""pyparsing grammar for BIND named.conf files.

Only parses the directives we care about (zone, acl, options, view)
and gracefully skips everything else.
"""

from __future__ import annotations

import pyparsing as pp

pp.ParserElement.enable_packrat()

# ---------- unknown-statement warning collection ----------
_unknown_warnings: list[str] = []


def get_unknown_warnings() -> list[str]:
    """Return and clear warnings for unknown statements encountered during parsing."""
    warnings = list(_unknown_warnings)
    _unknown_warnings.clear()
    return warnings


def _on_unknown(tokens):
    _unknown_warnings.append(str(tokens[0]))
    return []


# ---------- primitives ----------
SEMI = pp.Suppress(pp.Literal(";"))
LBRACE = pp.Suppress(pp.Literal("{"))
RBRACE = pp.Suppress(pp.Literal("}"))

# Comments: //, /* */, #
comment = pp.cppStyleComment | pp.pythonStyleComment

# Quoted or bare string
quoted_string = pp.QuotedString('"') | pp.QuotedString("'")
bare_word = pp.Regex(r'[A-Za-z0-9_./:\-!]+')
value = quoted_string | bare_word

# IP address (with optional port and TSIG key, we just grab the IP)
ip_addr = pp.Regex(r'[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+')

# ---------- helpers ----------

def _ip_list(name: str):
    """An IP list like: masters { 10.0.0.1; 10.0.0.2; };"""
    key_keyword = pp.Keyword(name) | (pp.Keyword(name.rstrip("s") + "ies") if name.endswith("s") else pp.NoMatch())
    # Also handle 'primaries' as alias for 'masters'
    if name == "masters":
        key_keyword = pp.Keyword("masters") | pp.Keyword("primaries")
    elif name == "forwarders":
        key_keyword = pp.Keyword("forwarders")
    elif name == "also-notify":
        key_keyword = pp.Keyword("also-notify")
    elif name == "allow-transfer":
        key_keyword = pp.Keyword("allow-transfer")

    # Items can be IPs, ACL names, 'key' references, 'port' specs — grab values
    item = ip_addr | value
    return pp.Group(
        pp.Suppress(key_keyword)
        + LBRACE
        + pp.ZeroOrMore(item + SEMI)
        + RBRACE
        + SEMI
    )(name.replace("-", "_"))


def _keyword_value(name: str):
    """A simple keyword value; like: type master;"""
    return pp.Suppress(pp.Keyword(name)) + value("value") + SEMI


# ---------- zone internals ----------

zone_type_stmt = pp.Group(
    pp.Suppress(pp.Keyword("type")) + value("value") + SEMI
)("zone_type")

file_stmt = pp.Group(
    pp.Suppress(pp.Keyword("file")) + value("value") + SEMI
)("file")

masters_stmt = _ip_list("masters")
forwarders_stmt = _ip_list("forwarders")
also_notify_stmt = _ip_list("also-notify")
allow_transfer_stmt = _ip_list("allow-transfer")

# Catch-all for unknown statements inside blocks
# Matches: keyword value* ;  OR  keyword value* { ... } ;?
# Captures the keyword for warning reporting, then suppresses the rest.
_nested_braces = pp.nested_expr("{", "}")
unknown_stmt = (
    bare_word.copy().add_parse_action(_on_unknown)
    + pp.Suppress(
        pp.ZeroOrMore(value | pp.Regex(r'!'))
        + (
            (LBRACE + pp.SkipTo("}") + RBRACE + pp.Optional(pp.Literal(";")))
            | SEMI
        )
    )
)

zone_body_stmt = (
    zone_type_stmt
    | file_stmt
    | masters_stmt
    | forwarders_stmt
    | also_notify_stmt
    | allow_transfer_stmt
    | unknown_stmt
)

# ---------- zone block ----------

zone_block = pp.Group(
    pp.Suppress(pp.Keyword("zone"))
    + value("zone_name")
    + pp.Optional(pp.Suppress(value))  # optional class like IN
    + LBRACE
    + pp.ZeroOrMore(zone_body_stmt)
    + RBRACE
    + SEMI
)("zone*")

# ---------- options block ----------

options_forwarders = _ip_list("forwarders")
options_also_notify = _ip_list("also-notify")
options_allow_transfer = _ip_list("allow-transfer")

options_listen_on_v6 = pp.Group(
    pp.Suppress(pp.Keyword("listen-on-v6"))
    + pp.Optional(pp.Suppress(pp.Keyword("port") + value))
    + LBRACE + pp.ZeroOrMore((ip_addr | value) + SEMI) + RBRACE + SEMI
)("listen_on_v6")

options_listen_on = pp.Group(
    pp.Suppress(pp.Keyword("listen-on"))
    + pp.Optional(pp.Suppress(pp.Keyword("port") + value))
    + LBRACE + pp.ZeroOrMore((ip_addr | value) + SEMI) + RBRACE + SEMI
)("listen_on")

options_body_stmt = (
    options_forwarders
    | options_also_notify
    | options_allow_transfer
    | options_listen_on_v6
    | options_listen_on
    | unknown_stmt
)

options_block = pp.Group(
    pp.Suppress(pp.Keyword("options"))
    + LBRACE
    + pp.ZeroOrMore(options_body_stmt)
    + RBRACE
    + SEMI
)("options*")

# ---------- acl block ----------

acl_block = pp.Group(
    pp.Suppress(pp.Keyword("acl"))
    + value("acl_name")
    + LBRACE
    + pp.ZeroOrMore(value + SEMI)("entries")
    + RBRACE
    + SEMI
)("acl*")

# ---------- view block ----------

server_stmt = pp.Group(
    pp.Suppress(pp.Keyword("server"))
    + ip_addr("ip")
    + pp.Optional(pp.Suppress(LBRACE + pp.SkipTo("}") + RBRACE))
    + SEMI
)("view_servers*")


view_body_stmt = (
    zone_block
    | also_notify_stmt
    | allow_transfer_stmt
    | forwarders_stmt
    | server_stmt
    | unknown_stmt
)

view_block = pp.Group(
    pp.Suppress(pp.Keyword("view"))
    + value("view_name")
    + pp.Optional(pp.Suppress(value))  # optional class
    + LBRACE
    + pp.ZeroOrMore(view_body_stmt)
    + RBRACE
    + SEMI
)("view*")

# ---------- include directive ----------

include_directive = pp.Group(
    pp.Suppress(pp.Keyword("include"))
    + value("path")
    + SEMI
)("include*")

# ---------- top-level ----------

# Skip unknown top-level blocks (logging, controls, etc.)
unknown_top_block = (
    bare_word.copy().add_parse_action(_on_unknown)
    + pp.Suppress(
        pp.ZeroOrMore(value)
        + pp.nested_expr("{", "}")
        + pp.Optional(pp.Literal(";"))
    )
)

unknown_top_stmt = (
    bare_word.copy().add_parse_action(_on_unknown)
    + pp.Suppress(pp.OneOrMore(value) + SEMI)
)

top_level_stmt = (
    zone_block
    | options_block
    | acl_block
    | view_block
    | include_directive
    | unknown_top_block
    | unknown_top_stmt
)

named_conf = pp.ZeroOrMore(top_level_stmt)
named_conf.ignore(comment)


def parse_named_conf(text: str) -> pp.ParseResults:
    """Parse a named.conf file and return structured results."""
    _unknown_warnings.clear()
    return named_conf.parse_string(text, parse_all=True)
