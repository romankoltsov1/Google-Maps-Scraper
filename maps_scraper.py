#!/usr/bin/env python3
"""
Google Maps Scraper Core Module

Browser-based scraping using Playwright for reliable JavaScript rendering.
"""

from __future__ import annotations

import asyncio
import html
import json
import random
import re
import string
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Playwright for browser automation
from playwright.async_api import async_playwright, Page, Browser, BrowserContext


USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


@dataclass(frozen=True)
class ProxyConfig:
    """Represents a single proxy configuration."""
    scheme: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None

    def build_url(self, session_id: str | None = None, session_length: int | None = None) -> str:
        """Build proxy URL with optional sticky session parameters."""
        username = self.username or ""
        
        if session_id and username:
            if "sessionid-" in username:
                username = re.sub(r"sessionid-[^-:]+", f"sessionid-{session_id}", username)
            elif "package-" in username:
                username = f"{username}-sessionid-{session_id}"

        if session_length and username:
            if "sessionlength-" in username:
                username = re.sub(r"sessionlength-\d+", f"sessionlength-{session_length}", username)
            elif "sessionid-" in username:
                username = f"{username}-sessionlength-{session_length}"

        auth = ""
        if username and self.password:
            auth = f"{urllib.parse.quote(username, safe='-._~')}:{urllib.parse.quote(self.password, safe='-._~')}@"
        elif username:
            auth = f"{urllib.parse.quote(username, safe='-._~')}@"

        return f"{self.scheme}://{auth}{self.host}:{self.port}"


class ProxyPool:
    """Manages a pool of proxies with round-robin distribution."""
    
    def __init__(
        self, 
        proxies: list[ProxyConfig], 
        session_length: int | None = None, 
        sticky: bool = True
    ) -> None:
        self._proxies = proxies
        self._session_length = session_length
        self._sticky = sticky
        self._idx = 0
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self._proxies)
    
    @property
    def size(self) -> int:
        return len(self._proxies)

    async def next_proxy(self, request_key: str) -> str | None:
        """Get next proxy from pool with sticky session support."""
        if not self._proxies:
            return None

        async with self._lock:
            proxy = self._proxies[self._idx % len(self._proxies)]
            self._idx += 1

        session_id = None
        if self._sticky:
            session_id = "s" + ''.join(
                random.choice(string.ascii_lowercase + string.digits) for _ in range(12)
            )

        return proxy.build_url(session_id=session_id, session_length=self._session_length)


def parse_proxy_line(line: str) -> ProxyConfig:
    """
    Parse proxy from various formats:
    - host:port username:password
    - username:password@host:port  
    - http://username:password@host:port
    - proxy.soax.com:5000 package-...-sessionid-...:PASSWORD
    """
    value = line.strip()
    if not value or value.startswith("#"):
        raise ValueError("empty or comment")

    # Format: host:port username:password (SOAX style)
    if " " in value and "@" not in value:
        hostport, auth = value.split(None, 1)
        value = f"{auth}@{hostport}"

    # Add scheme if missing
    if "://" not in value:
        value = f"http://{value}"

    parsed = urllib.parse.urlparse(value)
    if not parsed.hostname or not parsed.port:
        raise ValueError(f"invalid proxy format: {line}")

    username = urllib.parse.unquote(parsed.username) if parsed.username else None
    password = urllib.parse.unquote(parsed.password) if parsed.password else None

    return ProxyConfig(
        scheme=parsed.scheme or "http",
        host=parsed.hostname,
        port=parsed.port,
        username=username,
        password=password,
    )


def load_proxies(path: Path | None) -> list[ProxyConfig]:
    """Load proxies from file."""
    if not path:
        return []

    proxies: list[ProxyConfig] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            p = parse_proxy_line(raw)
            proxies.append(p)
        except ValueError:
            continue
    return proxies


