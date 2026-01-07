import asyncio
import logging
from datetime import datetime

import httpx
from selectolax.parser import HTMLParser

from model import Post, PostMetadata, PostCrawlerSelectors
from store import write_jsonl

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
    ) -> None:
        self._selectors = selectors
        self._concurrency = concurrency
        self._timeout_s = timeout_s
        self._retries = retries

        self._headers = {
            "User-Agent": "Mozilla/5.0 (compatible; CaesarBot/1.0; +https://example.invalid)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        }

        self._sem = asyncio.Semaphore(concurrency)
        self._timeout = httpx.Timeout(timeout=timeout_s)

    async def crawl(self, post_metadatas: list[PostMetadata]) -> list[Post]:
        """
        Crawl multiple posts concurrently.
        """
        async with httpx.AsyncClient(
            headers=self._headers,
            follow_redirects=True,
            timeout=self._timeout,
        ) as client:
            tasks = [self._fetch_post(client, meta) for meta in post_metadatas]
            results = await asyncio.gather(*tasks)
            return [post for post in results if post is not None]

    async def _fetch_post(self, client: httpx.AsyncClient, metadata: PostMetadata) -> Post | None:
        """
        Fetch and parse a single post.
        """
        async with self._sem:
            for attempt in range(self._retries + 1):
                try:
                    resp = await client.get(metadata.url)
                    if not (200 <= resp.status_code < 300):
                        logger.warning(f"HTTP {resp.status_code} for {metadata.url}")
                        continue
                    
                    return self._parse_post(resp.text, metadata)
                except Exception as e:
                    logger.warning(f"Error fetching {metadata.url}: {e}")
                    if attempt < self._retries:
                        await asyncio.sleep(0.3 * (attempt + 1))
            return None

    def _parse_post(self, html: str, metadata: PostMetadata) -> Post | None:
        """
        Parse post HTML using model's factory method.
        Handles Next.js hydration by extracting content from scripts if standard DOM is empty.
        """
        tree = HTMLParser(html)
        content_node = tree.css_first(self._selectors.content_container)
        
        # Check if we have a valid node
        if not content_node:
            logger.error(f"Could not find content container for {metadata.url}")
            return None

        # Check if content is empty (common in Next.js SSR before hydration for some elements)
        # Specifically check for missing images that we expect to be there
        has_images = any(True for _ in content_node.css("img"))
        
        # If no images found, try to extract from hydration scripts
        if not has_images:
            logger.info("No images found in DOM, attempting to extract from hydration scripts...")
            try:
                hydrated_html = self._extract_hydrated_content(tree)
                if hydrated_html:
                    logger.info("Successfully extracted hydrated content")
                    # Create a new parser for the hydrated content
                    # We wrap it in a div with the expected ID to match the selector logic if needed,
                    # or just pass the root of this new tree.
                    # Since parse_dom_node expects a node, we parse the fragment.
                    hydrated_tree = HTMLParser(f'<div id="article-content-inner">{hydrated_html}</div>')
                    content_node = hydrated_tree.body.child
            except Exception as e:
                logger.warning(f"Failed to extract hydration data: {e}")

        return Post.parse_dom_node(content_node, metadata)

    def _extract_hydrated_content(self, tree: HTMLParser) -> str | None:
        """
        Extracts HTML content strings from Next.js self.__next_f.push calls.
        """
        # Collect all fragments that look like article content
        fragments = []
        for script in tree.css("script"):
            text = script.text()
            if not text or "self.__next_f.push" not in text:
                continue
            
            # Simple string parsing to avoid full JS parsing
            # Look for HTML-like strings inside the push array: [1, "...<p>..."]
            # We specifically look for the structure matching the article content
            # The pattern seen is: self.__next_f.push([1,"..."])
            # We want the second element if it's a string containing HTML tags
            
            # Basic extraction: find the string literal inside the array
            # This is a heuristic. A proper JSON/JS parser would be safer but heavier.
            # We look for the pattern: , " ... " ] or , " ... " )
            
            start_marker = 'self.__next_f.push([1,"'
            if start_marker in text:
                # Extract the content string
                start_idx = text.find(start_marker) + len(start_marker)
                # Find the end of the string. This is tricky due to escaping.
                # But typically it ends with "])
                
                # Let's try to just grab the content if it looks like the article
                # Optimization: check if it contains common tags we expect in the article
                if "<p" in text or "<span" in text:
                     # Python's string processing to unescape the JS string would be needed
                     # For now, let's try a simpler approach assuming the format is relatively clean
                     # or use a regex to find the string payload
                     import re
                     # Match the string inside the array: [1, "CONTENT"]
                     match = re.search(r'self\.__next_f\.push\(\[1,"(.*)"\]\)', text, re.DOTALL)
                     if match:
                         # Unescape the JS string
                         content = match.group(1).encode('utf-8').decode('unicode_escape')
                         # Next.js might double escape or use specific formatting
                         # But 'unicode_escape' handles \uXXXX commonly found
                         fragments.append(content)

        if not fragments:
            return None
            
        # Filter fragments to identifying likely article content (HTML) vs JSON data
        # Check for common tags found in the article body
        html_fragments = []
        for frag in fragments:
            if "<p" in frag or "<div" in frag or "<span" in frag or "<br" in frag:
                html_fragments.append(frag)
        
        if not html_fragments:
            logger.warning("Found hydration data but no HTML-like content")
            return None

        # Join all HTML fragments as they might be split
        # Sort by length descending just to be safe if we want to prioritize? 
        # Actually Next.js might push them in specific order, but usually independent chunks.
        # Joining them all is safer than picking one if they split the article.
        # But if they are duplicates (e.g. one for desktop, one for mobile? unlikely), joining might duplicate.
        # In the log we saw 29519 and 29204 bytes. They might be very similar.
        # Let's try to just take the longest HTML fragment for now, as duplication is worse.
        # If we miss content, we can revisit joining strategies.
        full_content = max(html_fragments, key=len)
        logger.info(f"Selected hydrated fragment of length {len(full_content)}")
        logger.info(f"Fragment snippet: {full_content[:200]}")
        return full_content

async def main():
    # Initial post URLs provided by user
    urls = [
        "https://workatravel.pixnet.net/blog/posts/5063201814",
        "https://workatravel.pixnet.net/blog/posts/5071682496"
    ]

    # Create dummy metadata for testing (since we don't have titles/dates from page crawler yet)
    # In a real scenario, these would come from PageCrawler
    metadatas = [
        PostMetadata(url=url, title=f"Test Post {i}", published_at=datetime.now())
        for i, url in enumerate(urls)
    ]

    crawler = PostCrawler(
        selectors=PostCrawlerSelectors(
            content_container="#article-content-inner"  # Typical Pixnet content selector
        ),
        concurrency=10
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
