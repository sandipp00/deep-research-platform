from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass

import httpx

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

_REDIRECT_CODES = {301, 302, 303, 307, 308}
_BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata",
    "metadata.google.internal",
    "instance-data",
}
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain", ".home.arpa")
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=8.0)


class BlockedURLError(Exception):
    pass


class ResponseTooLargeError(Exception):
    pass


@dataclass
class FetchResult:
    url: str
    status_code: int
    headers: httpx.Headers
    content: bytes

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";")[0].strip().lower()

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


def ip_is_public(ip: IPAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return ip_is_public(ip.ipv4_mapped)
        if ip.sixtofour is not None:
            return ip_is_public(ip.sixtofour)
        if ip.teredo is not None:
            return False
        if ip in _NAT64:
            return ip_is_public(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return False
    return ip.is_global


def check_url(url: str) -> httpx.URL:
    try:
        parsed = httpx.URL(url.strip())
    except Exception as e:
        raise BlockedURLError(f"invalid URL ({type(e).__name__})") from None
    if parsed.scheme not in ("http", "https"):
        raise BlockedURLError(f"scheme '{parsed.scheme or 'none'}' is not allowed")
    host = (parsed.host or "").rstrip(".").lower()
    if not host:
        raise BlockedURLError("missing host")
    if parsed.userinfo:
        raise BlockedURLError("credentials in URL are not allowed")
    if host in _BLOCKED_HOSTNAMES or host.endswith(_BLOCKED_SUFFIXES):
        raise BlockedURLError(f"host '{host}' is not allowed")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not ip_is_public(literal):
        raise BlockedURLError(f"address {literal} is not public")
    return parsed


async def _getaddrinfo(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


async def resolve_public(host: str, port: int) -> list[IPAddress]:
    try:
        return [ipaddress.ip_address(host)] if _is_ip_literal(host) else await _resolve(host, port)
    except BlockedURLError:
        raise
    except Exception as e:
        raise BlockedURLError(f"could not resolve host '{host}' ({type(e).__name__})") from None


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


async def _resolve(host: str, port: int) -> list[IPAddress]:
    raw = await asyncio.wait_for(_getaddrinfo(host, port), timeout=5.0)
    ips: list[IPAddress] = []
    for addr in raw:
        ip = ipaddress.ip_address(addr.split("%", 1)[0])
        if ip not in ips:
            ips.append(ip)
    if not ips:
        raise BlockedURLError(f"host '{host}' did not resolve")
    for ip in ips:
        if not ip_is_public(ip):
            raise BlockedURLError(f"host '{host}' resolves to non-public address {ip}")
    return ips


async def validate_url(url: str) -> httpx.URL:
    parsed = check_url(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    await resolve_public(parsed.host.rstrip("."), port)
    return parsed


async def _read_capped(resp: httpx.Response, max_bytes: int) -> bytes:
    declared = resp.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        raise ResponseTooLargeError(f"response is {declared} bytes, limit {max_bytes}")
    buf = bytearray()
    async for chunk in resp.aiter_bytes():
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise ResponseTooLargeError(f"response exceeds {max_bytes} bytes")
    return bytes(buf)


async def safe_get(
    url: str,
    *,
    max_bytes: int,
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | float = _DEFAULT_TIMEOUT,
    max_redirects: int = 5,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FetchResult:
    current = url
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=False, trust_env=False, transport=transport
    ) as client:
        for _ in range(max_redirects + 1):
            parsed = check_url(current)
            host = parsed.host.rstrip(".")
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            ips = await resolve_public(host, port)
            pinned = parsed.copy_with(host=str(ips[0]))
            host_header = parsed.raw_host.decode("ascii")
            if parsed.port:
                host_header = f"{host_header}:{parsed.port}"
            req_headers = {**(headers or {}), "Host": host_header}
            extensions = {"sni_hostname": parsed.raw_host.decode("ascii")} if parsed.scheme == "https" else {}
            request = client.build_request("GET", pinned, headers=req_headers, extensions=extensions)
            resp = await client.send(request, stream=True)
            try:
                if resp.status_code in _REDIRECT_CODES:
                    location = resp.headers.get("location")
                    if not location:
                        raise BlockedURLError("redirect without location")
                    current = str(parsed.join(location))
                    continue
                content = await _read_capped(resp, max_bytes)
                return FetchResult(str(parsed), resp.status_code, resp.headers, content)
            finally:
                await resp.aclose()
    raise BlockedURLError("too many redirects")