async def create_browser_context(
    playwright,
    proxy_url: str | None = None,
    headless: bool = True
) -> tuple[Browser, BrowserContext]:
    """Create a browser context with optional proxy."""
    
    # Launch browser without proxy first
    args = [
        '--disable-blink-features=AutomationControlled',
        '--disable-http2',  # SOAX proxies don't handle HTTP/2 well
        '--disable-quic',   # Disable QUIC protocol
    ]
    
    browser = await playwright.chromium.launch(
        headless=headless,
        args=args
    )
    
    # Build context options
    context_options = {
        "viewport": {"width": 1920, "height": 1080},
        "user_agent": random.choice(USER_AGENTS),
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "permissions": [],
    }
    
    # Add proxy at context level (more reliable for HTTP proxies)
    if proxy_url:
        parsed = urllib.parse.urlparse(proxy_url)
        # For HTTP proxies, use http:// scheme explicitly
        # Playwright will handle HTTPS through HTTP proxy correctly
        proxy_config = {
            "server": f"http://{parsed.hostname}:{parsed.port}",
        }
        if parsed.username:
            proxy_config["username"] = urllib.parse.unquote(parsed.username)
        if parsed.password:
            proxy_config["password"] = urllib.parse.unquote(parsed.password)
        context_options["proxy"] = proxy_config
    
    context = await browser.new_context(**context_options)
    
    # Set cookies to bypass consent
    await context.add_cookies([
        {
            "name": "CONSENT",
            "value": "YES+cb.20210328-17-p0.en+FX+",
            "domain": ".google.com",
            "path": "/",
        },
        {
            "name": "SOCS",
            "value": "CAESHAgBEhJnd3NfMjAyMzA2MTItMF9SQzIaAmRlIAEaBgiAo_CmBg",
            "domain": ".google.com",
            "path": "/",
        },
    ])
    
    return browser, context


async def test_proxy(
    playwright,
    proxy_url: str,
    timeout_s: float = 10.0
) -> tuple[bool, str]:
    """Test if a proxy is working.
    
    Returns:
        (success: bool, message: str)
    """
    try:
        browser, context = await create_browser_context(playwright, proxy_url, headless=True)
        page = await context.new_page()
        
        try:
            await page.goto("https://www.google.com", timeout=int(timeout_s * 1000))
            await browser.close()
            return True, "Proxy is working"
        except Exception as e:
            await browser.close()
            error_msg = str(e)
            if "ERR_TUNNEL_CONNECTION_FAILED" in error_msg:
                return False, "Proxy connection failed - check proxy URL and credentials"
            elif "ERR_PROXY_CONNECTION_FAILED" in error_msg:
                return False, "Cannot connect to proxy server - proxy may be down"
            elif "auth" in error_msg.lower():
                return False, "Proxy authentication failed - check username/password"
            else:
                return False, f"Proxy error: {error_msg[:100]}"
    except Exception as e:
        return False, f"Failed to create browser with proxy: {str(e)[:100]}"


async def scroll_results_panel(
    page: Page,
    scroll_limit: int = 10,
    scroll_pause: float = 2.0,
) -> int:
    """Scroll the results panel to load more results.
    
    Args:
        page: Playwright page object
        scroll_limit: Maximum number of scroll attempts
        scroll_pause: Seconds to wait between scrolls
        
    Returns:
        Total number of results found after scrolling
    """
    # Google Maps feed container selector (most reliable)
    scroll_container = page.locator('[role="feed"]').first
    
    # Fallback: try other selectors if feed not found
    if await scroll_container.count() == 0:
        fallback_selectors = [
            '.m6QErb',
            '.section-scrollbox',
            '[role="main"]',
        ]
        for selector in fallback_selectors:
            container = page.locator(selector).first
            if await container.count() > 0:
                scroll_container = container
                break
    
    if await scroll_container.count() == 0:
        # No scrollable container found, return current count
        return await page.locator('a[href*="/maps/place/"]').count()
    
    total_loaded = 0
    no_change_count = 0
    
    # Scroll multiple times to load more results
    for i in range(scroll_limit):
        try:
            # Get current result count
            current_links = await page.locator('a[href*="/maps/place/"]').count()
            
            # Perform scroll
            await scroll_container.evaluate("el => el.scrollBy(0, 800)")
            
            # Wait for potential new results to load
            await page.wait_for_timeout(int(scroll_pause * 1000))
            
            # Check if new results appeared
            new_links = await page.locator('a[href*="/maps/place/"]').count()
            
            if new_links > current_links:
                total_loaded = new_links
                no_change_count = 0
            else:
                no_change_count += 1
                # If no change for 2 consecutive scrolls, we've likely reached the end
                if no_change_count >= 2:
                    break
                    
        except Exception:
            continue
    
    return total_loaded or await page.locator('a[href*="/maps/place/"]').count()


