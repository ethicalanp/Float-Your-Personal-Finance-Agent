import ipaddress
import socket
from urllib.parse import urlparse

import httpx


class FetchError(Exception):
    """Base error for source fetching."""

    pass


class SSRFSecurityViolation(FetchError):
    """Raised when target host resolves to private, loopback, or link-local address."""

    pass


class InsecureSchemeError(FetchError):
    """Raised when URL is not HTTPS."""

    pass


class DomainNotAllowedError(FetchError):
    """Raised when domain is not in the manifest allowlist."""

    pass


class ResponseSizeExceededError(FetchError):
    """Raised when remote response exceeds maximum allowed size."""

    pass


class ContentTypeNotAllowedError(FetchError):
    """Raised when response Content-Type is not supported."""

    pass


class RedirectDomainMismatchError(FetchError):
    """Raised when response redirects to a different domain."""

    pass


ALLOWED_CONTENT_TYPES = {
    "text/html",
    "application/pdf",
    "text/markdown",
    "text/plain",
    "application/xhtml+xml",
}

USER_AGENT = "Float-Personal-Finance-Agent/1.0 (+https://github.com/PersonalFinanceAgent/Float)"
MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB


def validate_url_safety(url: str, domain_allowlist: set[str]) -> str:
    """Validate scheme, domain allowlist, and resolve DNS to ensure IP is not private/loopback."""
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise InsecureSchemeError(f"Only HTTPS URLs are permitted, got: {parsed.scheme} in '{url}'")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise FetchError(f"Invalid URL without hostname: '{url}'")

    if domain_allowlist and hostname not in domain_allowlist:
        raise DomainNotAllowedError(f"Host '{hostname}' is not in the manifest domain allowlist: {domain_allowlist}")

    # DNS Resolution and SSRF validation
    try:
        addr_info = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise FetchError(f"DNS resolution failed for '{hostname}': {e}") from e

    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = sockaddr[0]
        ip_obj = ipaddress.ip_address(ip_str)

        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast or ip_obj.is_reserved:
            raise SSRFSecurityViolation(
                f"SSRF violation: Host '{hostname}' resolved to disallowed IP address: {ip_str}"
            )

    return hostname


async def fetch_url(
    url: str,
    domain_allowlist: set[str],
    client: httpx.AsyncClient | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> tuple[bytes, str]:
    """Safely fetch a remote resource with SSRF checks, domain allowlist, and size capping.

    Returns:
        (content_bytes, content_type)
    """
    initial_host = validate_url_safety(url, domain_allowlist)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/pdf,text/markdown,text/plain;q=0.9,*/*;q=0.5",
    }

    own_client = False
    if client is None:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
            follow_redirects=False,
        )
        own_client = True

    try:
        response = await client.get(url, headers=headers)

        # Handle redirects manually to verify target domain stays within initial domain
        if response.is_redirect:
            redirect_target = response.headers.get("Location")
            if not redirect_target:
                raise FetchError("Redirect response missing 'Location' header")

            redirect_parsed = urlparse(redirect_target)
            redirect_host = (redirect_parsed.hostname or initial_host).lower()

            if redirect_host != initial_host:
                raise RedirectDomainMismatchError(
                    f"Redirect to another domain '{redirect_host}' from '{initial_host}' is blocked"
                )

            # Re-validate target URL
            validate_url_safety(redirect_target, domain_allowlist)
            response = await client.get(redirect_target, headers=headers)

        if response.status_code != 200:
            raise FetchError(f"HTTP request failed with status {response.status_code}: {response.text[:200]}")

        raw_content_type = response.headers.get("Content-Type", "application/octet-stream").lower()
        base_content_type = raw_content_type.split(";")[0].strip()

        if base_content_type not in ALLOWED_CONTENT_TYPES:
            raise ContentTypeNotAllowedError(
                f"Disallowed Content-Type '{base_content_type}'. Allowed: {ALLOWED_CONTENT_TYPES}"
            )

        content = response.content
        if len(content) > max_bytes:
            raise ResponseSizeExceededError(
                f"Response payload {len(content)} bytes exceeds maximum {max_bytes} bytes limit"
            )

        return content, base_content_type
    finally:
        if own_client:
            await client.aclose()
