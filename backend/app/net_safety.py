"""Destination checks for operator-supplied URLs (QA/Security review, ADR 0019).

The LLM base URL receives full transcripts, so it must not point at addresses that are never a
legitimate model server: cloud metadata and link-local ranges, unspecified, multicast and
reserved addresses, and the names of AdVera's own internal services. Private LAN and loopback
addresses stay allowed because Ollama commonly runs on the LAN. Redirects are never followed.
The check runs when settings are written or models discovered, not on every settings read.
Hostnames are resolved here; DNS that changes afterwards is not re-checked.
"""

import asyncio
import ipaddress
import socket
import urllib.parse

INTERNAL_SERVICE_NAMES = {"postgres", "redis", "api", "frontend", "migrate"}
METADATA_NAMES = {"metadata", "metadata.google.internal", "instance-data"}


class UnsafeDestination(ValueError):
    """Raised with a stable code; never includes the URL."""


def _check_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    if (
        address.is_link_local
        or address.is_unspecified
        or address.is_multicast
        or address.is_reserved
    ):
        raise UnsafeDestination("UNSAFE_DESTINATION")


def _resolve(host: str) -> list[str]:
    try:
        return [item[4][0] for item in socket.getaddrinfo(host, None)]
    except OSError:
        return []  # unresolved names cannot be an internal address; discovery reports them


async def assert_safe_destination(url: str) -> None:
    host = (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
    if not host or host in INTERNAL_SERVICE_NAMES or host in METADATA_NAMES:
        raise UnsafeDestination("UNSAFE_DESTINATION")
    try:
        literals = [ipaddress.ip_address(host)]
    except ValueError:
        literals = [
            ipaddress.ip_address(item.split("%")[0])
            for item in await asyncio.to_thread(_resolve, host)
        ]
    for address in literals:
        _check_address(address)
