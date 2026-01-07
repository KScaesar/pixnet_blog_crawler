import asyncio
import time
from typing import Callable

import httpx
from selectolax.parser import HTMLParser

from model import PostMetadata, PostMetadataResult, PostMetadataSelectors


def _should_retry_status(code: int) -> bool:
    return code in {429, 500, 502, 503, 504}


class PostMetadataExtractor:
    """
    httpx + selectolax batch post extractor.

    Primary workflow:
      await PostMetadataExtractor(...).execute(urls)
    """

    def __init__(
        self,
        *,
        selectors: PostMetadataSelectors,
        concurrency: int = 10,
        timeout_s: float = 15.0,
        retries: int = 2,
        follow_redirects: bool = True,
        retry_backoff_s: Callable[[int], float] | None = None,
    ) -> None:
        if concurrency <= 0:
            raise ValueError("concurrency must be > 0")
        if retries < 0:
            raise ValueError("retries must be >= 0")

        self._selectors = selectors
        self._concurrency = concurrency
        self._timeout_s = timeout_s
        self._retries = retries
        self._follow_redirects = follow_redirects

        self._headers = {
            "User-Agent": "Mozilla/5.0 (compatible; CaesarBot/1.0; +https://example.invalid)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        }

        self._retry_backoff_s = retry_backoff_s or (lambda attempt: 0.3 * (attempt + 1))

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

    async def execute(self, urls: list[str]) -> list[PostMetadataResult]:
        """
        Main workflow:
        - concurrently fetch urls
        - parse HTML with selectolax
        - return per-url results (success/failure)
        """
        async with httpx.AsyncClient(
            headers=self._headers,
            follow_redirects=self._follow_redirects,
            timeout=self._timeout,
            limits=self._limits,
        ) as client:
            tasks = [
                self._fetch_and_extract(client, i, url) for i, url in enumerate(urls)
            ]
            return await asyncio.gather(*tasks)

    async def _fetch_and_extract(
        self, client: httpx.AsyncClient, index: int, url: str
    ) -> PostMetadataResult:
        async with self._sem:
            t0 = time.perf_counter()
            last_status: int | None = None
            last_error: str | None = None
            final_url: str | None = None

            for attempt in range(self._retries + 1):
                try:
                    resp = await client.get(url)
                    last_status = resp.status_code
                    final_url = str(resp.url)

                    if not (200 <= resp.status_code < 300):
                        last_error = f"HTTPStatusError: {resp.status_code}"
                        if attempt < self._retries and _should_retry_status(
                            resp.status_code
                        ):
                            await asyncio.sleep(self._retry_backoff_s(attempt))
                            continue
                        return self._fail(url, last_status, last_error, final_url, t0)

                    post = self._extract_post(index=index, url=url, html=resp.text)
                    return self._ok(url, post, resp.status_code, final_url, t0)

                except (
                    httpx.TimeoutException,
                    httpx.NetworkError,
                    httpx.RemoteProtocolError,
                ) as e:
                    last_error = f"{type(e).__name__}: {e}"
                    if attempt < self._retries:
                        await asyncio.sleep(self._retry_backoff_s(attempt))
                        continue
                    return self._fail(url, last_status, last_error, final_url, t0)

                except httpx.RequestError as e:
                    # e.g. invalid URL
                    last_error = f"{type(e).__name__}: {e}"
                    return self._fail(url, last_status, last_error, final_url, t0)

                except Exception as e:
                    last_error = f"UnexpectedError: {type(e).__name__}: {e}"
                    return self._fail(url, last_status, last_error, final_url, t0)

            return self._fail(
                url, last_status, last_error or "UnknownError", final_url, t0
            )

    def _extract_post(self, *, index: int, url: str, html: str) -> PostMetadata:
        tree = HTMLParser(html)
        s = self._selectors

        title = self._first_text(tree, s.title)
        published_at = self._published_at(tree, s.published_at)

        return PostMetadata(
            index=index,
            published_at=published_at,
            title=title,
            url=url,
        )

    @staticmethod
    def _first_text(tree: HTMLParser, selector: str) -> str | None:
        node = tree.css_first(selector)
        if node is None:
            return None
        text = node.text(strip=True)
        return text or None

    @staticmethod
    def _published_at(tree: HTMLParser, selector: str) -> str | None:
        node = tree.css_first(selector)
        if node is None:
            return None
        dt = node.attributes.get("datetime")
        if dt:
            return dt
        content = node.attributes.get("content")
        if content:
            return content
        text = node.text(strip=True)
        return text or None

    @staticmethod
    def _ok(
        url: str, post: PostMetadata, status: int, final_url: str | None, t0: float
    ) -> PostMetadataResult:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return PostMetadataResult(
            url=url,
            post=post,
            ok=True,
            status_code=status,
            error=None,
            final_url=final_url,
            elapsed_ms=elapsed_ms,
        )

    @staticmethod
    def _fail(
        url: str,
        status: int | None,
        error: str,
        final_url: str | None,
        t0: float,
    ) -> PostMetadataResult:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return PostMetadataResult(
            url=url,
            post=None,
            ok=False,
            status_code=status,
            error=error,
            final_url=final_url,
            elapsed_ms=elapsed_ms,
        )


# Example:
# import asyncio
#
# extractor = PostExtractor(
#     selectors=PostSelectors(
#         title="h1.post-title",
#         published_at="time[datetime], meta[property='article:published_time']",
#     ),
#     concurrency=20,
#     timeout_s=10.0,
#     retries=2,
# )
#
# results = asyncio.run(extractor.execute(["https://example.com/post/1"]))
# for r in results:
#     print(r.ok, r.status_code, r.post.title if r.post else r.error)


def main():
    print("Hello from pixnet-blog-crawler!")


if __name__ == "__main__":
    main()
