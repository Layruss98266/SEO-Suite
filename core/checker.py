"""
Google Indexing Status Checker
Features: Parallel tabs · GSC API · Proxy rotation · Email/Slack/Teams
          Resume · Retry · Excel · HTML · Compare · Filter · Schedule
          Crawl depth · Priority score · Trend chart · Multiple inputs
"""

import csv
import json
import logging
import os
import random
import re
import sys
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Re-export focused classes so callers can import from core.checker or core.<module>
from core.notifier import NotificationService  # noqa: E402
from core.report_generator import ReportGenerator  # noqa: E402
from core.security import esc as _esc  # noqa: E402
from core.security import filter_public_urls as _filter_urls
from core.security import validate_public_url as _validate_url

# ── Colors ────────────────────────────────────────────────────────────────────
try:
    from colorama import Fore, Style, init
    init(autoreset=True)
    GREEN = Fore.GREEN; RED = Fore.RED; YELLOW = Fore.YELLOW
    CYAN = Fore.CYAN;   BOLD = Style.BRIGHT; RESET = Style.RESET_ALL
except ImportError:
    GREEN = RED = YELLOW = CYAN = BOLD = RESET = ""

# ── Optional deps ─────────────────────────────────────────────────────────────
try:
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_IMPORT_ERROR = None
except ImportError as _e:
    # Defer the hard failure until indexing actually runs. This lets the module
    # import in audit-only environments and CI (where Playwright might not be
    # installed) without bringing down every other route in app/server.py.
    sync_playwright = None
    PWTimeout = Exception  # type: ignore[misc,assignment]
    _PLAYWRIGHT_IMPORT_ERROR = _e


def _require_playwright() -> None:
    """Raise a runtime error only when browser-based indexing is actually used."""
    if sync_playwright is None:
        raise RuntimeError(
            "Playwright is required for indexing checks. "
            "Run: pip install playwright && playwright install chromium"
        ) from _PLAYWRIGHT_IMPORT_ERROR

try:
    from tqdm import tqdm; HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

try:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    HAS_XLSX = True
except ImportError:
    HAS_XLSX = False

try:
    import schedule as sched; HAS_SCHEDULE = True
except ImportError:
    HAS_SCHEDULE = False

try:
    from playwright_stealth import stealth_sync; HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False
    def stealth_sync(page): pass  # no-op fallback

try:
    import requests as req_lib; HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# ── Dirs ──────────────────────────────────────────────────────────────────────
# Anchor all runtime paths to the project root so the app behaves consistently
# regardless of the working directory from which it is launched. Previously
# Path("data") resolved relative to cwd, which could split config, reports,
# uploads, and profiles across different trees when launched outside repo root.
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DATA_DIR     = _PROJECT_ROOT / "data";           DATA_DIR.mkdir(exist_ok=True)
PROGRESS_DIR = DATA_DIR / "progress";            PROGRESS_DIR.mkdir(exist_ok=True)
REPORTS_DIR  = DATA_DIR / "reports";             REPORTS_DIR.mkdir(exist_ok=True)
HISTORY_FILE = DATA_DIR / "history.json"

# ── Config ────────────────────────────────────────────────────────────────────
def load_config() -> dict:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    cfg_file = _PROJECT_ROOT / "config.json"
    cfg = json.loads(cfg_file.read_text()) if cfg_file.exists() else {}

    # Overlay secrets from environment variables so they never live in config.json
    import os
    _env_keys = {
        "pagespeed_api_key": "PAGESPEED_API_KEY",
        "serpapi_key":        "SERPAPI_KEY",
        "moz_access_id":      "MOZ_ACCESS_ID",
        "moz_secret_key":     "MOZ_SECRET_KEY",
        "dataforseo_login":   "DATAFORSEO_LOGIN",
        "dataforseo_password":"DATAFORSEO_PASSWORD",
    }
    for cfg_key, env_key in _env_keys.items():
        val = os.getenv(env_key, "")
        if val:
            cfg[cfg_key] = val

    return cfg

CFG = load_config()

def _t(key: str, default: Any) -> Any:
    """Read a value from CFG['timings'], falling back to default."""
    return CFG.get("timings", {}).get(key, default)

# ── Beep ──────────────────────────────────────────────────────────────────────
def beep() -> None:
    try:
        import winsound
        for _ in range(3): winsound.Beep(1000, 400); time.sleep(0.2)
    except Exception:
        print("\a\a\a")


# ══════════════════════════════════════════════════════════════════════════════
# INPUT — Sitemap / CSV / Domain
# ══════════════════════════════════════════════════════════════════════════════

