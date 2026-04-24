"""
Medium Reading List → Markdown Scraper

Scrapes all articles from any Medium reading list via Freedium (paywall bypass),
saves each as a clean markdown file — ready for a personal knowledge base,
Obsidian vault, or LLM Wiki source directory.

Usage:
    python scraper.py

Only new (not-yet-scraped) articles are processed on each run.
Configure via environment variables or a .env file (see .env.example).
"""

import hashlib
import json
import os
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests
from slugify import slugify

# ---------------------------------------------------------------------------
# Configuration (all overridable via environment variables)
# ---------------------------------------------------------------------------

READING_LIST_URL   = os.environ.get("READING_LIST_URL", "https://medium.com/@youruser/list/reading-list")
FREEDIUM_BASE      = os.environ.get("FREEDIUM_BASE", "https://freedium-mirror.cfd/")
STATE_FILE         = os.environ.get("STATE_FILE", "state.json")
OUTPUT_DIR         = os.environ.get("OUTPUT_DIR", "raw")
ASSETS_DIR         = os.path.join(OUTPUT_DIR, "assets")
RATE_LIMIT_SECONDS = int(os.environ.get("RATE_LIMIT_SECONDS", "2"))

# Medium article URL pattern: /<user-or-pub>/<slug>-<8-12 hex chars>
ARTICLE_URL_RE = re.compile(
    r"^https://medium\.com/[^/]+/[a-zA-Z0-9][a-zA-Z0-9-]*-[a-f0-9]{8,12}$"
)

# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def load_state() -> set:
    """Return the set of already-scraped Medium article URLs."""
    if not os.path.exists(STATE_FILE):
        return set()
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return set(data.get("scraped", []))


