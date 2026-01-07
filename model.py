from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True, kw_only=True)
class PostMetadata:
    idx: int = field(default=0, init=False)
    published_at: datetime
    url: str
    title: str

    def __str__(self) -> str:
        return f"[{self.idx:05d}]: {self.published_at} - {self.url} - {self.title}"


class PageCrawlerSelectors:
    """
    CSS selectors for extracting post metadata from paginated pages.

    Attributes:
        post_container: Selector for each post container on the page
        title: Selector for post title (relative to post_container)
        published_at: Selector for published date (relative to post_container)
        post_url: Selector for post URL link (relative to post_container)
    """

    def __init__(
        self,
        *,
        post_container: str,
        title: str,
        published_at: str,
        post_url: str,
    ) -> None:
        self.post_container = post_container
        self.title = title
        self.published_at = published_at
        self.post_url = post_url
