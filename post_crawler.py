import asyncio
import logging
from datetime import datetime

import httpx
from playwright.async_api import async_playwright
from selectolax.parser import HTMLParser

from model import Post, PostCrawlerSelectors, PostMetadata

logger = logging.getLogger(__name__)


class PostCrawler:
    """
    Crawls individual blog posts and extracts detailed content.
    """

    def __init__(
        self,
        *,
        selectors: PostCrawlerSelectors,
        concurrency: int = 5,
        timeout_s: float = 15.0,
        retries: int = 2,
        use_playwright: bool = True,
    ) -> None:
        self._selectors = selectors
        self._concurrency = concurrency
        self._timeout_s = timeout_s
        self._retries = retries
        self._use_playwright = use_playwright

        self._headers = {
            "User-Agent": "Mozilla/5.0 (compatible; CaesarBot/1.0; +https://example.invalid)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        }

        self._sem = asyncio.Semaphore(concurrency)
        self._timeout = httpx.Timeout(timeout=timeout_s)

    async def crawl(self, post_metadata_many: list[PostMetadata]) -> list[Post]:
        """
        Crawl multiple posts concurrently.
        """
        async with httpx.AsyncClient(
            headers=self._headers,
            follow_redirects=True,
            timeout=self._timeout,
        ) as client:
            tasks = [self._fetch_post(client, meta) for meta in post_metadata_many]
            results = await asyncio.gather(*tasks)
            return [post for post in results if post is not None]

    async def _fetch_post(self, client: httpx.AsyncClient, metadata: PostMetadata) -> Post | None:
        """
        Fetch and parse a single post.
        """
        async with self._sem:
            for attempt in range(self._retries + 1):
                try:
                    html = None

                    if self._use_playwright:
                        html = await self._render_with_playwright(metadata.url)

                    if html is None:
                        resp = await client.get(metadata.url)
                        if not (200 <= resp.status_code < 300):
                            logger.warning(f"HTTP {resp.status_code} for {metadata.url}")
                            continue
                        html = resp.text

                    return self._parse_post(html, metadata)
                except Exception as e:
                    logger.warning(f"Error fetching {metadata.url}: {e}")
                    if attempt < self._retries:
                        await asyncio.sleep(0.3 * (attempt + 1))
            return None

    async def _render_with_playwright(self, url: str) -> str | None:
        """
        Render the page with Playwright to capture JS-injected content (e.g., images).
        """
        goto_timeout_ms = int(max(self._timeout_s * 1000, 25000))
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                try:
                    await page.goto(url, wait_until="networkidle", timeout=goto_timeout_ms)
                except Exception:
                    # Fallback for slow pages/CDN: relax to DOMContentLoaded with a bit more time.
                    await page.goto(url, wait_until="domcontentloaded", timeout=goto_timeout_ms)
                try:
                    await page.wait_for_selector(f"{self._selectors.content_container}", timeout=5000)
                    await page.wait_for_selector(f"{self._selectors.content_container} img", timeout=5000)
                except Exception:
                    # It's fine if images are not immediately present; we still capture the DOM.
                    pass
                await page.wait_for_timeout(500)
                html = await page.content()
                await browser.close()
                return html
        except Exception as e:
            logger.warning(f"Playwright render failed for {url}: {e}")
            return None

    def _parse_post(self, html: str, metadata: PostMetadata) -> Post | None:
        """
        Parse post HTML using model's factory method.
        """
        tree = HTMLParser(html)
        content_node = tree.css_first(self._selectors.content_container)

        if not content_node:
            logger.error(f"Could not find content container for {metadata.url}")
            return None

        return Post.parse_dom_node(content_node, metadata)


async def main():
    # Initial post URLs provided by user
    urls = ["https://workatravel.pixnet.net/blog/posts/5063201814", "https://workatravel.pixnet.net/blog/posts/5071682496"]

    # Create dummy metadata for testing (since we don't have titles/dates from page crawler yet)
    # In a real scenario, these would come from PageCrawler
    metadatas = [PostMetadata(url=url, title=f"Test Post {i}", published_at=datetime.now()) for i, url in enumerate(urls)]

    crawler = PostCrawler(
        selectors=PostCrawlerSelectors(
            content_container="#article-content-inner"  # Typical Pixnet content selector
        ),
        concurrency=10,
    )

    posts = await crawler.crawl(metadatas)

    if posts:
        # write_jsonl(posts, "posts_detail.jsonl")
        print(f"Successfully crawled {len(posts)} posts\n")
        for post in posts:
            print(post)
            print("=" * 80)  # Extra newline between posts
    else:
        print("No posts were crawled.")


if __name__ == "__main__":
    asyncio.run(main())
