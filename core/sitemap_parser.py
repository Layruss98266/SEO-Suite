"""
SitemapParser — fetch and parse XML sitemaps, domain auto-discovery, crawling.
Extracted from core/checker.py for single-responsibility.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


class SitemapParser:
    """Fetch and parse XML sitemaps (including sitemap indexes).

    Usage::

        parser = SitemapParser(timeout_secs=15)
        urls = parser.fetch("https://example.com/sitemap.xml")
    """

    def __init__(self, timeout_secs: int = 15) -> None:
        self.timeout_secs = timeout_secs

    # ── Public ────────────────────────────────────────────────────────────────

    def fetch(self, sitemap_url: str, _depth: int = 0, _seen: set | None = None) -> list[str]:
        """Return all page URLs from a sitemap (or sitemap index).

        Uses safe_requests_get so a sitemap-index referencing an internal host
        cannot be used to pivot fetches into private space. Cycle protection
        (`_depth`, `_seen`) prevents infinite recursion on self-referencing
        sitemap indexes.
        """
        from core.security import safe_requests_get, validate_public_url
        if _depth > 5:
            logger.warning("Sitemap recursion depth exceeded at %s — stopping", sitemap_url)
            return []
        if _seen is None:
            _seen = set()
        if sitemap_url in _seen:
            return []
        _seen.add(sitemap_url)
        try:
            sitemap_url = validate_public_url(sitemap_url)
        except ValueError as e:
            logger.error("Refusing non-public sitemap URL %s: %s", sitemap_url, e)
            return []
        logger.info("Fetching sitemap: %s", sitemap_url)
        try:
            r = safe_requests_get(
                sitemap_url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=self.timeout_secs,
            )
            content = r.content
        except Exception as e:
            logger.error("Failed to fetch sitemap %s: %s", sitemap_url, e)
            return []
        urls = self._parse(content, sitemap_url, _depth, _seen)
        # Filter the leaf URLs too so smuggled internal hosts never reach the
        # downstream audit/index pipeline.
        from core.security import filter_public_urls
        return filter_public_urls(urls)

    def from_domain(self, domain: str) -> list[str]:
        """Auto-detect sitemap from a bare domain URL."""
        domain = domain.strip().rstrip("/")
        if not domain.startswith("http"):
            domain = "https://" + domain
        for path in ["/sitemap.xml", "/sitemap_index.xml", "/sitemap/"]:
            urls = self.fetch(domain + path)
            if urls:
                return urls
        logger.warning("No sitemap found for %s — using homepage only", domain)
        return [domain]

    def crawl(self, start_url: str, max_pages: int = 50, max_depth: int = 2) -> list[str]:
        """BFS crawl from start_url, following internal <a href> links."""
        try:
            import requests as _r
            from bs4 import BeautifulSoup as _BS
            from urllib.parse import urljoin as _uj
        except ImportError as e:
            logger.error("crawl requires requests + beautifulsoup4: %s", e)
            return []

        start_url = start_url.strip()
        if not start_url.startswith("http"):
            start_url = "https://" + start_url
        base_host = urlparse(start_url).netloc

        seen: set[str] = set()
        found: list[str] = []
        q: deque[tuple[str, int]] = deque([(start_url, 0)])
        headers = {"User-Agent": "Mozilla/5.0 (compatible; SEOCrawler/1.0)"}

        while q and len(found) < max_pages:
            url, depth = q.popleft()
            if url in seen:
                continue
            seen.add(url)
            try:
                r = _r.get(url, headers=headers, timeout=8, allow_redirects=True)
                if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
                    continue
            except Exception:
                continue
            found.append(url)
            if depth >= max_depth:
                continue
            try:
                soup = _BS(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = _uj(url, a["href"]).split("#")[0].rstrip("/")
                    if not href.startswith("http"):
                        continue
                    if urlparse(href).netloc != base_host:
                        continue
                    if href not in seen and len(found) + len(q) < max_pages * 3:
                        q.append((href, depth + 1))
            except Exception:
                continue
        return found

    # ── Private ───────────────────────────────────────────────────────────────

    def _parse(self, content: bytes, source_url: str, depth: int = 0,
               seen: set | None = None) -> list[str]:
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            return self._fallback_parse(content, depth, seen, self)

        # Sitemap index → recurse
        children = root.findall("sm:sitemap/sm:loc", ns)
        if children:
            urls: list[str] = []
            for node in children:
                if node.text:
                    urls.extend(self.fetch(node.text.strip(), depth + 1, seen))
            return urls
        return [loc.text.strip() for loc in root.findall("sm:url/sm:loc", ns) if loc.text]

    @staticmethod
    def _fallback_parse(content: bytes, depth: int = 0, seen: set | None = None,
                         parser_inst: "SitemapParser | None" = None) -> list[str]:
        try:
            from lxml import etree as _lxml
            parser = _lxml.XMLParser(recover=True)
            root = _lxml.fromstring(content, parser)
            ns_uri = "http://www.sitemaps.org/schemas/sitemap/0.9"
            children = root.findall(f"{{{ns_uri}}}sitemap/{{{ns_uri}}}loc")
            if children:
                # Previously returned [] here, dropping every nested sitemap on a
                # malformed sitemap-index. Recurse instead so fallback gives the
                # same coverage as the strict parser.
                if parser_inst is None:
                    return []
                urls: list[str] = []
                for node in children:
                    if node.text:
                        urls.extend(parser_inst.fetch(node.text.strip(), depth + 1, seen))
                return urls
            return [loc.text.strip() for loc in root.findall(f".//{{{ns_uri}}}loc") if loc.text]
        except Exception:
            return re.findall(r"<loc>\s*(https?://[^\s<]+)\s*</loc>",
                              content.decode("utf-8", errors="replace"))
