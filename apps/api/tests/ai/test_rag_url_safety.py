import socket
from unittest.mock import patch

import httpx
import pytest

from app.ai.rag.fetcher import (
    ContentTypeNotAllowedError,
    DomainNotAllowedError,
    InsecureSchemeError,
    RedirectDomainMismatchError,
    ResponseSizeExceededError,
    SSRFSecurityViolation,
    fetch_url,
    validate_url_safety,
)


def test_validate_url_safety_rejects_insecure_scheme() -> None:
    with pytest.raises(InsecureSchemeError, match="Only HTTPS URLs are permitted"):
        validate_url_safety("http://rbi.org.in/notice", domain_allowlist={"rbi.org.in"})


def test_validate_url_safety_rejects_unallowlisted_domain() -> None:
    with pytest.raises(DomainNotAllowedError, match="is not in the manifest domain allowlist"):
        validate_url_safety("https://malicious-site.com/doc", domain_allowlist={"rbi.org.in"})


@pytest.mark.parametrize(
    "disallowed_ip",
    [
        "127.0.0.1",
        "10.0.0.5",
        "192.168.1.100",
        "172.16.0.1",
        "169.254.169.254",  # AWS/Cloud metadata link-local
        "::1",
        "fe80::1",  # IPv6 link-local
    ],
)
def test_validate_url_safety_ssrf_rejects_private_and_loopback_ips(disallowed_ip: str) -> None:
    allowlist = {"trusted-domain.gov.in"}

    def mock_getaddrinfo(host, port, proto=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (disallowed_ip, 443))]

    with patch("socket.getaddrinfo", side_effect=mock_getaddrinfo):
        with pytest.raises(SSRFSecurityViolation, match="disallowed IP address"):
            validate_url_safety("https://trusted-domain.gov.in/doc", domain_allowlist=allowlist)


@pytest.mark.asyncio
async def test_fetch_url_rejects_redirect_to_different_domain() -> None:
    allowlist = {"cybercrime.gov.in", "evil-redirect.com"}

    def handler(request: httpx.Request) -> httpx.Response:
        if "cybercrime.gov.in" in str(request.url):
            return httpx.Response(302, headers={"Location": "https://evil-redirect.com/stolen"})
        return httpx.Response(200, text="Evil payload")

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with pytest.raises(RedirectDomainMismatchError, match="Redirect to another domain"):
            await fetch_url("https://cybercrime.gov.in/advisory", domain_allowlist=allowlist, client=mock_client)


@pytest.mark.asyncio
async def test_fetch_url_enforces_max_size_cap() -> None:
    allowlist = {"rbi.org.in"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"A" * 5000, headers={"Content-Type": "text/markdown"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with pytest.raises(ResponseSizeExceededError, match="exceeds maximum"):
            await fetch_url(
                "https://rbi.org.in/large",
                domain_allowlist=allowlist,
                client=mock_client,
                max_bytes=1000,
            )


@pytest.mark.asyncio
async def test_fetch_url_rejects_unsupported_content_type() -> None:
    allowlist = {"rbi.org.in"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"binary", headers={"Content-Type": "application/x-executable"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with pytest.raises(ContentTypeNotAllowedError, match="Disallowed Content-Type"):
            await fetch_url("https://rbi.org.in/bin", domain_allowlist=allowlist, client=mock_client)
