# Google Maps Scraper

Google Maps scraper built with Playwright for reliable JavaScript-rendered extraction of business listings, with CSV/config batch input, proxy support, pagination via scrolling, and one-query-per-file JSON output.

## Features

- **Full JavaScript Rendering** - Uses real browser (Playwright/Chromium) to handle dynamic content
- **Multiple Input Methods** - Single query, CSV batch, config file, or interactive mode
- **Pagination Support** - Scroll to load more results (not just first 8-10)
- **Proxy Support** - Works with SOAX and any HTTP/HTTPS proxies
- **One Query = One File** - Each search query outputs a separate JSON file
- **Extracts**: Title, rating, image URL, and Maps link

## Installation

```bash
# Clone the repository
git clone https://github.com/romankoltsov1/Google-Maps-Scraper.git
cd google-maps-scraper

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browser
python3 -m playwright install chromium
```

## Quick Start

### Interactive Mode
```bash
python3 scraper.py
```
Type queries one by one, press Enter twice when done.

### Single Query
```bash
python3 scraper.py "coffee shops in porto"
```
Output: `output/coffee-shops-in-porto.json`

### Get More Results (Pagination)
```bash
# Get ~40-60 results by scrolling (default: 10 scrolls)
python3 scraper.py "restaurants in NYC" --scroll-limit 20

# Faster scrolling with shorter pause
python3 scraper.py "hotels in Paris" --scroll-limit 15 --scroll-pause 1
```

### Batch from CSV
```bash
python3 scraper.py --csv queries.csv
```

### With Proxies
```bash
python3 scraper.py --csv queries.csv --proxies proxies.txt
```

## Output Format

Each query creates one JSON file:

```json
{
  "query": "coffee porto",
  "count": 18,
  "results": [
    {
      "position": 1,
      "title": "Baco Coffee Lab",
      "rating": 4.8,
      "website": null,
      "image_url": "https://lh3.googleusercontent.com/p/AF1Qip...",
      "maps_url": "https://www.google.com/maps/place/..."
    }
  ]
}
```

### Output Fields

| Field | Description |
|-------|-------------|
| `position` | Ranking position (1, 2, 3...) |
| `title` | Business name |
| `rating` | Star rating (e.g., 4.5) or null |
| `website` | Website URL (usually null in search results) |
| `image_url` | Thumbnail image from Google Maps |
| `maps_url` | Direct link to Google Maps place page |

**Note:** Fields like `address`, `phone`, `hours`, and `review text` are not available in search results. Use the `maps_url` to visit the detail page for complete information.

## Proxy Configuration

### SOAX Proxies (Recommended)

The scraper has built-in support for SOAX sticky session proxies. Format:
```
proxy.soax.com:5000 package-12345-country-us-sessionid-abc-sessionlength-90:YOUR_PASSWORD
proxy.soax.com:5000 package-12345-country-uk-sessionid-def-sessionlength-180:YOUR_PASSWORD
```

Features:
- Automatic sticky session rotation
- Session ID generation
- Country targeting support

### Other Proxy Providers

Works with any HTTP/HTTPS proxy provider:
```
http://username:password@host:port
username:password@host:port
host:port username:password
```

Create `proxies.txt` and run:
```bash
python3 scraper.py --csv queries.csv --proxies proxies.txt
```

**Test proxies before scraping:**
```bash
python3 scraper.py --proxies proxies.txt --test-proxies
```

## Input Formats

### 1. CSV File
```csv
query
restaurants in Tokyo
coffee shops in Berlin
hotels in Paris
```

### 2. Config File (YAML)
```yaml
# config.yaml
queries:
  - coffee shops in New York
  - restaurants in London

proxies: proxies.txt
output_dir: ./results
scroll_limit: 15
scroll_pause: 2.0
```

### 3. Config File (JSON)
```json
{
  "queries": ["pizza rome", "sushi tokyo"],
  "proxies": "proxies.txt",
  "output_dir": "./output",
  "scroll_limit": 10
}
```

## Command Line Options

```
usage: scraper.py [OPTIONS] [QUERY]

Options:
  --csv FILE            CSV file with queries
  --config FILE         Config file (JSON or YAML)
  --proxies FILE        Proxy list file
  --test-proxies        Test proxy connections without scraping
  --output-dir DIR      Output directory (default: ./output)
  --concurrency N       Concurrent browsers (default: 5)
  --timeout SECONDS     Page load timeout (default: 60)
  --scroll-limit N      Number of scrolls to load more results (default: 10)
  --scroll-pause SEC    Seconds between scrolls (default: 2.0)
  --visible             Show browser window (for debugging)
  -h, --help            Show help message
```

