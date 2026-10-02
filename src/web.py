"""Small, safety-conscious public web reader for ForgePilot research context."""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests


class WebFetchError(RuntimeError):
    """A user-safe error raised when a public page cannot be read."""


@dataclass(frozen=True)
class WebPage:
    url: str
    title: str
    text: str
    content_type: str


class _TextExtractor(HTMLParser):
    _SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "template", "iframe", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        if tag in {"p", "div", "section", "article", "li", "br", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag in {"p", "div", "section", "article", "li", "br", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if not self._skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "\n".join(part.strip() for part in "".join(self.parts).splitlines() if part.strip())


def _is_public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return address.is_global


def validate_public_url(value: str) -> str:
    """Validate an HTTP(S) target before the server retrieves it.

    The reader intentionally refuses localhost, private/link-local networks,
    non-standard ports, user-info URLs, and non-web protocols. It is a useful
    SSRF guard, though deployments should still use normal network egress rules.
    """
    candidate = value.strip()
    if not candidate:
        raise WebFetchError("Enter a public http:// or https:// URL.")
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise WebFetchError("Only complete public http:// or https:// URLs can be read.")
    if parsed.username or parsed.password:
        raise WebFetchError("URLs containing account credentials are not allowed.")
    if parsed.port and parsed.port not in {80, 443}:
        raise WebFetchError("Only standard web ports (80 and 443) are allowed.")
    host = parsed.hostname.rstrip(".").lower()
    try:
        try:
            addresses = {host} if _is_public_ip(host) else set()
        except ValueError:
            addresses = {record[4][0] for record in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
        if not addresses or not all(_is_public_ip(address) for address in addresses):
            raise WebFetchError("That URL does not resolve to a public web server.")
    except socket.gaierror as exc:
        raise WebFetchError("The website address could not be resolved.") from exc
    except ValueError as exc:
        raise WebFetchError("The website address is not valid.") from exc
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


def _read_limited(response: requests.Response, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=16_384):
        if not chunk:
            continue
        total += len(chunk)
        if total > limit:
            raise WebFetchError("That page is too large to read safely (limit: 2 MB).")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_public_page(url: str, *, max_characters: int = 18_000) -> WebPage:
    """Fetch readable text from a public page, following at most three safe redirects."""
    current = validate_public_url(url)
    session = requests.Session()
    # Keep the deployment's normal outbound proxy configuration. The requested
    # URL and every redirect are validated before a connection is made.
    headers = {
        "User-Agent": "ForgePilot-WebReader/0.1 (+https://github.com/Ghanimsokaki/mine-agent)",
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
    }
    try:
        for _ in range(4):
            response = session.get(current, headers=headers, timeout=(4, 12), allow_redirects=False, stream=True)
            if response.is_redirect:
                location = response.headers.get("location")
                response.close()
                if not location:
                    raise WebFetchError("The website returned an invalid redirect.")
                current = validate_public_url(urljoin(current, location))
                continue
            if not response.ok:
                response.close()
                raise WebFetchError(f"The website returned HTTP {response.status_code}.")
            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
            if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                response.close()
                raise WebFetchError("This reader supports public HTML and plain-text pages, not this file type.")
            content_length = response.headers.get("content-length")
            try:
                advertised_size = int(content_length) if content_length else 0
            except ValueError:
                advertised_size = 0
            if advertised_size > 2_000_000:
                response.close()
                raise WebFetchError("That page is too large to read safely (limit: 2 MB).")
            raw = _read_limited(response, 2_000_000)
            encoding = response.encoding or "utf-8"
            response.close()
            source = raw.decode(encoding, errors="replace")
            if content_type == "text/plain":
                text = source
                title = urlsplit(current).hostname or "Web page"
            else:
                extractor = _TextExtractor()
                extractor.feed(source)
                text = extractor.text()
                title = " ".join(extractor.title.split()) or urlsplit(current).hostname or "Web page"
            text = "\n".join(line.strip() for line in text.splitlines() if line.strip())[:max_characters]
            if not text:
                raise WebFetchError("The page did not expose readable text. You can use the browser bridge for an approved view of the page instead.")
            return WebPage(current, title[:300], text, content_type)
    except requests.RequestException as exc:
        raise WebFetchError("The public page could not be reached.") from exc
    raise WebFetchError("Too many redirects while reading that page.")
