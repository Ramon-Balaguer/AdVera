"""Destination checks for operator-supplied URLs (QA/Security review).

The LLM base URL receives full transcripts, so it must not point at addresses that are never a
legitimate model server: cloud metadata and link-local ranges, unspecified, multicast and
reserved addresses, and the names of AdVera's own internal services. Private LAN and loopback
addresses (IPv4 and IPv6) stay allowed because Ollama commonly runs there. Redirects are never
followed. The check runs when settings are written or models discovered, not on every read.

Legacy IPv4 spellings that resolvers accept (`2852039166`, `0xa9fea9fe`, `169.254.43518`,
octal parts) are parsed here explicitly instead of relying on the platform resolver, which
handles them differently on Windows and Linux. A name that does not resolve is refused: it
cannot be checked, and a name that later resolves to a forbidden address is the same hole.
Hostnames are resolved once, here; DNS that changes afterwards is not re-checked.
"""

import asyncio
import ipaddress
import socket
import urllib.parse

INTERNAL_SERVICE_NAMES = {"postgres", "redis", "api", "frontend", "migrate"}
METADATA_NAMES = {"metadata", "metadata.google.internal", "instance-data"}

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class UnsafeDestination(ValueError):
    """Raised with a stable code; never includes the URL."""

    def __init__(self, code: str = "UNSAFE_DESTINATION") -> None:
        super().__init__(code)
        self.code = code


def _check_address(address: IPAddress) -> None:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    if address.is_loopback:
        return  # a model server on this machine is legitimate (and ::1 is "reserved" in IPv6)
    if (
        address.is_link_local
        or address.is_unspecified
        or address.is_multicast
        or address.is_reserved
    ):
        raise UnsafeDestination


def legacy_ipv4(host: str) -> ipaddress.IPv4Address | None:
    """Parse inet_aton-style IPv4 (1 to 4 parts; hex, octal or decimal), or None."""
    parts = host.split(".")
    if not 1 <= len(parts) <= 4 or any(not part for part in parts):
        return None
    numbers: list[int] = []
    for part in parts:
        try:
            if part[:2].lower() == "0x":
                numbers.append(int(part[2:], 16))
            elif len(part) > 1 and part[0] == "0":
                numbers.append(int(part, 8))
            else:
                numbers.append(int(part, 10))
        except ValueError:
            return None
    *leading, last = numbers
    if any(number > 255 for number in leading) or last >= 256 ** (5 - len(numbers)):
        return None
    value = last
    for index, number in enumerate(leading):
        value += number << (8 * (3 - index))
    return ipaddress.IPv4Address(value)


def _resolve(host: str) -> list[str]:
    try:
        return [item[4][0] for item in socket.getaddrinfo(host, None)]
    except OSError:
        return []


async def assert_safe_destination(url: str) -> None:
    host = (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
    if not host or host in INTERNAL_SERVICE_NAMES or host in METADATA_NAMES:
        raise UnsafeDestination
    literal: IPAddress | None
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = legacy_ipv4(host)
    if literal is not None:
        _check_address(literal)
        return
    resolved = await asyncio.to_thread(_resolve, host)
    if not resolved:
        raise UnsafeDestination("UNRESOLVABLE_HOST")
    for item in resolved:
        _check_address(ipaddress.ip_address(item.split("%")[0]))