async def fetch_page_with_playwright(
    playwright,
    url: str,
    proxy_url: str | None = None,
    timeout_s: float = 30.0,
    headless: bool = True,
    scroll_limit: int = 10,
    scroll_pause: float = 2.0,
) -> tuple[str, Page]:
    """Fetch page content using Playwright browser. Returns HTML and page object.
    
    Args:
        playwright: Playwright instance
        url: URL to fetch
        proxy_url: Optional proxy URL
        timeout_s: Page load timeout in seconds
        headless: Run browser in headless mode
        scroll_limit: Number of scroll attempts to load more results
        scroll_pause: Seconds to wait between scrolls
    """
    browser, context = await create_browser_context(playwright, proxy_url, headless)
    
    page = await context.new_page()
    
    # Navigate to the page
    response = await page.goto(
        url,
        wait_until="load",
        timeout=int(timeout_s * 1000)
    )
    
    if not response:
        raise Exception("Page navigation failed")
    
    # Wait for initial results to load
    await page.wait_for_timeout(5000)
    
    # Scroll to load more results if needed
    if scroll_limit > 0:
        await scroll_results_panel(page, scroll_limit, scroll_pause)
    
    # Get page content
    content = await page.content()
    
    return content, page


async def extract_places_from_page(page: Page) -> list[dict[str, Any]]:
    """Extract place data directly from Playwright page using selectors."""
    places = []
    
    # Find all containers that have place links inside
    # Use query_selector_all to get actual elements
    containers = await page.query_selector_all('div:has(> a[href*="/maps/place/"])')
    
    seen_urls: set[str] = set()
    
    for container in containers:
        try:
            # Get the place link from this container
            link_elem = await container.query_selector('a[href*="/maps/place/"]')
            if not link_elem:
                continue
                
            href = await link_elem.get_attribute('href')
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)
            
            # Extract data from URL
            full_url = href if href.startswith('http') else f"https://www.google.com{href}"
            
            # Get title - look for heading role
            title = None
            title_elem = await container.query_selector('div[role="heading"], .fontHeadlineSmall')
            if title_elem:
                title = await title_elem.text_content()
            
            # If no title found, extract from URL
            if not title:
                url_match = re.search(r'/maps/place/([^/]+)', href)
                if url_match:
                    title = urllib.parse.unquote_plus(url_match.group(1)).replace('+', ' ')
            
            # Get rating - look for span with rating pattern (like "4.5" or "4,5")
            rating = None
            spans = await container.query_selector_all('span')
            for span in spans:
                text = await span.text_content()
                if text:
                    # Match rating pattern: number with . or , (European format)
                    rating_match = re.match(r'^([0-9]+[,.][0-9])$', text.strip())
                    if rating_match:
                        # Convert European comma to dot
                        rating_str = rating_match.group(1).replace(',', '.')
                        try:
                            rating = float(rating_str)
                            break
                        except ValueError:
                            pass
            
            # Get website - look for external links
            website = None
            external_links = await container.query_selector_all('a[href^="http"]')
            for ext_link in external_links:
                href_val = await ext_link.get_attribute('href')
                if href_val and 'google.com' not in href_val and '/maps/place/' not in href_val:
                    website = href_val
                    break
            
            # Get image URL
            image_url = None
            imgs = await container.query_selector_all('img')
            for img in imgs:
                src = await img.get_attribute('src')
                if src and ('googleusercontent.com' in src or 'gstatic.com' in src or 'google maps' in (await img.get_attribute('alt') or '').lower()):
                    image_url = src
                    break
            
            place = {
                "position": len(places) + 1,
                "title": title.strip() if title else None,
                "rating": rating,
                "website": website,
                "image_url": image_url,
                "maps_url": full_url,
            }
            places.append(place)
            
        except Exception:
            continue
    
    return places