## Pagination Guide

Google Maps loads ~8-10 results initially. Use scroll options to get more:

| Scroll Limit | Typical Results | Time |
|--------------|-----------------|------|
| 0 | 8-10 | ~10s |
| 5 | 25-35 | ~20s |
| 10 | 45-60 | ~35s |
| 20 | 80-120 | ~60s |

```bash
# Quick scan (10 results)
python3 scraper.py "coffee shops" --scroll-limit 0

# Standard (40-60 results)
python3 scraper.py "restaurants" --scroll-limit 10

# Deep scan (100+ results)
python3 scraper.py "hotels" --scroll-limit 25 --scroll-pause 1.5
```

## Performance

Browser-based scraping provides reliability at the cost of speed:

| Setup | Speed | Results/Query |
|-------|-------|---------------|
| No scroll | ~5-10s | 8-10 |
| 10 scrolls | ~30-40s | 40-60 |
| 20 scrolls | ~60-90s | 80-120 |

**Scaling Tips:**
- Use proxies to avoid rate limiting
- Lower concurrency to reduce memory (each browser uses ~100MB)
- Run multiple instances on different servers

```bash
# Server 1
python3 scraper.py --csv batch1.csv --proxies proxies1.txt --scroll-limit 10

# Server 2
python3 scraper.py --csv batch2.csv --proxies proxies2.txt --scroll-limit 10
```

## Limitations

From **search results page**, we can extract:
- ✅ Business name
- ✅ Rating (stars)
- ✅ Thumbnail image
- ✅ Maps URL

Cannot extract from search results (requires visiting detail page):
- ❌ Full address
- ❌ Phone number
- ❌ Opening hours
- ❌ Website (rarely shown in list view)
- ❌ Reviews/text content
- ❌ Price range ($, $$, $$$)

**Workaround:** Use the `maps_url` field to visit individual place pages.

## Troubleshooting

### No results found
- Increase timeout: `--timeout 90`
- Try visible mode: `--visible`
- Check if Google changed their layout

### Slow performance
- Reduce scroll limit: `--scroll-limit 5`
- Use faster proxies
- Check network connection

### Browser errors
```bash
# Reinstall browser
python3 -m playwright install chromium --force

# Update Playwright
pip install --upgrade playwright
python3 -m playwright install chromium
```

### Proxy errors

**Test proxies first:**
```bash
python3 scraper.py --proxies proxies.txt --test-proxies
```

**SOAX Proxy Setup:**

SOAX uses HTTP proxies. Format in `proxies.txt`:
```
# Format 1 (recommended)
proxy.soax.com:5000 package-329562-country-at:PASSWORD

# Format 2 (URL style)
http://package-329562-country-at:PASSWORD@proxy.soax.com:5000
```

**Important:** The scraper automatically:
- Uses HTTP proxy mode (even for HTTPS sites)
- Disables HTTP/2 and QUIC (these cause issues with many proxies)
- This ensures compatibility with SOAX and most residential proxies

**Common errors:**

1. **ERR_TUNNEL_CONNECTION_FAILED / Timeout**
   - The scraper now automatically disables HTTP/2 and QUIC for proxy compatibility
   - If you still get timeouts, the proxy may be blocked by Google
   - Try a different proxy IP or country
   - Increase timeout: `--timeout 90`

2. **ERR_PROXY_CONNECTION_FAILED**
   - Cannot connect to proxy server
   - Check proxy host and port

3. **Test with curl first:**
   ```bash
   curl -x "http://package-329562-country-at:PASSWORD@proxy.soax.com:5000" \
        https://www.google.com
   ```
   If curl works but scraper doesn't, check the proxy format in `proxies.txt`.

**Working without proxies:**
If proxies fail, you can still scrape without them:
```bash
python3 scraper.py "coffee shops" --scroll-limit 5
```

## Advanced Usage

### Debug Mode (Visible Browser)
```bash
python3 scraper.py "test query" --visible --timeout 30 --scroll-limit 2
```

### Custom Concurrency
```bash
# Single browser (slowest, most reliable)
python3 scraper.py --csv queries.csv --concurrency 1

# High concurrency (faster, more memory)
python3 scraper.py --csv queries.csv --concurrency 10
```

## Requirements

- Python 3.10+
- Playwright 1.40+
- Chromium browser (auto-installed)

## Legal Notice

- This tool is for educational and research purposes
- Respect Google's Terms of Service
- Use responsibly with appropriate rate limiting
- Consider official Google Places API for production use
- Check legal requirements in your jurisdiction

## License

MIT License - See LICENSE file for details