def fetch_sitemap_urls(sitemap_url: str, _depth: int = 0, _seen: set | None = None) -> list[str]:
    # Defend against sitemap-index loops (an index pointing to itself or to a
    # cycle) by capping recursion depth and tracking visited URLs.
    if _depth > 5:
        logger.warning("Sitemap recursion depth exceeded at %s — stopping", sitemap_url)
        return []
    if _seen is None:
        _seen = set()
    if sitemap_url in _seen:
        return []
    try:
        sitemap_url = _validate_url(sitemap_url)
    except Exception as e:
        logger.error("SSRF guard blocked sitemap URL %s: %s", sitemap_url, e)
        return []
    _seen.add(sitemap_url)
    parsed = urlparse(sitemap_url)
    if parsed.scheme not in ("http", "https"):
        logger.error("Invalid sitemap URL (must start with http/https): %s", sitemap_url)
        return []
    logger.info("Fetching sitemap: %s", sitemap_url)
    # Use safe_requests_get so every redirect hop is re-validated against the
    # SSRF allowlist. The previous urllib.request.urlopen call followed redirects
    # with no validation, letting a public sitemap URL bounce the server into
    # private or metadata addresses.
    from core.security import safe_requests_get as _safe_get
    try:
        r = _safe_get(
            sitemap_url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=_t("sitemap_fetch_timeout_secs", 15),
        )
        content = r.content
    except Exception as e:
        logger.error("Failed to fetch sitemap %s: %s", sitemap_url, e)
        return []

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = None
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        try:
            from lxml import etree as _lxml_et
            _parser = _lxml_et.XMLParser(recover=True)
            root = _lxml_et.fromstring(content, _parser)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            children_lxml = root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap/{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
            if children_lxml:
                urls: list[str] = []
                for node in children_lxml:
                    if node.text:
                        urls.extend(fetch_sitemap_urls(node.text.strip(), _depth + 1, _seen))
                return urls
            return [loc.text.strip() for loc in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc") if loc.text]
        except Exception:
            import re as _re
            return _re.findall(r"<loc>\s*(https?://[^\s<]+)\s*</loc>", content.decode("utf-8", errors="replace"))

    children = root.findall("sm:sitemap/sm:loc", ns)
    if children:
        urls: list[str] = []
        for node in children:
            urls.extend(fetch_sitemap_urls(node.text.strip(), _depth + 1, _seen))
        return urls
    return [loc.text.strip() for loc in root.findall("sm:url/sm:loc", ns)]

def fetch_from_domain(domain: str) -> list[str]:
    domain = domain.strip().rstrip("/")
    if not domain.startswith("http"):
        domain = "https://" + domain
    try:
        domain = _validate_url(domain)
    except ValueError as e:
        logger.error("Refusing to scan non-public domain %s: %s", domain, e)
        return []
    for path in ["/sitemap.xml", "/sitemap_index.xml", "/sitemap/"]:
        urls = fetch_sitemap_urls(domain + path)
        if urls:
            return urls
    logger.warning("No sitemap found for %s — using homepage only", domain)
    return [domain]

def crawl_site(start_url: str, max_pages: int = 50, max_depth: int = 2) -> list[str]:
    """BFS crawl from start_url, following internal <a href> links up to max_depth."""
    from collections import deque
    from urllib.parse import urljoin as _uj
    from urllib.parse import urlparse as _up

    from bs4 import BeautifulSoup as _BS

    # Use safe_requests_get so every redirect hop is re-validated against the
    # SSRF allowlist. The previous raw `requests.get` followed redirects with
    # no validation, letting a public URL bounce the server into private space.
    from core.security import safe_requests_get as _safe_get

    start_url = start_url.strip()
    if not start_url.startswith("http"):
        start_url = "https://" + start_url
    try:
        start_url = _validate_url(start_url)
    except ValueError as e:
        logger.error("Refusing to crawl non-public URL %s: %s", start_url, e)
        return []
    base_host = _up(start_url).netloc

    seen, found = set(), []
    q = deque([(start_url, 0)])
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SEOCrawler/1.0)"}
    while q and len(found) < max_pages:
        url, depth = q.popleft()
        if url in seen: continue
        seen.add(url)
        try:
            r = _safe_get(url, headers=headers, timeout=_t("crawl_request_timeout_secs", 8))
            if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
                continue
        except Exception:
            continue
        found.append(url)
        if depth >= max_depth: continue
        try:
            soup = _BS(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = _uj(url, a["href"]).split("#")[0].rstrip("/")
                if not href.startswith("http"): continue
                if _up(href).netloc != base_host: continue
                # Validate the link too — a crafted host header on the base
                # page could otherwise pivot crawls into private space.
                try:
                    href = _validate_url(href)
                except ValueError:
                    continue
                if href not in seen and len(found) + len(q) < max_pages * 3:
                    q.append((href, depth + 1))
        except Exception:
            continue
    return found

def load_from_csv_excel(file_path: str) -> list[str]:
    def _looks_like_header(row: list[str]) -> bool:
        normalized = [cell.strip().lower() for cell in row if cell and cell.strip()]
        if not normalized:
            return False
        return any(cell in {"url", "urls", "link", "links"} for cell in normalized)

    def _find_url_col(row: list[str]) -> int | None:
        for idx, cell in enumerate(row):
            if cell.strip().lower() in {"url", "urls", "link", "links"}:
                return idx
        return None

    def _extract_cells(rows: list[list[str]]) -> list[str]:
        if not rows:
            return []
        header = rows[0]
        url_col = _find_url_col(header) if _looks_like_header(header) else None
        if url_col is not None:
            return [
                row[url_col].strip()
                for row in rows[1:]
                if len(row) > url_col and row[url_col] and row[url_col].strip().startswith("http")
            ]
        urls = [
            cell.strip()
            for row in rows
            for cell in row
            if cell and cell.strip().startswith("http")
        ]
        if not urls and any(cell.strip() for cell in header):
            cols = ", ".join(cell.strip() for cell in header if cell and cell.strip()) or "<empty>"
            raise ValueError(
                f"File must contain a URL column or at least one http(s) URL. Found columns: {cols}"
            )
        return urls

    path = Path(file_path)
    if not path.exists():
        logger.error("File not found: %s", file_path)
        return []
    urls: list[str] = []
    if path.suffix.lower() in (".xlsx", ".xls"):
        if not HAS_XLSX:
            logger.error("openpyxl not installed — cannot read Excel file")
            return []
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        rows = [
            [str(cell).strip() if cell is not None else "" for cell in row]
            for row in ws.iter_rows(values_only=True)
        ]
        urls = _extract_cells(rows)
    else:
        sample = path.read_text(encoding="utf-8", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(sample[:2048], delimiters=",\t;|")
        except csv.Error:
            dialect = csv.excel
        with open(path, encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f, dialect)
            rows = [[cell.strip() for cell in row] for row in reader]
        urls = _extract_cells(rows)
    # Filter every URL through the SSRF allowlist — a malicious CSV could
    # otherwise smuggle internal hosts past the upload form.
    safe_urls = _filter_urls(urls)
    if len(safe_urls) != len(urls):
        logger.warning("Dropped %d non-public URLs from %s",
                       len(urls) - len(safe_urls), file_path)
    return safe_urls

def get_urls_from_user() -> list[str]:
    print(f"\n{BOLD}How do you want to provide URLs?{RESET}")
    print("  1. Sitemap URL")
    print("  2. Multiple sitemap URLs (comma-separated)")
    print("  3. Domain only (auto-detect sitemap)")
    print("  4. CSV / Excel file")
    choice = input("\nChoice (1-4): ").strip()

    if choice == "1":
        url = input("Sitemap URL: ").strip()
        if not url:
            print(f"{RED}No URL entered.{RESET}"); return []
        return fetch_sitemap_urls(url)

    elif choice == "2":
        raw   = input("Sitemap URLs (comma-separated): ").strip()
        urls: list[str] = []
        for u in raw.split(","):
            urls.extend(fetch_sitemap_urls(u.strip()))
        return urls

    elif choice == "3":
        domain = input("Domain (e.g. edstellar.com): ").strip()
        return fetch_from_domain(domain)

    elif choice == "4":
        path = input("File path (CSV or Excel): ").strip()
        return load_from_csv_excel(path)

    else:
        print(f"{RED}Invalid choice.{RESET}"); return []


# ══════════════════════════════════════════════════════════════════════════════
# URL HELPERS — filter, depth, priority, type
# ══════════════════════════════════════════════════════════════════════════════

def filter_urls(urls: list[str], pattern: str) -> list[str]:
    return [u for u in urls if pattern.lower() in u.lower()] if pattern else urls

def get_crawl_depth(url: str) -> int:
    return len([p for p in urlparse(url).path.strip("/").split("/") if p])

def get_url_type(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path: return "Homepage"
    seg = path.split("/")[0]
    return seg.replace("-", " ").title() if seg else "Other"

def get_priority_score(url: str) -> str:
    high = CFG.get("priority", {}).get("high_value_patterns", ["/category/", "/course/"])
    low  = CFG.get("priority", {}).get("low_value_patterns",  ["/tag/", "/author/"])
    depth = get_crawl_depth(url)
    if any(p in url for p in high):        return "High"
    if any(p in url for p in low):         return "Low"
    if depth <= 1:                         return "High"
    if depth <= 3:                         return "Medium"
    return "Low"


# ══════════════════════════════════════════════════════════════════════════════
# PROGRESS / RESUME
# ══════════════════════════════════════════════════════════════════════════════

def progress_file_for(key: str) -> Path:
    # Use a stable hash of the full key so different URL orderings between
    # runs still resolve to the same progress file (callers join multiple URLs
    # together — without sorting/hashing, ['a','b'] and ['b','a'] would split).
    import hashlib
    digest = hashlib.sha1(key.encode("utf-8", errors="replace")).hexdigest()[:16]
    return PROGRESS_DIR / f"progress_{digest}.json"

def load_progress(pf: Path) -> dict:
    return json.loads(pf.read_text()) if pf.exists() else {}

def save_progress(pf: Path, data: dict):
    # Atomic write — concurrent retry + main run threads otherwise race on the
    # same file and can truncate it mid-write, losing progress.
    tmp = pf.with_suffix(pf.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, pf)


# ══════════════════════════════════════════════════════════════════════════════
# COMPARE RUNS
# ══════════════════════════════════════════════════════════════════════════════

def find_latest_report() -> Path | None:
    reports = sorted(REPORTS_DIR.glob("indexing_report_*.csv"), reverse=True)
    return reports[0] if reports else None

def compare_runs(current: dict[str, str], prev_file: Path) -> dict:
    prev: dict[str, str] = {}
    with open(prev_file, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            prev[row["URL"]] = row["Google Indexed"]
    ni, nd = [], []
    for url, status in current.items():
        old = prev.get(url)
        if not old: continue
        if old != "Indexed" and status == "Indexed":   ni.append(url)
        elif old == "Indexed" and status != "Indexed": nd.append(url)
    return {"newly_indexed": ni, "newly_deindexed": nd}


# ══════════════════════════════════════════════════════════════════════════════
# HISTORY / TREND
# ══════════════════════════════════════════════════════════════════════════════

def load_history() -> list[dict]:
    return json.loads(HISTORY_FILE.read_text()) if HISTORY_FILE.exists() else []

def save_history(counts: dict, total: int, timestamp: str):
    history = load_history()
    history.append({
        "date":        timestamp,
        "total":       total,
        "indexed":     counts.get("Indexed", 0),
        "not_indexed": counts.get("Not Indexed", 0),
    })
    HISTORY_FILE.write_text(json.dumps(history[-30:], indent=2))  # keep last 30 runs


# ══════════════════════════════════════════════════════════════════════════════
# GSC API CHECK
# ══════════════════════════════════════════════════════════════════════════════

def gsc_check_url(url: str, service, site_url: str = None) -> str:
    try:
        if not site_url:
            parsed = urlparse(url)
            site_url = f"{parsed.scheme}://{parsed.netloc}/"
        resp = service.urlInspectionResult().inspect(
            body={"inspectionUrl": url, "siteUrl": site_url}
        ).execute()
        verdict = resp.get("urlInspectionResult", {}).get("indexStatusResult", {}).get("verdict", "")
        return "Indexed" if verdict == "PASS" else "Not Indexed"
    except Exception as e:
        return f"GSC Error: {e}"

def build_gsc_service() -> Any | None:
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds_file = CFG.get("gsc", {}).get("credentials_file", "gsc_credentials.json")
        creds = service_account.Credentials.from_service_account_file(
            creds_file,
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
        )
        return build("searchconsole", "v1", credentials=creds)
    except Exception as e:
        logger.error("GSC setup failed: %s", e)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# BROWSER CHECK (Playwright)
# ══════════════════════════════════════════════════════════════════════════════

_print_lock = threading.Lock()


def _normalize_url(url: str) -> str:
    """Lowercase, strip scheme, strip www, strip trailing slash and fragment."""
    url = url.lower().split("#")[0].split("?")[0].rstrip("/")
    url = re.sub(r'^https?://', '', url)
    if url.startswith("www."):
        url = url[4:]
    return url


def is_page_alive(page) -> bool:
    """Return True if the Playwright page/browser is still usable."""
    try:
        page.title()
        return True
    except Exception:
        return False


def google_check(page, url: str, delay_state: dict) -> str:
    clean      = url.replace("https://", "").replace("http://", "").rstrip("/")
    # filter=0 disables Google's duplicate-result filtering; num=10 gives more to match against
    search_url = f"https://www.google.com/search?q=site:{clean}&hl=en&num=10&filter=0"
    try:
        if not is_page_alive(page):
            return "Error: Browser context closed"

        _page_timeout = _t("browser_page_timeout_ms", 20000)
        t0 = time.time()
        page.goto(search_url, wait_until="domcontentloaded", timeout=_page_timeout)
        elapsed = time.time() - t0

        # Adaptive delay
        _delay_max = _t("delay_max_secs", 15.0)
        _delay_min = _t("delay_base_secs", 3.0)
        base = delay_state["base"]
        delay_state["base"] = min(base + 1, _delay_max) if elapsed > 5 else max(base - 0.5, _delay_min) if elapsed < 2 else base
        time.sleep(random.uniform(delay_state["base"], delay_state["base"] + 3))

        html = page.content()

        if "detected unusual traffic" in html.lower() or "captcha" in html.lower():
            beep()
            with _print_lock:
                print(f"\n{YELLOW}⚠  CAPTCHA — solve it in the browser window{RESET}\n")
            delay_state["base"] = min(delay_state["base"] + 3, _delay_max)
            time.sleep(_t("captcha_wait_secs", 60))
            page.goto(search_url, wait_until="domcontentloaded", timeout=_page_timeout)
            time.sleep(4)
            html = page.content()

        delay_state["count"] = delay_state.get("count", 0) + 1
        _break_every = _t("rate_limit_break_every_n", 10)
        if delay_state["count"] % _break_every == 0:
            wait = random.uniform(
                _t("rate_limit_break_min_secs", 15),
                _t("rate_limit_break_max_secs", 25),
            )
            with _print_lock:
                print(f"\n  {CYAN}Break {wait:.0f}s to avoid rate limiting…{RESET}\n")
            time.sleep(wait)

        html_lower = html.lower()
        no_results_patterns = [
            "did not match any documents",
            "no results found",
            "your search did not match",
            "did not match any web pages",
            "no webpages were found",
        ]
        if any(t in html_lower for t in no_results_patterns):
            return "Not Indexed"

        target_norm   = _normalize_url(url)
        target_domain = _normalize_url(url).split("/")[0]  # e.g. "example.com"
        target_path   = "/" + "/".join(_normalize_url(url).split("/")[1:]) if "/" in _normalize_url(url) else "/"

        # Collect result URLs — multiple selectors cover old and new Google SERP layouts
        result_urls: list[str] = []
        for selector in (
            "div.g a[href]",
            "#rso a[href]",
            ".yuRUbf a[href]",
            "div[data-sokoban-container] a[href]",
            "div[jscontroller] h3 ~ a[href]",
        ):
            try:
                for el in page.locator(selector).all()[:15]:
                    href = el.get_attribute("href") or ""
                    if href.startswith("http"):
                        result_urls.append(href.split("?")[0].split("#")[0].rstrip("/").lower())
            except Exception:
                pass

        # Fallback regex — restrict to target domain to avoid capturing nav/ad links
        if not result_urls:
            result_urls = [
                u.rstrip("/").lower()
                for u in re.findall(r'href="(https?://[^"?#]+)"', html)
                if target_domain in u.lower()
            ]

        # 1) Exact match (www/scheme-normalized)
        for r in result_urls:
            if _normalize_url(r) == target_norm:
                return "Indexed"

        # 2) Path match — covers www↔non-www and http↔https variants
        for r in result_urls:
            r_norm = _normalize_url(r)
            r_domain = r_norm.split("/")[0]
            r_path   = "/" + "/".join(r_norm.split("/")[1:]) if "/" in r_norm else "/"
            # Same domain (ignoring www) and same path
            if r_domain == target_domain and r_path == target_path:
                return "Indexed"

        # 3) result-stats count > 0 means something from this site is indexed at this path
        try:
            stats_el = page.locator("#result-stats").first
            if stats_el.count() > 0:
                nums = re.findall(r'\d+', (stats_el.text_content() or "").replace(",", ""))
                if nums and int(nums[0]) > 0:
                    return "Indexed"
        except Exception:
            pass

        return "Not Indexed"

    except PWTimeout: return "Timeout"
    except Exception as e: return f"Error: {e}"


def check_parallel(urls: list[str], n: int, proxy_list: list, headless: bool, delay_state: dict, callback) -> dict[str, str]:
    """Check URLs using n parallel browser tabs."""
    _require_playwright()
    results: dict[str, str] = {}
    batches = [urls[i::n] for i in range(n)]

    def worker(batch: list[str], proxy: dict | None):
        with sync_playwright() as p:
            launch_args = {
                "headless": headless,
                "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            }
            if proxy:
                launch_args["proxy"] = proxy

            browser = p.chromium.launch(**launch_args)
            ctx = browser.new_context(
                user_agent=CHROME_UA,
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            page = ctx.new_page()
            stealth_sync(page)
            page.goto("https://www.google.com", wait_until="domcontentloaded")
            time.sleep(2)
            try:
                btn = page.locator("button:has-text('Accept all'), button:has-text('I agree')")
                if btn.count() > 0:
                    btn.first.click(); time.sleep(1)
            except Exception:
                pass

            local_delay = dict(delay_state)
            for url in batch:
                # Re-launch context if browser crashed mid-batch (check before each URL)
                if not is_page_alive(page):
                    try:
                        ctx2  = browser.new_context(
                            user_agent=CHROME_UA,
                            viewport={"width": 1280, "height": 800}, locale="en-US"
                        )
                        page = ctx2.new_page()
                        stealth_sync(page)
                        page.goto("https://www.google.com", wait_until="domcontentloaded")
                        time.sleep(2)
                    except Exception as e:
                        results[url] = f"Error: Browser restart failed — {e}"
                        callback(url, results[url])
                        continue
                try:
                    status = google_check(page, url, local_delay)
                except Exception as e:
                    status = f"Error: {e}"
                    # Force alive-check on next iteration by invalidating page
                    try:
                        page.close()
                    except Exception:
                        pass
                    if not is_page_alive(page):
                        page = ctx.new_page()
                        stealth_sync(page)
                results[url] = status
                callback(url, status)

            try:
                browser.close()
            except Exception:
                pass

    threads = []
    for i, batch in enumerate(batches):
        if not batch: continue
        proxy = {"server": proxy_list[i % len(proxy_list)]} if proxy_list else None
        t = threading.Thread(target=worker, args=(batch, proxy))
        t.start(); threads.append(t)

    for t in threads:
        t.join()

    return results


# ══════════════════════════════════════════════════════════════════════════════
# REPORTS — Excel + HTML
# ══════════════════════════════════════════════════════════════════════════════

def generate_excel(rows: list[dict], path: Path, type_summary: dict):
    if not HAS_XLSX:
        print(f"  {YELLOW}openpyxl not installed — skipping Excel{RESET}"); return
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "Results"
    HDR  = PatternFill("solid", fgColor="1F4E79")
    GF   = PatternFill("solid", fgColor="C6EFCE")
    RF   = PatternFill("solid", fgColor="FFC7CE")
    YF   = PatternFill("solid", fgColor="FFEB9C")

    headers = ["#", "URL", "Status", "Priority", "Depth", "URL Type", "Checked At"]
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = HDR; cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center")

    for row in rows:
        ws.append([row["num"], row["url"], row["status"], row["priority"], row["depth"], row["url_type"], row["checked_at"]])
        c = ws.cell(ws.max_row, 3)
        c.fill = GF if row["status"] == "Indexed" else RF if row["status"] == "Not Indexed" else YF

    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 65
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 8
    ws.column_dimensions["F"].width = 22
    ws.column_dimensions["G"].width = 22

    ws2 = wb.create_sheet("By URL Type")
    ws2.append(["URL Type", "Indexed", "Not Indexed", "Other", "Total"])
    for cell in ws2[1]: cell.fill = HDR; cell.font = Font(bold=True, color="FFFFFF")
    for t, c in sorted(type_summary.items()):
        ws2.append([t, c.get("Indexed",0), c.get("Not Indexed",0), c.get("Other",0), sum(c.values())])
    for col in "ABCDE": ws2.column_dimensions[col].width = 22

    wb.save(path)
    print(f"  Excel  → {BOLD}{path}{RESET}")


def generate_html(rows: list[dict], path: Path, counts: dict, type_summary: dict, compare: dict | None, history: list[dict]) -> None:
    indexed     = counts.get("Indexed", 0)
    not_indexed = counts.get("Not Indexed", 0)
    other       = sum(v for k, v in counts.items() if k not in ("Indexed","Not Indexed"))
    total       = indexed + not_indexed + other
    pct         = round(indexed / total * 100, 1) if total else 0

    t_labels  = json.dumps(list(type_summary.keys()))
    t_indexed = json.dumps([v.get("Indexed", 0) for v in type_summary.values()])
    t_not     = json.dumps([v.get("Not Indexed", 0) for v in type_summary.values()])

    hist_dates   = json.dumps([h["date"][:10] for h in history])
    hist_indexed = json.dumps([h["indexed"] for h in history])
    hist_not     = json.dumps([h["not_indexed"] for h in history])

    compare_html = ""
    if compare:
        ni, nd = compare["newly_indexed"], compare["newly_deindexed"]
        ni_li  = "".join(f"<li><a href='{_esc(u)}' target='_blank'>{_esc(u)}</a></li>" for u in ni)
        nd_li  = "".join(f"<li><a href='{_esc(u)}' target='_blank'>{_esc(u)}</a></li>" for u in nd)
        compare_html = f"""
        <div class="section">
          <h2>Changes Since Last Run</h2>
          <div class="summary-cards" style="margin-bottom:16px">
            <div class="card green"><span class="num">{len(ni)}</span><span class="lbl">Newly Indexed</span></div>
            <div class="card red"><span class="num">{len(nd)}</span><span class="lbl">Newly De-indexed</span></div>
          </div>
          {"<h3 class='change-head green-txt'>Newly Indexed</h3><ul class='change-list'>" + ni_li + "</ul>" if ni else ""}
          {"<h3 class='change-head red-txt'>Newly De-indexed</h3><ul class='change-list red-list'>" + nd_li + "</ul>" if nd else ""}
        </div>"""

    rows_html = "".join(
        f"<tr class='{'indexed' if r['status']=='Indexed' else 'not-indexed' if r['status']=='Not Indexed' else 'other'}'>"
        f"<td>{_esc(r['num'])}</td>"
        f"<td><a href='{_esc(r['url'])}' target='_blank'>{_esc(r['url'])}</a></td>"
        f"<td>{'✅' if r['status']=='Indexed' else '❌' if r['status']=='Not Indexed' else '⚠️'} {_esc(r['status'])}</td>"
        f"<td><span class='badge badge-{'high' if r['priority']=='High' else 'med' if r['priority']=='Medium' else 'low'}'>{_esc(r['priority'])}</span></td>"
        f"<td>{_esc(r['depth'])}</td>"
        f"<td>{_esc(r['url_type'])}</td>"
        f"<td>{_esc(r['checked_at'])}</td></tr>"
        for r in rows
    )

    trend_section = ""
    if len(history) > 1:
        trend_section = f"""
        <div class="section">
          <h2>Trend — Last {len(history)} Runs</h2>
          <canvas id="trend" height="80"></canvas>
        </div>"""

    other_btn = f"<button class='btn' onclick=\"filterRows('other',this)\">⚠️ Other ({other})</button>" if other else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Indexing Report {datetime.now().strftime('%Y-%m-%d')}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<link rel="stylesheet" href="https://cdn.datatables.net/1.13.8/css/jquery.dataTables.min.css">
<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.datatables.net/1.13.8/js/jquery.dataTables.min.js"></script>
<style>
/* DataTables overrides to match report theme */
.dataTables_wrapper .dataTables_length select,
.dataTables_wrapper .dataTables_filter input{{
  border:1px solid #ddd;border-radius:8px;padding:5px 10px;font-size:12px;
}}
.dataTables_wrapper .dataTables_paginate .paginate_button{{
  border-radius:6px;font-size:12px;padding:4px 10px;
}}
.dataTables_wrapper .dataTables_paginate .paginate_button.current{{
  background:#1F4E79;color:#fff!important;border-color:#1F4E79;
}}
.dataTables_wrapper .dataTables_info{{font-size:12px;color:#666}}
</style>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f2f5;color:#1a1a2e}}
header{{background:#1F4E79;color:#fff;padding:20px 40px;display:flex;justify-content:space-between;align-items:center}}
header h1{{font-size:20px;font-weight:700}}
header p{{opacity:.7;font-size:13px}}
.container{{max-width:1300px;margin:24px auto;padding:0 24px}}
.summary-cards{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:24px}}
.card{{background:#fff;border-radius:12px;padding:18px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.06);display:flex;flex-direction:column;gap:4px}}
.card .num{{font-size:34px;font-weight:800}}
.card .lbl{{font-size:11px;color:#666;text-transform:uppercase;letter-spacing:.5px}}
.card.blue .num{{color:#0969da}}.card.green .num{{color:#1a7f37}}.card.red .num{{color:#cf222e}}
.card.yellow .num{{color:#9a6700}}.card.purple .num{{color:#6f42c1}}
.section{{background:#fff;border-radius:12px;padding:22px;margin-bottom:22px;box-shadow:0 2px 8px rgba(0,0,0,.06)}}
.section h2{{font-size:15px;font-weight:700;color:#1F4E79;margin-bottom:14px}}
.charts{{display:grid;grid-template-columns:1fr 2fr;gap:22px;margin-bottom:22px}}
.filters{{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center}}
.btn{{padding:6px 14px;border:none;border-radius:20px;cursor:pointer;font-size:12px;background:#e8eaf0;color:#444}}
.btn.active{{background:#1F4E79;color:#fff}}
input[type=text]{{padding:6px 12px;border:1px solid #ddd;border-radius:8px;font-size:12px;width:260px}}
table{{width:100%;border-collapse:collapse}}
th{{background:#1F4E79;color:#fff;padding:10px 13px;text-align:left;font-size:12px}}
td{{padding:9px 13px;font-size:12px;border-bottom:1px solid #f0f2f5;vertical-align:middle}}
td a{{color:#0969da;text-decoration:none;word-break:break-all}}
td a:hover{{text-decoration:underline}}
tr.indexed td:nth-child(3){{color:#1a7f37;font-weight:600}}
tr.not-indexed td:nth-child(3){{color:#cf222e;font-weight:600}}
tr:hover td{{background:#f8f9fb}}
.badge{{padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600}}
.badge-high{{background:#d4edda;color:#155724}}
.badge-med{{background:#fff3cd;color:#856404}}
.badge-low{{background:#f8d7da;color:#721c24}}
.change-head{{font-size:13px;margin:12px 0 6px}}
.green-txt{{color:#1a7f37}}.red-txt{{color:#cf222e}}
.change-list{{padding-left:18px;font-size:12px}}
.change-list li{{margin:3px 0;color:#1a7f37}}
.change-list.red-list li{{color:#cf222e}}
.pct-bar{{background:#e8eaf0;border-radius:10px;height:8px;margin-top:8px;overflow:hidden}}
.pct-fill{{background:#1a7f37;height:100%;border-radius:10px;width:{pct}%}}
</style>
</head>
<body>
<header>
  <div><h1>Google Indexing Status Report</h1><p>Generated {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p></div>
  <div style="text-align:right;color:white"><div style="font-size:28px;font-weight:800">{pct}%</div><div style="opacity:.7;font-size:12px">Index Rate</div></div>
</header>
<div class="container">
  <div class="summary-cards">
    <div class="card blue"><span class="num">{total}</span><span class="lbl">Total Checked</span></div>
    <div class="card green"><span class="num">{indexed}</span><span class="lbl">Indexed</span></div>
    <div class="card red"><span class="num">{not_indexed}</span><span class="lbl">Not Indexed</span></div>
    <div class="card yellow"><span class="num">{other}</span><span class="lbl">Errors/Other</span></div>
    <div class="card purple"><span class="num">{pct}%</span><span class="lbl">Index Rate<div class="pct-bar"><div class="pct-fill"></div></div></span></div>
  </div>

  {compare_html}
  {trend_section}

  <div class="charts">
    <div class="section" style="margin:0"><h2>Indexed vs Not Indexed</h2><canvas id="pie"></canvas></div>
    <div class="section" style="margin:0"><h2>By URL Type</h2><canvas id="bar"></canvas></div>
  </div>

  <div class="section">
    <h2>All Results</h2>
    <div class="filters">
      <button class="btn active" onclick="filterRows('all',this)">All ({total})</button>
      <button class="btn" onclick="filterRows('indexed',this)">✅ Indexed ({indexed})</button>
      <button class="btn" onclick="filterRows('not-indexed',this)">❌ Not Indexed ({not_indexed})</button>
      {other_btn}
      <button class="btn" onclick="filterRows('high-pri',this)">🔴 High Priority</button>
    </div>
    <table id="results-table">
      <thead><tr><th>#</th><th>URL</th><th>Status</th><th>Priority</th><th>Depth</th><th>Type</th><th>Checked At</th></tr></thead>
      <tbody id="tb">{rows_html}</tbody>
    </table>
  </div>
</div>
<script>
new Chart(document.getElementById('pie'),{{
  type:'doughnut',
  data:{{labels:['Indexed','Not Indexed','Other'],datasets:[{{data:[{indexed},{not_indexed},{other}],backgroundColor:['#1a7f37','#cf222e','#9a6700'],borderWidth:0}}]}},
  options:{{plugins:{{legend:{{position:'bottom'}}}},cutout:'60%'}}
}});
new Chart(document.getElementById('bar'),{{
  type:'bar',
  data:{{labels:{t_labels},datasets:[{{label:'Indexed',data:{t_indexed},backgroundColor:'#1a7f37'}},{{label:'Not Indexed',data:{t_not},backgroundColor:'#cf222e'}}]}},
  options:{{responsive:true,plugins:{{legend:{{position:'bottom'}}}},scales:{{x:{{ticks:{{maxRotation:45}}}},y:{{beginAtZero:true}}}}}}
}});
{"new Chart(document.getElementById('trend'),{type:'line',data:{labels:" + hist_dates + ",datasets:[{label:'Indexed',data:" + hist_indexed + ",borderColor:'#1a7f37',backgroundColor:'rgba(26,127,55,.1)',tension:.4,fill:true},{label:'Not Indexed',data:" + hist_not + ",borderColor:'#cf222e',backgroundColor:'rgba(207,34,46,.1)',tension:.4,fill:true}]},options:{responsive:true,plugins:{legend:{position:'bottom'}},scales:{y:{beginAtZero:true}}}});" if len(history) > 1 else ""}
var _activeFilter='all';
var dt=$(document).ready(function(){{
  var table=$('#results-table').DataTable({{
    pageLength:50,
    lengthMenu:[[25,50,100,250,-1],['25','50','100','250','All']],
    order:[[0,'asc']],
    columnDefs:[{{targets:0,width:'40px'}},{{targets:4,width:'60px'}}],
    language:{{search:'🔍 Search:',lengthMenu:'Show _MENU_ rows',info:'Showing _START_–_END_ of _TOTAL_ URLs',paginate:{{previous:'‹',next:'›'}}}}
  }});
  $.fn.dataTable.ext.search.push(function(settings,data,dataIndex,rowData,counter){{
    var row=$(table.row(dataIndex).node());
    if(_activeFilter==='all') return true;
    if(_activeFilter==='high-pri') return row.find('td:nth-child(4)').text().trim()==='High';
    return row.hasClass(_activeFilter);
  }});
  window._dt=table;
}});
function filterRows(type,btn){{
  document.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  _activeFilter=type;
  window._dt.draw();
}}
</script>
</body>
</html>"""

    path.write_text(html, encoding="utf-8")
    print(f"  HTML   → {BOLD}{path}{RESET}")


# ══════════════════════════════════════════════════════════════════════════════
# CORE RUN LOGIC
# ══════════════════════════════════════════════════════════════════════════════

def _run_browser_pass(urls: list[str], headless: bool, proxy_list: list,
                      delay_state: dict, on_result: Callable) -> None:
    """Check a batch of URLs via a single browser tab (SERP `site:` scrape).

    Used as the fallback when GSC can't answer for a URL. Opens one Chromium
    context, dismisses the consent dialog, and runs google_check per URL,
    reporting each via on_result.
    """
    _require_playwright()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            proxy={"server": proxy_list[0]} if proxy_list else None,
        )
        ctx = browser.new_context(
            user_agent=CHROME_UA,
            viewport={"width": 1280, "height": 800}, locale="en-US",
        )
        page = ctx.new_page()
        stealth_sync(page)
        page.goto("https://www.google.com", wait_until="domcontentloaded"); time.sleep(2)
        try:
            btn = page.locator("button:has-text('Accept all'), button:has-text('I agree')")
            if btn.count() > 0: btn.first.click(); time.sleep(1)
        except Exception:
            pass
        iterator = tqdm(urls, unit="url") if HAS_TQDM else urls
        for url in iterator:
            on_result(url, google_check(page, url, delay_state))
        try:
            browser.close()
        except Exception:
            pass


def run_check(urls: list[str], use_gsc: bool | None = None, headless: bool = False,
              quiet: bool = False, progress_cb: Callable | None = None) -> tuple[list[dict], dict, dict, dict]:
    # GSC URL Inspection is the authoritative, ToS-compliant indexation source,
    # so prefer it whenever it's configured. SERP scraping is the fallback — used
    # for URLs GSC can't answer (properties the service account doesn't own) or
    # when GSC isn't set up at all. `use_gsc=None` means "auto-detect from config".
    if use_gsc is None:
        use_gsc = bool(CFG.get("gsc", {}).get("enabled"))
    gsc_service = build_gsc_service() if use_gsc else None
    if use_gsc and gsc_service is None:
        use_gsc = False  # GSC requested but unavailable — fall back to browser
    if not use_gsc:
        _require_playwright()
    # Sort before joining so the resume key is stable across runs that happen
    # to receive the same set of URLs in a different order.
    pf   = progress_file_for(",".join(sorted(urls)[:3]))
    full_saved = load_progress(pf)
    # Scope saved results to only the URLs in this run so the limit is honoured
    urls_set = set(urls)
    saved    = {u: s for u, s in full_saved.items() if u in urls_set}
    # Only skip URLs that definitively resolved — retry Error/Timeout/Other
    already_done   = {u for u, s in saved.items() if s in ("Indexed", "Not Indexed")}
    remaining      = [u for u in urls if u not in already_done]

    counts: dict       = {}
    type_summary: dict = {}
    all_rows: list     = []
    current_results    = dict(saved)
    failed_urls: list  = []

    # Seed resumed results (only URLs in this run)
    for url in urls:
        if url not in saved:
            continue
        status = saved[url]
        t = get_url_type(url)
        type_summary.setdefault(t, {})
        type_summary[t][status] = type_summary[t].get(status, 0) + 1
        counts[status] = counts.get(status, 0) + 1
        all_rows.append({"num": len(all_rows)+1, "url": url, "status": status,
                         "priority": get_priority_score(url), "depth": get_crawl_depth(url),
                         "url_type": get_url_type(url), "checked_at": "resumed"})

    # gsc_service was already resolved at the top of run_check (GSC-first logic).
    proxy_list     = CFG.get("proxies", [])
    n_parallel     = min(CFG.get("parallel_tabs", 1), len(remaining)) if remaining else 1
    delay_state    = {"base": _t("delay_base_secs", 3.0), "count": 0}

    _result_lock = threading.Lock()

    def on_result(url: str, status: str):
        ts       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        priority = get_priority_score(url)
        depth    = get_crawl_depth(url)
        url_type = get_url_type(url)

        with _result_lock:
            if "Error" in status or status == "Timeout":
                failed_urls.append(url)

            counts[status] = counts.get(status, 0) + 1
            current_results[url] = status
            type_summary.setdefault(url_type, {})
            type_summary[url_type][status] = type_summary[url_type].get(status, 0) + 1
            num = len(all_rows) + 1
            all_rows.append({"num": num, "url": url, "status": status, "priority": priority,
                             "depth": depth, "url_type": url_type, "checked_at": ts})
            # Merge into full saved file so URLs outside this run's limit are preserved
            save_progress(pf, {**full_saved, **current_results})

        if progress_cb:
            progress_cb(num, len(urls), url, status)

        if not quiet or status != "Indexed":
            icon = f"{GREEN}✅{RESET}" if status=="Indexed" else (f"{RED}❌{RESET}" if status=="Not Indexed" else f"{YELLOW}⚠{RESET}")
            with _print_lock:
                print(f"[{num:>4}] {url}\n       {icon} {status}\n")

    if use_gsc and gsc_service:
        print(f"\n{BOLD}Using Google Search Console API (primary)…{RESET}\n")
        iterator = tqdm(remaining, unit="url") if HAS_TQDM else remaining
        # URLs GSC can't resolve (not an owned property, quota exhausted, etc.)
        # are deferred to a browser SERP-scrape fallback so they still get a verdict.
        gsc_deferred: list[tuple[str, str]] = []
        for url in iterator:
            status = gsc_check_url(url, gsc_service)
            if status.startswith("GSC Error"):
                gsc_deferred.append((url, status))
            else:
                on_result(url, status)

        if gsc_deferred:
            if sync_playwright is None:
                # No browser available — surface the GSC error rather than guessing.
                for url, err in gsc_deferred:
                    on_result(url, err)
            else:
                print(f"\n{YELLOW}GSC could not resolve {len(gsc_deferred)} URL(s) "
                      f"(not owned / quota) — falling back to browser…{RESET}\n")
                _run_browser_pass([u for u, _ in gsc_deferred], headless,
                                  proxy_list, delay_state, on_result)
    elif n_parallel > 1:
        print(f"\n{BOLD}Using {n_parallel} parallel browser tabs…{RESET}\n")
        check_parallel(remaining, n_parallel, proxy_list, headless, delay_state, on_result)
    else:
        print(f"\n{BOLD}Checking {len(remaining)} URLs…{RESET}\n")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=headless,
                args=["--disable-blink-features=AutomationControlled","--no-sandbox"],
                proxy={"server": proxy_list[0]} if proxy_list else None
            )
            ctx  = browser.new_context(
                user_agent=CHROME_UA,
                viewport={"width": 1280, "height": 800}, locale="en-US"
            )
            page = ctx.new_page()
            stealth_sync(page)
            page.goto("https://www.google.com", wait_until="domcontentloaded"); time.sleep(2)
            try:
                btn = page.locator("button:has-text('Accept all'), button:has-text('I agree')")
                if btn.count() > 0: btn.first.click(); time.sleep(1)
            except Exception: pass

            iterator = tqdm(remaining, unit="url") if HAS_TQDM else remaining
            for url in iterator:
                on_result(url, google_check(page, url, delay_state))

            # Retry failed URLs with a fresh browser so a crashed context doesn't block retries
            if failed_urls:
                print(f"\n{YELLOW}Auto-retrying {len(failed_urls)} failed URLs…{RESET}\n")
                try:
                    with sync_playwright() as retry_pw:
                        retry_browser = retry_pw.chromium.launch(
                            headless=headless,
                            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                            proxy={"server": proxy_list[0]} if proxy_list else None
                        )
                        retry_ctx  = retry_browser.new_context(
                            user_agent=CHROME_UA,
                            viewport={"width": 1280, "height": 800}, locale="en-US"
                        )
                        retry_page = retry_ctx.new_page()
                        stealth_sync(retry_page)
                        retry_page.goto("https://www.google.com", wait_until="domcontentloaded")
                        time.sleep(2)
                        for url in failed_urls:
                            status = google_check(retry_page, url, delay_state)
                            for row in all_rows:
                                if row["url"] == url:
                                    old = row["status"]
                                    counts[old] = max(0, counts.get(old, 0) - 1)
                                    counts[status] = counts.get(status, 0) + 1
                                    row["status"] = status
                                    current_results[url] = status
                                    save_progress(pf, {**full_saved, **current_results})
                                    break
                            with _print_lock:
                                print(f"  [retry] {url} → {status}")
                        try:
                            retry_browser.close()
                        except Exception:
                            pass
                except Exception as e:
                    with _print_lock:
                        print(f"{YELLOW}  Retry pass failed: {e}{RESET}")

            try:
                browser.close()
            except Exception:
                pass

    if pf.exists(): pf.unlink()
    return all_rows, counts, type_summary, current_results


# ══════════════════════════════════════════════════════════════════════════════
# SCHEDULE
# ══════════════════════════════════════════════════════════════════════════════

def scheduled_run():
    cfg  = CFG.get("schedule", {})
    surl = cfg.get("sitemap_url", "")
    if not surl:
        print(f"{RED}[SCHEDULED] No sitemap_url in config — skipping run{RESET}")
        return
    lim  = cfg.get("limit", 100)
    urls = fetch_sitemap_urls(surl)[:lim]
    print(f"\n{CYAN}[SCHEDULED] Running at {datetime.now().strftime('%H:%M:%S')}…{RESET}")
    execute_and_save(urls)

def start_scheduler():
    if not HAS_SCHEDULE:
        print(f"{RED}schedule not installed{RESET}"); return
    cfg      = CFG.get("schedule", {})
    interval = cfg.get("interval", "daily")
    t        = cfg.get("time", "08:00")
    if interval == "daily":
        sched.every().day.at(t).do(scheduled_run)
    elif interval == "weekly":
        sched.every().monday.at(t).do(scheduled_run)
    elif interval == "hourly":
        sched.every().hour.do(scheduled_run)
    print(f"{GREEN}Scheduler started — {interval} at {t}{RESET}")
    while True:
        sched.run_pending(); time.sleep(30)


def execute_and_save(urls: list[str], headless: bool = False, quiet: bool = False,
                     use_gsc: bool | None = None, do_compare: bool = False,
                     prev_report: Path | None = None,
                     progress_cb: Callable | None = None) -> Path:
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path    = REPORTS_DIR / f"indexing_report_{timestamp}.csv"
    excel_path  = REPORTS_DIR / f"indexing_report_{timestamp}.xlsx"
    html_path   = REPORTS_DIR / f"indexing_report_{timestamp}.html"

    all_rows, counts, type_summary, current_results = run_check(
        urls, use_gsc=use_gsc, headless=headless, quiet=quiet, progress_cb=progress_cb
    )

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["#","URL","Google Indexed","Priority","Depth","URL Type","Checked At"])
        for r in all_rows:
            w.writerow([r["num"],r["url"],r["status"],r["priority"],r["depth"],r["url_type"],r["checked_at"]])

    compare_data = compare_runs(current_results, prev_report) if do_compare and prev_report else None

    save_history(counts, len(all_rows), timestamp)
    history = load_history()

    print(f"\n{BOLD}Generating reports…{RESET}")
    _gen = ReportGenerator()
    try:
        _gen.excel(all_rows, excel_path, type_summary)
        _gen.html(all_rows, html_path, counts, type_summary, compare_data, history)
    except Exception:
        # Clean up any partially-written companion files so the CSV (primary
        # discovery file) is never left with orphaned siblings on disk.
        for _p in (excel_path, html_path):
            if _p.exists():
                try: _p.unlink()
                except OSError: pass
        raise
    print(f"  CSV    → {BOLD}{csv_path}{RESET}")

    NotificationService(CFG).notify_all(counts, len(all_rows), html_path)

    total = len(all_rows)
    print(f"\n{BOLD}{CYAN}{'='*56}\n  SUMMARY\n{'='*56}{RESET}")
    print(f"  Total          : {total}")
    print(f"  {GREEN}Indexed        : {counts.get('Indexed',0)}{RESET}")
    print(f"  {RED}Not Indexed    : {counts.get('Not Indexed',0)}{RESET}")
    errs = sum(v for k,v in counts.items() if k not in ("Indexed","Not Indexed"))
    if errs: print(f"  {YELLOW}Errors/Other   : {errs}{RESET}")
    print(f"\n{BOLD}  By URL Type:{RESET}")
    for t, c in sorted(type_summary.items()):
        print(f"    {t:<30} {GREEN}{c.get('Indexed',0)} indexed{RESET}  {RED}{c.get('Not Indexed',0)} not indexed{RESET}")
    if compare_data:
        print(f"\n{BOLD}  Changes:{RESET}")
        print(f"    {GREEN}Newly indexed    : {len(compare_data['newly_indexed'])}{RESET}")
        print(f"    {RED}Newly de-indexed : {len(compare_data['newly_deindexed'])}{RESET}")
    print(f"\n  Open → {BOLD}{html_path}{RESET}\n")
    return html_path


# ══════════════════════════════════════════════════════════════════════════════
# MAIN CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    from core.version import CLI_BANNER
    print(f"\n{BOLD}{CYAN}{'='*56}")
    print(f"  {CLI_BANNER} — Indexing Checker")
    print("   Parallel · GSC · Proxy · Schedule · Notify")
    print(f"{'='*56}{RESET}\n")

    urls = get_urls_from_user()
    if not urls: print(f"{RED}No URLs.{RESET}"); sys.exit(1)
    print(f"\n{GREEN}Found {len(urls)} URLs.{RESET}")

    pattern = input("Filter by URL pattern (e.g. /category/) or Enter to skip: ").strip()
    urls    = filter_urls(urls, pattern)
    if pattern: print(f"{CYAN}Filtered to {len(urls)} URLs{RESET}")

    # Resume
    pf      = progress_file_for(",".join(sorted(urls)[:3]))
    saved   = load_progress(pf)
    if saved:
        print(f"\n{YELLOW}Previous progress: {len(saved)} URLs checked.{RESET}")
        if input("Resume? (y/n): ").strip().lower() != "y":
            saved = {}; pf.unlink(missing_ok=True)

    remaining = [u for u in urls if u not in saved]
    print(f"{GREEN}{len(remaining)} URLs to check.{RESET}")

    raw = input("How many to check? (number or 'all'): ").strip()
    if raw.lower() != "all":
        try: remaining = remaining[:int(raw)]
        except ValueError: remaining = remaining[:10]

    # Options
    use_gsc  = CFG.get("gsc", {}).get("enabled") and input("Use GSC API? (y/n): ").strip().lower() == "y"
    quiet    = input("Show only Not Indexed? (y/n): ").strip().lower() == "y"
    headless = input("Run browser in background? (y/n): ").strip().lower() == "y"

    # Schedule
    if CFG.get("schedule", {}).get("enabled"):
        if input("Run on schedule instead? (y/n): ").strip().lower() == "y":
            start_scheduler(); return

    # Compare
    prev = find_latest_report()
    do_compare = False
    if prev:
        print(f"\n{CYAN}Previous report: {prev.name}{RESET}")
        do_compare = input("Compare with previous run? (y/n): ").strip().lower() == "y"

    execute_and_save(remaining, headless=headless, quiet=quiet,
                     use_gsc=use_gsc, do_compare=do_compare, prev_report=prev)


if __name__ == "__main__":
    main()