def extract_places_from_html(html_content: str) -> list[dict[str, Any]]:
    """Extract place data from Google Maps HTML."""
    places = []
    
    # Look for place links
    hrefs = re.findall(r'href="(/maps/place/[^"]+)"', html_content)
    
    seen: set[str] = set()
    for raw_href in hrefs:
        href = html.unescape(raw_href)
        href = urllib.parse.unquote(href)
        
        # Extract data_id and place_id from href
        data_id_match = re.search(r"0x[a-fA-F0-9]+:0x[a-fA-F0-9]+", href)
        place_id_match = re.search(r"(?:!1s|place_id:|ludocid\\x3d|ludocid%3D|ludocid=)(ChI[a-zA-Z0-9_-]+)", href)
        latlng_match = re.search(r"!3d(-?\d+(?:\.\d+)+)!4d(-?\d+(?:\.\d+)+)", href)
        
        # Create unique key
        dedupe_key = (place_id_match.group(1) if place_id_match else "") + "|" + (data_id_match.group(0) if data_id_match else href)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        
        # Extract title
        title = ""
        m_title = re.search(r"/maps/place/([^/]+)", href)
        if m_title:
            title = urllib.parse.unquote_plus(m_title.group(1)).replace("+", " ")
        
        # Convert data_id to data_cid
        data_cid = None
        if data_id_match:
            try:
                second = data_id_match.group(0).split(":", 1)[1]
                data_cid = str(int(second, 16))
            except Exception:
                pass
        
        place = {
            "title": title or None,
            "place_id": place_id_match.group(1) if place_id_match else None,
            "data_id": data_id_match.group(0) if data_id_match else None,
            "data_cid": data_cid,
            "maps_url": "https://www.google.com" + href,
            "gps_coordinates": {
                "latitude": float(latlng_match.group(1)) if latlng_match else None,
                "longitude": float(latlng_match.group(2)) if latlng_match else None,
            },
        }
        places.append(place)
    
    return places


def extract_json_data(html_content: str) -> list[dict[str, Any]]:
    """Extract place data from embedded JSON in the page."""
    places = []
    
    # Look for AF_initDataCallback which contains the map data
    patterns = [
        r'AF_initDataCallback\s*\(\s*\{[^}]*data\s*:\s*function\s*\(\s*\)\s*\{\s*return\s*(\[.+?\])\s*\}',
        r'AF_initDataCallback\s*\(\s*\{[^}]*data\s*:\s*(\[.+?\])',
        r'window\._APP_INITIALIZATION_STATE_\s*=\s*(\[.+?\]);',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, html_content, re.DOTALL)
        for match in matches:
            try:
                # Try to parse the JSON
                data = json.loads(match)
                # Extract places from the data structure
                places.extend(extract_from_google_data(data))
            except (json.JSONDecodeError, Exception):
                continue
    
    return places