def save_state(scraped: set) -> None:
    """Persist the set of scraped URLs to state.json."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"scraped": sorted(scraped)}, f, indent=2)

# ---------------------------------------------------------------------------
# Reading-list discovery (JavaScript-rendered, infinite scroll)
# ---------------------------------------------------------------------------

_HREF_RE = re.compile(
    r'href="(/[^"]+/[a-zA-Z0-9][a-zA-Z0-9-]+-[a-f0-9]{8,12})(?:\?[^"]*)?\"'
)


def _collect_urls_from_html(html: str) -> set:
    """Extract Medium article URLs directly from raw HTML via regex."""
    urls = set()
    for path in _HREF_RE.findall(html):
        urls.add("https://medium.com" + path)
    return urls


def _make_scroll_action(result_holder: list):
    """
    Build a Scrapling page_action that scrolls Medium's reading list to the
    bottom. Medium virtualizes the DOM — nodes scroll out of view and are
    removed — so we harvest URLs at every scroll step, not just at the end.

    Strategy: scroll down → nudge up → nudge down → repeat until the page
    height stops growing for 6 consecutive checks.
    """
    def scroll_action(page):
        prev_height = 0
        no_change_streak = 0
        scroll_n = 0
        all_urls: set = set()

        while no_change_streak < 6:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2500)
            # Nudge up then down to re-trigger IntersectionObserver
            page.evaluate("window.scrollBy(0, -400)")
            page.wait_for_timeout(600)
            page.evaluate("window.scrollBy(0, 600)")
            page.wait_for_timeout(2000)

            new_height = page.evaluate("document.body.scrollHeight")
            scroll_n += 1

            batch = _collect_urls_from_html(page.content())
            all_urls.update(batch)

            if new_height > prev_height:
                print(f"    scroll {scroll_n}: {len(all_urls)} articles found...")
                no_change_streak = 0
            else:
                no_change_streak += 1
                print(f"    scroll {scroll_n}: no new content (streak {no_change_streak}/6), {len(all_urls)} total...")

            prev_height = new_height

        result_holder.append(all_urls)

    return scroll_action


def get_all_article_urls() -> list:
    """
    Use StealthyFetcher (Patchright — removes headless fingerprints) to load
    the Medium reading list and scroll through all articles.
    No login required.
    """
    from scrapling.fetchers import StealthyFetcher

    print(f"[*] Loading reading list: {READING_LIST_URL}")
    print("    Scrolling to collect all articles (this may take a few minutes)...")

    result_holder = []
    StealthyFetcher.fetch(
        READING_LIST_URL,
        headless=True,
        network_idle=True,
        page_action=_make_scroll_action(result_holder),
    )

    if not result_holder:
        print("  [!] Scroll action returned no URLs — falling back to initial page load.")
        page = StealthyFetcher.fetch(READING_LIST_URL, headless=True, network_idle=True)
        urls = _collect_urls_from_html(page.html_content)
    else:
        urls = result_holder[0]

    print(f"[+] Discovered {len(urls)} article URLs in the reading list.")
    return list(urls)

# ---------------------------------------------------------------------------
# Article scraper via Freedium
# ---------------------------------------------------------------------------

CONTENT_SELECTORS = [
    ".main-content",
    ".post-content",
    "article",
    ".article-content",
    "main",
]


def _extract_data(page, medium_url: str):
    """Extract title, paragraphs, and images from a Scrapling page."""
    # Title
    title_el = page.find("h1")
    title = title_el.text.strip() if title_el else None
    if not title:
        title_el = page.find("title")
        if title_el:
            title = re.sub(r"\s*[-|]\s*(Freedium|Medium).*$", "", title_el.text).strip()
    if not title:
        title = medium_url.split("/")[-1]

    # Content container
    container = None
    for sel in CONTENT_SELECTORS:
        container = page.find(sel)
        if container:
            break
    if container is None:
        container = page

    # Paragraphs
    paragraphs = []
    for p in container.css("p"):
        text = p.text.strip()
        if text:
            paragraphs.append(text)

    # Freedium sometimes wraps content in <div> blocks without <p>
    if not paragraphs:
        for div in container.css("div"):
            text = div.text.strip()
            if len(text) > 80:
                paragraphs.append(text)

    # Images
    images = []
    for img in container.css("img"):
        src = img.attrib.get("src", "").strip()
        alt = img.attrib.get("alt", "").strip()
        if src and not src.startswith("data:"):
            images.append({"src": src, "alt": alt})

    return {
        "title": title,
        "content": paragraphs,
        "images": images,
        "source_url": medium_url,
    }


def scrape_article(medium_url: str):
    """
    Fetch article via Freedium and return structured data.
    Tries plain HTTP first; falls back to headless browser if content is thin.
    """
    from scrapling.fetchers import DynamicFetcher, Fetcher

    freedium_url = FREEDIUM_BASE + medium_url
    print(f"  [>] Fetching: {freedium_url}")

    try:
        page = Fetcher.get(freedium_url, stealthy_headers=True)
        data = _extract_data(page, medium_url)
        if data and len(data["content"]) >= 3:
            return data
        print("  [!] Plain fetch returned thin content, retrying with browser...")
    except Exception as exc:
        print(f"  [!] Plain fetch failed ({exc}), retrying with browser...")

    try:
        page = DynamicFetcher.fetch(freedium_url, headless=True, network_idle=True)
        data = _extract_data(page, medium_url)
        if data:
            return data
    except Exception as exc:
        print(f"  [!] Browser fetch also failed: {exc}")

    return None

# ---------------------------------------------------------------------------
# Image downloader
# ---------------------------------------------------------------------------

def _ext_from_url_or_content_type(url: str, content_type: str) -> str:
    """Derive a file extension from URL path or Content-Type header."""
    path = urlparse(url).path
    _, ext = os.path.splitext(path)
    if ext and len(ext) <= 5:
        return ext.lower()
    ct_map = {
        "image/jpeg": ".jpg",
        "image/png":  ".png",
        "image/gif":  ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
    }
    for ct, e in ct_map.items():
        if ct in content_type:
            return e
    return ".jpg"


def download_image(url: str, assets_dir: str) -> str:
    """
    Download an image to assets_dir and return its relative path.
    Falls back to the original URL on any error.
    """
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]

    existing = list(Path(assets_dir).glob(f"{url_hash}.*"))
    if existing:
        return f"assets/{existing[0].name}"

    try:
        resp = requests.get(url, timeout=15, stream=True, headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        })
        resp.raise_for_status()
        ext = _ext_from_url_or_content_type(url, resp.headers.get("Content-Type", ""))
        filename = f"{url_hash}{ext}"
        dest = os.path.join(assets_dir, filename)
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return f"assets/{filename}"
    except Exception as exc:
        print(f"    [!] Image download failed ({exc}), using remote URL.")
        return url

# ---------------------------------------------------------------------------
# Markdown writer
# ---------------------------------------------------------------------------

def save_as_markdown(data: dict, output_dir: str, assets_dir: str) -> None:
    """Write article data to a markdown file in output_dir."""
    slug = slugify(data["title"])[:80] or "untitled"
    filepath = os.path.join(output_dir, f"{slug}.md")

    if os.path.exists(filepath):
        print(f"  [=] Already exists, skipping: {filepath}")
        return

    today = date.today().isoformat()

    lines = [
        "---",
        f"source: {data['source_url']}",
        f"date_scraped: {today}",
        "---",
        "",
        f"# {data['title']}",
        "",
    ]

    for img in data["images"]:
        alt = img.get("alt", "") or "image"
        src = img.get("local_path") or img["src"]
        lines.append(f"![{alt}]({src})")
    if data["images"]:
        lines.append("")

    for para in data["content"]:
        lines.append(para)
        lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  [+] Saved: {filepath}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    os.makedirs(ASSETS_DIR, exist_ok=True)

    scraped = load_state()
    all_urls = get_all_article_urls()

    new_urls = [u for u in all_urls if u not in scraped]
    print(
        f"\n[*] Total articles: {len(all_urls)} | "
        f"Already scraped: {len(scraped)} | "
        f"New to process: {len(new_urls)}\n"
    )

    if not new_urls:
        print("[OK] Nothing new to scrape. Run again after new articles are added to the list.")
        return

    for i, url in enumerate(new_urls, 1):
        print(f"[{i}/{len(new_urls)}] {url}")
        data = scrape_article(url)

        # Always mark processed (even on failure) to avoid infinite retries
        scraped.add(url)

        if data:
            for img in data["images"]:
                local = download_image(img["src"], ASSETS_DIR)
                img["local_path"] = local
            save_as_markdown(data, OUTPUT_DIR, ASSETS_DIR)
        else:
            print(f"  [!] Could not scrape article, skipping.")

        save_state(scraped)

        if i < len(new_urls):
            time.sleep(RATE_LIMIT_SECONDS)

    print(f"\n[DONE] Processed {len(new_urls)} new article(s).")
    print(f"       Markdown files are in: {os.path.abspath(OUTPUT_DIR)}/")


if __name__ == "__main__":
    main()
