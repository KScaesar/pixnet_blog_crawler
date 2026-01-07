import asyncio
import logging
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import httpx
from selectolax.parser import HTMLParser

import dom
from model import PostMetadata, PageCrawlerSelectors
from store import write_jsonl

logger = logging.getLogger(__name__)


class PageCrawler:
    """
    Crawls paginated blog pages and extracts post metadata from each page.
    """

    def __init__(
        self,
        *,
        base_url: str,  # 基礎 URL，例如 "https://example.com/blog"
        selectors: "PageCrawlerSelectors",  # CSS 選擇器配置
        start_page: int = 1,  # 起始頁碼（包含）
        end_page: int,  # 結束頁碼（包含）
        concurrency: int = 5,  # 並發請求數量
        timeout_s: float = 15.0,  # 請求超時時間（秒）
        retries: int = 2,  # 失敗重試次數
    ) -> None:
        """
        Args:
            base_url: Base URL with page parameter (e.g., "https://example.com/blog")
            selectors: CSS selectors for extracting post metadata from each page
            start_page: Starting page number (inclusive, default: 1)
            end_page: Ending page number (inclusive)
            concurrency: Number of concurrent page requests
            timeout_s: Request timeout in seconds
            retries: Number of retries for failed requests
        """
        self._base_url = base_url
        self._selectors = selectors
        self._start_page = start_page
        self._end_page = end_page
        self._concurrency = concurrency
        self._timeout_s = timeout_s
        self._retries = retries

        self._headers = {
            "User-Agent": "Mozilla/5.0 (compatible; CaesarBot/1.0; +https://example.invalid)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        }

        self._sem = asyncio.Semaphore(concurrency)

        self._timeout = httpx.Timeout(
            timeout=timeout_s,
            connect=min(5.0, timeout_s),
            read=timeout_s,
            write=timeout_s,
            pool=timeout_s,
        )

        self._limits = httpx.Limits(
            max_connections=max(20, concurrency * 2),
            max_keepalive_connections=max(10, concurrency),
            keepalive_expiry=30.0,
        )

    async def crawl(self) -> list[PostMetadata]:
        """
        Crawl pages in the specified range and extract post metadata.
        Pages are fetched concurrently up to the concurrency limit.

        Returns:
            Sorted list of PostMetadata (by published_at desc, with index from 1 to N)
        """

        async with httpx.AsyncClient(
            headers=self._headers,
            follow_redirects=True,
            timeout=self._timeout,
            limits=self._limits,
        ) as client:
            # Create tasks for all pages
            tasks = [self._fetch_page(client, self._build_page_url(page_num)) for page_num in range(self._start_page, self._end_page + 1)]

            # Execute all tasks concurrently
            results = await asyncio.gather(*tasks)

            # Flatten results into a single list
            all_posts: list[PostMetadata] = []
            for posts in results:
                all_posts.extend(posts)

        # Sort and reindex before returning
        return self._sort_and_reindex(all_posts)

    def _build_page_url(self, page_num: int) -> str:
        """Build URL for a specific page number."""
        parsed = urlparse(self._base_url)
        query_params = parse_qs(parsed.query)
        query_params["page"] = [str(page_num)]

        new_query = urlencode(query_params, doseq=True)
        new_parsed = parsed._replace(query=new_query)

        return urlunparse(new_parsed)

    async def _fetch_page(self, client: httpx.AsyncClient, url: str) -> list[PostMetadata]:
        """
        Fetch a single page and extract all post metadata.

        Args:
            client: HTTP client
            url: Page URL

        Returns:
            List of PostMetadata from this page (all with index=0)
        """
        async with self._sem:
            for attempt in range(self._retries + 1):
                try:
                    resp = await client.get(url)

                    if not (200 <= resp.status_code < 300):
                        logger.warning(f"HTTP {resp.status_code} for {url} (attempt {attempt + 1}/{self._retries + 1})")
                        if attempt < self._retries:
                            await asyncio.sleep(0.3 * (attempt + 1))
                            continue
                        logger.error(f"Failed to fetch {url} after {self._retries + 1} attempts: HTTP {resp.status_code}")
                        return []

                    return self._extract_posts_from_page(resp.text)

                except (
                    httpx.TimeoutException,
                    httpx.NetworkError,
                    httpx.RemoteProtocolError,
                ) as e:
                    logger.warning(f"{type(e).__name__} for {url} (attempt {attempt + 1}/{self._retries + 1}): {e}")
                    if attempt < self._retries:
                        await asyncio.sleep(0.3 * (attempt + 1))
                        continue
                    logger.error(f"Failed to fetch {url} after {self._retries + 1} attempts: {type(e).__name__}")
                    return []

                except Exception as e:
                    logger.exception(f"Unexpected error fetching {url} (attempt {attempt + 1}/{self._retries + 1}): {e}")
                    return []

        return []

    def _extract_posts_from_page(self, html: str) -> list[PostMetadata]:
        """
        Extract all post metadata from a page's HTML.

        Args:
            html: Page HTML content
            page_url: URL of the page (for resolving relative URLs)

        Returns:
            List of PostMetadata (all with index=0)
        """
        tree = HTMLParser(html)
        posts: list[PostMetadata] = []

        # Extract post containers
        post_nodes = tree.css(self._selectors.post_container)

        for node in post_nodes:
            title = dom.extract_text(node, self._selectors.title)
            published_at = dom.extract_datetime(node, self._selectors.published_at)
            url = dom.extract_url(node, self._selectors.post_url)

            # Only add if we have all required fields (non-empty)
            if url and title and published_at:
                posts.append(
                    PostMetadata(
                        url=url,
                        title=title,
                        published_at=published_at,
                    )
                )

        return posts

    @staticmethod
    def _sort_and_reindex(posts: list[PostMetadata]) -> list[PostMetadata]:
        """
        Sort posts by published_at (descending, newest first) and reassign index from 1.
        """
        sorted_posts = sorted(posts, key=lambda p: p.published_at, reverse=True)
        for i, post in enumerate(sorted_posts):
            sorted_posts[len(sorted_posts) - i - 1].idx = i + 1
        return sorted_posts


# Example usage:
async def main():
    crawler = PageCrawler(
        base_url="https://workatravel.pixnet.net/blog",
        selectors=PageCrawlerSelectors(
            post_container="div.article",
            title=".article h2 a",
            published_at=".article li.publish",
            post_url=".article h2 a",
        ),
        start_page=1,
        end_page=163,
        concurrency=5,
    )

    posts = await crawler.crawl()
    write_jsonl(posts, "posts.json")
    print(f"\nTotal posts: {len(posts)}")


if __name__ == "__main__":
    asyncio.run(main())