def extract_from_google_data(data: Any) -> list[dict[str, Any]]:
    """Recursively extract place data from Google's complex data structure."""
    places = []
    
    def extract_recursive(obj, depth=0):
        if depth > 10:
            return
        
        if isinstance(obj, list):
            for item in obj:
                extract_recursive(item, depth + 1)
        elif isinstance(obj, dict):
            # Look for place-like structures
            if any(k in obj for k in ["title", "name", "place_id", "fsq_id"]):
                place = {}
                if "title" in obj:
                    place["title"] = obj["title"]
                if "name" in obj:
                    place["title"] = obj["name"]
                if place:
                    places.append(place)
            
            for v in obj.values():
                extract_recursive(v, depth + 1)
    
    extract_recursive(data)
    return places


async def scrape_search_results(
    playwright,
    query: str,
    proxy_pool: ProxyPool,
    timeout_s: float = 30.0,
    headless: bool = True,
    scroll_limit: int = 10,
    scroll_pause: float = 2.0,
) -> list[dict[str, Any]]:
    """Scrape search results for a query with pagination support.
    
    Args:
        playwright: Playwright instance
        query: Search query
        proxy_pool: Proxy pool for rotation
        timeout_s: Page load timeout
        headless: Run browser headless
        scroll_limit: Number of scrolls to load more results (0 = no scrolling)
        scroll_pause: Seconds between scrolls
    """
    search_url = "https://www.google.com/maps/search/" + urllib.parse.quote(query)
    
    # Get proxy if available
    proxy_url = await proxy_pool.next_proxy(query)
    
    # Fetch the page with scrolling
    html_content, page = await fetch_page_with_playwright(
        playwright,
        search_url,
        proxy_url=proxy_url,
        timeout_s=timeout_s,
        headless=headless,
        scroll_limit=scroll_limit,
        scroll_pause=scroll_pause,
    )
    
    # Extract places using Playwright selectors
    places = await extract_places_from_page(page)
    
    await page.close()
    await page.context.close()
    await page.context.browser.close()
    
    return places


