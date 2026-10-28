"""Who is calling? The address of whoever opened the connection — unless that
is one of our own reverse proxies (TRUSTED_PROXIES), in which case the real
caller is what the proxy wrote in X-Forwarded-For.

X-Forwarded-For is only believed from a trusted proxy: anyone can send the
header themselves, and honouring it from an arbitrary client would let them
pick the address the rate limiter and the audit trail record."""
import ipaddress

from fastapi import Request

from app.core.config import get_settings


def _parse(value: str | None):
    try:
        return ipaddress.ip_address((value or "").strip())
    except ValueError:
        return None


def _is_trusted(address, trusted: list) -> bool:
    return address is not None and any(address in network for network in trusted)


def resolve_client_ip(peer: str | None, forwarded_for: str | None, trusted: list) -> str:
    """`peer` is the connection's address, `forwarded_for` the raw header.
    Walks the header from the right (the hop closest to us), skipping our own
    proxies; the first address that is not one of them is the client. A
    header that doesn't parse, or has no outside address, is not believed."""
    if not peer:
        return "unknown"
    if not trusted or not _is_trusted(_parse(peer), trusted):
        return peer
    for hop in reversed((forwarded_for or "").split(",")):
        address = _parse(hop)
        if address is None:
            return peer
        if not _is_trusted(address, trusted):
            return str(address)
    return peer


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else None
    return resolve_client_ip(peer, request.headers.get("x-forwarded-for"), get_settings().trusted_proxy_networks)


def rate_limit_identity(ip: str) -> str:
    """What the limiter counts as one caller. An IPv6 user normally controls a
    whole /64, so counting single addresses would let them dodge the limit by
    changing the low bits; count the /64 instead."""
    address = _parse(ip)
    if isinstance(address, ipaddress.IPv6Address):
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return ip
