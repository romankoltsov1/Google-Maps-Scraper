#!/usr/bin/env python3
"""
Google Maps Scraper

A reliable Google Maps scraper built with Playwright browser automation.

Usage:
  1. Interactive:     python3 scraper.py
  2. Single query:    python3 scraper.py "coffee shops in nyc"
  3. From CSV:        python3 scraper.py --csv queries.csv
  4. From config:     python3 scraper.py --config config.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from maps_scraper import (
    ProxyPool,
    load_proxies,
    scrape_query,
    test_proxy,
)


def sanitize_filename(text: str, max_len: int = 50) -> str:
    """Convert query to safe filename."""
    safe = re.sub(r'[^\w\s-]', '', text.lower())
    safe = re.sub(r'[-\s]+', '-', safe).strip('-')
    return safe[:max_len]


def load_queries_from_csv(path: Path) -> list[dict[str, str]]:
    """Load queries from CSV file."""
    queries = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if 'query' in row:
                queries.append(row)
    return queries


def load_config(path: Path) -> dict[str, Any]:
    """Load configuration from YAML or JSON file."""
    text = path.read_text(encoding='utf-8')
    
    if path.suffix in ('.yaml', '.yml'):
        try:
            import yaml
            return yaml.safe_load(text)
        except ImportError:
            print("PyYAML required for YAML config. Install: pip install pyyaml", file=sys.stderr)
            sys.exit(1)
    else:
        return json.loads(text)


def interactive_mode() -> list[str]:
    """Interactive prompt for queries."""
    print("=" * 60)
    print("Google Maps Scraper - Interactive Mode")
    print("=" * 60)
    print()
    
    queries = []
    print("Enter your search queries (one per line).")
    print("Press Enter twice when done.")
    print("-" * 60)
    
    while True:
        query = input(f"Query {len(queries) + 1}: ").strip()
        if not query:
            break
        queries.append(query)
    
    if not queries:
        print("No queries entered. Exiting.")
        sys.exit(0)
    
    print(f"\n{len(queries)} query(s) to process.")
    return queries


def get_output_path(query: str, output_dir: Path, index: int | None = None) -> Path:
    """Generate output file path for a query."""
    safe_name = sanitize_filename(query)
    if index is not None:
        filename = f"{index:03d}_{safe_name}.json"
    else:
        filename = f"{safe_name}.json"
    return output_dir / filename


def parse_concurrency(raw: str) -> int | None:
    """Parse concurrency string to integer or None for infinite."""
    val = raw.strip().lower()
    if val in {"inf", "infinite", "unlimited", "0", "none", "null"}:
        return None
    n = int(val)
    if n < 1:
        raise ValueError("concurrency must be >= 1, or use inf/infinite/unlimited")
    return n


async def run_simple(
    queries: list[str],
    proxies_file: Path | None = None,
    output_dir: Path = Path("output"),
    concurrency: str = "5",
    timeout: float = 60.0,
    headless: bool = True,
    scroll_limit: int = 10,
    scroll_pause: float = 2.0,
) -> None:
    """Run scraper with simplified interface."""
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load proxies
    proxies = load_proxies(proxies_file)
    proxy_pool = ProxyPool(proxies=proxies, session_length=90)
    
    if proxy_pool.enabled:
        print(f"✓ Loaded {proxy_pool.size} proxies")
    else:
        print("⚠ No proxies loaded - using direct connection")
    
    concurrency_val = parse_concurrency(concurrency)
    print(f"✓ Concurrency: {'unlimited' if concurrency_val is None else concurrency_val}")
    print(f"✓ Scroll limit: {scroll_limit}")
    print(f"✓ Output directory: {output_dir.absolute()}")
    print(f"✓ Browser mode: {'headless' if headless else 'visible'}")
    print()
    
    async with async_playwright() as playwright:
        for i, query in enumerate(queries, 1):
            output_path = get_output_path(query, output_dir, i if len(queries) > 1 else None)
            
            print(f"[{i}/{len(queries)}] Searching: \"{query}\"")
            
            try:
                results = await scrape_query(
                    playwright=playwright,
                    query=query,
                    proxy_pool=proxy_pool,
                    timeout_s=timeout,
                    concurrency=concurrency_val,
                    headless=headless,
                    scroll_limit=scroll_limit,
                    scroll_pause=scroll_pause,
                )
                
                # Save to individual JSON file
                output_data = {
                    "query": query,
                    "count": len(results),
                    "results": results,
                }
                
                output_path.write_text(
                    json.dumps(output_data, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                
                print(f"    ✓ Found {len(results)} results → {output_path}")
                
            except Exception as e:
                print(f"    ✗ Error: {e}")
    
    print()
    print(f"✓ Done! Results saved to: {output_dir.absolute()}")


def main() -> int:
    """Main entry point with simple interface."""
    parser = argparse.ArgumentParser(
        description="Google Maps Scraper - Extract business listings from Google Maps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Interactive mode:       python3 scraper.py
  Single query:           python3 scraper.py "coffee shops in NYC"
  More results:           python3 scraper.py "coffee shops" --scroll-limit 20
  Faster scroll:          python3 scraper.py "restaurants" --scroll-limit 15 --scroll-pause 1
  With visible browser:   python3 scraper.py "coffee shops" --visible
  CSV file:               python3 scraper.py --csv queries.csv
  Config file:            python3 scraper.py --config config.yaml
  With proxies:           python3 scraper.py --csv queries.csv --proxies proxies.txt
  Test proxies:           python3 scraper.py --proxies proxies.txt --test-proxies
        """
    )
    
    parser.add_argument(
        "query",
        nargs="?",
        help="Search query (e.g., 'restaurants in London')"
    )
    parser.add_argument(
        "--csv",
        type=Path,
        metavar="FILE",
        help="CSV file with queries (column: 'query')"
    )
    parser.add_argument(
        "--config",
        type=Path,
        metavar="FILE",
        help="Config file (JSON or YAML)"
    )
    parser.add_argument(
        "--proxies",
        type=Path,
        metavar="FILE",
        help="Proxy file (SOAX format supported)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        metavar="DIR",
        help="Output directory (default: ./output)"
    )
    parser.add_argument(
        "--concurrency",
        default="5",
        help="Concurrency: 1..N (default: 5, browser-based)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Request timeout in seconds (default: 60)"
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Show browser window (for debugging)"
    )
    parser.add_argument(
        "--scroll-limit",
        type=int,
        default=10,
        metavar="N",
        help="Number of scrolls to load more results (default: 10, 0 = no scroll)"
    )
    parser.add_argument(
        "--scroll-pause",
        type=float,
        default=2.0,
        metavar="SECONDS",
        help="Seconds to wait between scrolls (default: 2.0)"
    )
    parser.add_argument(
        "--test-proxies",
        action="store_true",
        help="Test proxy connections without scraping"
    )
    
    args = parser.parse_args()
    
    # Test proxies if requested (do this first before interactive mode)
    if args.test_proxies:
        if not args.proxies:
            print("Error: --test-proxies requires --proxies FILE", file=sys.stderr)
            return 1
        
        print("Testing proxies...")
        print("-" * 50)
        
        proxies = load_proxies(args.proxies)
        if not proxies:
            print("No proxies found in file.", file=sys.stderr)
            return 1
        
        async def run_tests():
            async with async_playwright() as playwright:
                for i, proxy in enumerate(proxies, 1):
                    proxy_url = proxy.build_url()
                    print(f"\n[{i}/{len(proxies)}] Testing: {proxy.host}:{proxy.port}")
                    success, message = await test_proxy(playwright, proxy_url)
                    status = "✓" if success else "✗"
                    print(f"    {status} {message}")
        
        asyncio.run(run_tests())
        print("\n" + "-" * 50)
        print("Proxy testing complete.")
        return 0
    
    # Determine input source
    queries: list[str] = []
    proxies_file = args.proxies
    output_dir = args.output_dir
    
    # Scroll settings (can be overridden by config)
    scroll_limit = args.scroll_limit
    scroll_pause = args.scroll_pause
    
    if args.config:
        # Config file mode
        config = load_config(args.config)
        queries = config.get("queries", [])
        if not queries and config.get("query"):
            queries = [config["query"]]
        proxies_file = Path(config["proxies"]) if config.get("proxies") else proxies_file
        output_dir = Path(config.get("output_dir", output_dir))
        scroll_limit = config.get("scroll_limit", scroll_limit)
        scroll_pause = config.get("scroll_pause", scroll_pause)
        
    elif args.csv:
        # CSV mode
        rows = load_queries_from_csv(args.csv)
        queries = [r["query"] for r in rows]
        
    elif args.query:
        # Single query mode
        queries = [args.query]
        
    else:
        # Interactive mode
        queries = interactive_mode()
    
    if not queries:
        print("No queries to process.", file=sys.stderr)
        return 1
    
    # Run scraper
    try:
        asyncio.run(run_simple(
            queries=queries,
            proxies_file=proxies_file,
            output_dir=output_dir,
            concurrency=args.concurrency,
            timeout=args.timeout,
            headless=not args.visible,
            scroll_limit=scroll_limit,
            scroll_pause=scroll_pause,
        ))
        return 0
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