async def scrape_place_detail(
    playwright,
    seed: dict[str, Any],
    proxy_pool: ProxyPool,
    timeout_s: float = 30.0,
    headless: bool = True
) -> dict[str, Any]:
    """Scrape detailed information for a single place."""
    place_url = seed.get("maps_url")
    if not place_url:
        return seed
    
    proxy_url = await proxy_pool.next_proxy(place_url)
    
    try:
        html_content = await fetch_page_with_playwright(
            playwright,
            place_url,
            proxy_url=proxy_url,
            timeout_s=timeout_s,
            headless=headless
        )
        
        # Extract JSON-LD data
        jsonld = parse_jsonld(html_content)
        
        # Extract rating and reviews
        rating = None
        reviews = None
        if isinstance(jsonld.get("aggregateRating"), dict):
            rating = jsonld["aggregateRating"].get("ratingValue")
            reviews = jsonld["aggregateRating"].get("reviewCount")
        
        # Extract address
        address = None
        if isinstance(jsonld.get("address"), dict):
            addr = jsonld["address"]
            parts = [
                addr.get("streetAddress"),
                addr.get("addressLocality"),
                addr.get("addressRegion"),
                addr.get("postalCode"),
            ]
            address = ", ".join(str(x) for x in parts if x)
        
        # Extract phone and website
        phone = jsonld.get("telephone")
        website = jsonld.get("url")
        
        # Extract coordinates from JSON-LD if available
        lat = seed.get("gps_coordinates", {}).get("latitude")
        lng = seed.get("gps_coordinates", {}).get("longitude")
        geo = jsonld.get("geo") if isinstance(jsonld.get("geo"), dict) else {}
        lat = geo.get("latitude") or lat
        lng = geo.get("longitude") or lng
        
        # Extract types
        types = []
        jt = jsonld.get("@type")
        if isinstance(jt, str):
            types = [jt]
        elif isinstance(jt, list):
            types = [str(x) for x in jt if x not in ["LocalBusiness", "Place"]]
        
        type_ids = [re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_") for t in types if t]
        
        # Extract operating hours
        operating_hours = None
        hours_spec = jsonld.get("openingHoursSpecification")
        if isinstance(hours_spec, list):
            operating_hours = {}
            for item in hours_spec:
                if isinstance(item, dict):
                    day = item.get("dayOfWeek", "").split("/")[-1].lower()
                    opens = item.get("opens")
                    closes = item.get("closes")
                    if day and opens and closes:
                        operating_hours[day] = f"{opens}–{closes}"
        
        data_id = seed.get("data_id")
        place_id = seed.get("place_id")
        
        result = {
            "position": seed.get("position"),
            "title": seed.get("title") or jsonld.get("name"),
            "place_id": place_id,
            "data_id": data_id,
            "data_cid": seed.get("data_cid"),
            "reviews_link": (
                f"https://serpapi.com/search.json?data_id={urllib.parse.quote(data_id)}&engine=google_maps_reviews&hl=en"
                if data_id else None
            ),
            "photos_link": (
                f"https://serpapi.com/search.json?data_id={urllib.parse.quote(data_id)}&engine=google_maps_photos&hl=en"
                if data_id else None
            ),
            "gps_coordinates": {"latitude": lat, "longitude": lng},
            "place_id_search": (
                f"https://serpapi.com/search.json?engine=google_maps&google_domain=google.com&hl=en&place_id={place_id}"
                if place_id else None
            ),
            "provider_id": seed.get("provider_id"),
            "rating": float(rating) if rating else None,
            "reviews": int(reviews) if reviews else None,
            "price": jsonld.get("priceRange"),
            "type": types[0] if types else None,
            "types": types or None,
            "type_id": type_ids[0] if type_ids else None,
            "type_ids": type_ids or None,
            "address": address,
            "open_state": None,
            "hours": None,
            "operating_hours": operating_hours if operating_hours else None,
            "phone": phone,
            "website": website,
            "extensions": None,
            "unsupported_extensions": None,
            "service_options": None,
            "order_online": None,
            "thumbnail": None,
            "serpapi_thumbnail": None,
        }
        
        return result
        
    except Exception:
        # Return seed data if detail fetch fails
        return seed


def parse_jsonld(place_html: str) -> dict[str, Any]:
    """Extract JSON-LD structured data from HTML."""
    matches = re.findall(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        place_html,
        flags=re.DOTALL | re.IGNORECASE,
    )

    best: dict[str, Any] = {}
    for block in matches:
        txt = html.unescape(block).strip()
        if not txt:
            continue
        try:
            data = json.loads(txt)
        except json.JSONDecodeError:
            continue

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("@type") in {"LocalBusiness", "Place", "Restaurant", "Store"}:
                    return item
        if isinstance(data, dict) and data.get("@type") in {"LocalBusiness", "Place", "Restaurant", "Store"}:
            return data

        if isinstance(data, dict) and not best:
            best = data
    return best


async def scrape_query(
    playwright,
    query: str,
    proxy_pool: ProxyPool,
    timeout_s: float = 30.0,
    concurrency: int | None = None,
    headless: bool = True,
    scroll_limit: int = 10,
    scroll_pause: float = 2.0,
) -> list[dict[str, Any]]:
    """Scrape all places for a search query with pagination support.
    
    Args:
        playwright: Playwright instance
        query: Search query
        proxy_pool: Proxy pool for rotation
        timeout_s: Page load timeout
        concurrency: Max concurrent detail scraping (not used, kept for compatibility)
        headless: Run browser headless
        scroll_limit: Number of scrolls to load more results
        scroll_pause: Seconds between scrolls
        
    Returns:
        List of place dictionaries with: position, title, rating, website, image_url, maps_url
    """
    
    # Get search results with scrolling - returns final data directly
    places = await scrape_search_results(
        playwright,
        query,
        proxy_pool,
        timeout_s=timeout_s,
        headless=headless,
        scroll_limit=scroll_limit,
        scroll_pause=scroll_pause,
    )
    
    return places
