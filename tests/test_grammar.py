"""Tests for the pyparsing grammar."""

import pytest
from namedviz.parser.grammar import parse_named_conf


def test_parse_basic_zone():
    text = '''
    zone "example.com" {
        type master;
        file "example.com.zone";
    };
    '''
    result = parse_named_conf(text)
    zones = [r for r in result if r.getName() == "zone"]
    assert len(zones) == 1
    assert zones[0]["zone_name"] == "example.com"
    assert zones[0]["zone_type"]["value"] == "master"


def test_parse_slave_zone_with_masters():
    text = '''
    zone "example.com" {
        type slave;
        masters { 10.0.0.1; 10.0.0.2; };
        file "slaves/example.com.zone";
    };
    '''
    result = parse_named_conf(text)
    zones = [r for r in result if r.getName() == "zone"]
    assert len(zones) == 1
    masters = list(zones[0]["masters"])
    assert "10.0.0.1" in masters
    assert "10.0.0.2" in masters


def test_parse_zone_with_also_notify_and_transfer():
    text = '''
    zone "example.com" {
        type master;
        file "example.com.zone";
        also-notify { 10.0.0.2; 10.0.0.3; };
        allow-transfer { 10.0.0.2; };
    };
    '''
    result = parse_named_conf(text)
    zones = [r for r in result if r.getName() == "zone"]
    assert len(zones) == 1
    also_notify = list(zones[0]["also_notify"])
    assert len(also_notify) == 2
    allow_transfer = list(zones[0]["allow_transfer"])
    assert len(allow_transfer) == 1


def test_parse_forward_zone():
    text = '''
    zone "cdn.example.com" {
        type forward;
        forwarders { 203.0.113.10; 203.0.113.11; };
    };
    '''
    result = parse_named_conf(text)
    zones = [r for r in result if r.getName() == "zone"]
    assert len(zones) == 1
    assert zones[0]["zone_type"]["value"] == "forward"
    forwarders = list(zones[0]["forwarders"])
    assert len(forwarders) == 2


def test_parse_options_block():
    text = '''
    options {
        directory "/var/named";
        forwarders { 8.8.8.8; 8.8.4.4; };
        allow-transfer { 10.0.0.2; };
    };
    '''
    result = parse_named_conf(text)
    options = [r for r in result if r.getName() == "options"]
    assert len(options) == 1
    forwarders = list(options[0]["forwarders"])
    assert "8.8.8.8" in forwarders


def test_parse_acl_block():
    text = '''
    acl "internal" {
        10.0.0.0/8;
        172.16.0.0/12;
    };
    '''
    result = parse_named_conf(text)
    acls = [r for r in result if r.getName() == "acl"]
    assert len(acls) == 1
    assert acls[0]["acl_name"] == "internal"


def test_parse_view_block():
    text = '''
    view "internal" {
        zone "example.com" {
            type master;
            file "internal/example.com.zone";
        };
    };
    '''
    result = parse_named_conf(text)
    views = [r for r in result if r.getName() == "view"]
    assert len(views) == 1
    assert views[0]["view_name"] == "internal"


def test_skip_comments():
    text = '''
    // C++ comment
    # Shell comment
    /* C comment */
    zone "example.com" {
        type master;
        file "example.com.zone";
    };
    '''
    result = parse_named_conf(text)
    zones = [r for r in result if r.getName() == "zone"]
    assert len(zones) == 1


def test_skip_unknown_blocks():
    text = '''
    logging {
        channel default_log {
            file "/var/log/named.log" versions 3 size 5m;
            severity info;
        };
    };

    zone "example.com" {
        type master;
        file "example.com.zone";
    };
    '''
    result = parse_named_conf(text)
    zones = [r for r in result if r.getName() == "zone"]
    assert len(zones) == 1


def test_parse_multiple_zones():
    text = '''
    zone "a.com" { type master; file "a.zone"; };
    zone "b.com" { type slave; masters { 10.0.0.1; }; file "b.zone"; };
    zone "c.com" { type forward; forwarders { 8.8.8.8; }; };
    '''
    result = parse_named_conf(text)
    zones = [r for r in result if r.getName() == "zone"]
    assert len(zones) == 3


def test_parse_primaries_alias():
    """Test that 'primaries' works as an alias for 'masters'."""
    text = '''
    zone "example.com" {
        type slave;
        primaries { 10.0.0.1; };
        file "slaves/example.com.zone";
    };
    '''
    result = parse_named_conf(text)
    zones = [r for r in result if r.getName() == "zone"]
    assert len(zones) == 1
    masters = list(zones[0]["masters"])
    assert "10.0.0.1" in masters


def test_parse_listen_on():
    text = '''
    options {
        listen-on { 10.0.0.1; };
    };
    '''
    result = parse_named_conf(text)
    options = [r for r in result if r.getName() == "options"]
    assert len(options) == 1
    listen = list(options[0]["listen_on"])
    assert "10.0.0.1" in listen


def test_parse_listen_on_with_port():
    text = '''
    options {
        listen-on port 53 { 10.0.0.1; 10.0.0.2; };
    };
    '''
    result = parse_named_conf(text)
    options = [r for r in result if r.getName() == "options"]
    assert len(options) == 1
    listen = list(options[0]["listen_on"])
    assert "10.0.0.1" in listen
    assert "10.0.0.2" in listen


def test_parse_listen_on_v6():
    text = '''
    options {
        listen-on-v6 { ::1; };
    };
    '''
    result = parse_named_conf(text)
    options = [r for r in result if r.getName() == "options"]
    assert len(options) == 1
    listen_v6 = list(options[0]["listen_on_v6"])
    assert len(listen_v6) >= 1


def test_parse_listen_on_with_any():
    text = '''
    options {
        listen-on { any; };
    };
    '''
    result = parse_named_conf(text)
    options = [r for r in result if r.getName() == "options"]
    assert len(options) == 1
    listen = list(options[0]["listen_on"])
    assert "any" in listen
