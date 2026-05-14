"""Parse share links (vless / vmess / ss / socks5) into server dicts.

The output dict shape matches `backend.models.server.parse_server` so it can be
fed straight into VpnService.add_server.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import urllib.parse as urlparse
import uuid


def _b64_decode_padded(data: str) -> bytes:
    data = data.strip().replace("\n", "").replace("\r", "")
    pad = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(data + pad)
    except (binascii.Error, ValueError):
        try:
            return base64.b64decode(data + pad)
        except (binascii.Error, ValueError):
            return b""


def parse_subscription_body(body: str) -> list[str]:
    """Return a list of share-link strings from a raw subscription body.

    Body may be:
      - Base64 of newline-separated share links (most common).
      - Plain text with newline-separated share links.
    """
    body = body.strip()
    if not body:
        return []
    if "://" not in body:
        decoded = _b64_decode_padded(body)
        try:
            body = decoded.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            return []
    out: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if "://" in line:
            out.append(line)
    return out


def parse_share_link(link: str) -> dict | None:
    link = link.strip()
    if link.startswith("vless://"):
        return _parse_vless(link)
    if link.startswith("vmess://"):
        return _parse_vmess(link)
    if link.startswith("ss://"):
        return _parse_ss(link)
    if link.startswith("socks5://") or link.startswith("socks://"):
        return _parse_socks5(link)
    return None


def _decode_name(fragment: str) -> str:
    return urlparse.unquote(fragment or "").strip() or "imported"


def _parse_vless(link: str) -> dict | None:
    parsed = urlparse.urlparse(link)
    if not parsed.username or not parsed.hostname or not parsed.port:
        return None
    q = urlparse.parse_qs(parsed.query)

    def _q(k: str, default: str = "") -> str:
        return (q.get(k, [default]) or [default])[0]

    out: dict = {
        "name": _decode_name(parsed.fragment),
        "protocol": "vless",
        "address": parsed.hostname,
        "port": int(parsed.port),
        "uuid": parsed.username,
        "transport": _q("type", "tcp") or "tcp",
    }
    sec = _q("security", "")
    out["security"] = sec if sec in ("tls", "reality", "none") else None
    out["tls"] = bool(sec in ("tls", "reality"))
    sni = _q("sni") or _q("host")
    if sni:
        out["sni"] = sni
    for src, dst in [
        ("flow", "flow"),
        ("fp", "fp"),
        ("pbk", "pbk"),
        ("sid", "sid"),
        ("path", "path"),
        ("serviceName", "serviceName"),
    ]:
        v = _q(src)
        if v:
            out[dst] = v
    out["id"] = _gen_id("vless", out["address"], out["port"], out["uuid"])
    return {k: v for k, v in out.items() if v is not None}


def _parse_vmess(link: str) -> dict | None:
    payload = link[len("vmess://"):]
    decoded = _b64_decode_padded(payload)
    if not decoded:
        return None
    try:
        obj = json.loads(decoded.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, ValueError):
        return None
    addr = obj.get("add")
    port = obj.get("port")
    uuid_ = obj.get("id")
    if not addr or not port or not uuid_:
        return None
    out = {
        "name": obj.get("ps") or "imported",
        "protocol": "vmess",
        "address": addr,
        "port": int(port),
        "uuid": uuid_,
        "alterId": int(obj.get("aid") or 0),
        "security": obj.get("scy") or "auto",
        "transport": obj.get("net") or "tcp",
        "tls": (obj.get("tls") == "tls"),
    }
    if obj.get("sni") or obj.get("host"):
        out["sni"] = obj.get("sni") or obj.get("host")
    if obj.get("path"):
        out["path"] = obj["path"]
    if obj.get("host"):
        out["host"] = obj["host"]
    out["id"] = _gen_id("vmess", out["address"], out["port"], out["uuid"])
    return out


def _parse_ss(link: str) -> dict | None:
    # Two common forms:
    #   ss://base64(method:password)@host:port#name
    #   ss://base64(method:password@host:port)#name
    rest = link[len("ss://"):]
    frag = ""
    if "#" in rest:
        rest, frag = rest.split("#", 1)
    name = _decode_name(frag)

    method: str | None = None
    password: str | None = None
    host: str | None = None
    port: int | None = None

    if "@" in rest:
        creds_b64, host_part = rest.rsplit("@", 1)
        creds = _b64_decode_padded(creds_b64).decode("utf-8", errors="replace")
        if ":" in creds:
            method, password = creds.split(":", 1)
        if ":" in host_part:
            h, p = host_part.rsplit(":", 1)
            host = h
            try:
                port = int(p)
            except ValueError:
                pass
    else:
        whole = _b64_decode_padded(rest).decode("utf-8", errors="replace")
        m = re.match(r"^([^:]+):([^@]+)@([^:]+):(\d+)$", whole)
        if m:
            method, password, host, port = m.group(1), m.group(2), m.group(3), int(m.group(4))

    if not method or not password or not host or not port:
        return None
    return {
        "id": _gen_id("ss", host, port, password),
        "name": name,
        "protocol": "shadowsocks",
        "address": host,
        "port": port,
        "method": method,
        "password": password,
    }


def _parse_socks5(link: str) -> dict | None:
    parsed = urlparse.urlparse(link)
    if not parsed.hostname or not parsed.port:
        return None
    return {
        "id": _gen_id("socks5", parsed.hostname, parsed.port, parsed.username or ""),
        "name": _decode_name(parsed.fragment),
        "protocol": "socks5",
        "host": parsed.hostname,
        "port": int(parsed.port),
        "username": parsed.username,
        "password": parsed.password,
    }


def _gen_id(proto: str, host: str, port: int, secret: str) -> str:
    h = f"{proto}|{host}|{port}|{secret}".encode("utf-8")
    return uuid.uuid5(uuid.NAMESPACE_URL, h.decode("utf-8")).hex[:12]
