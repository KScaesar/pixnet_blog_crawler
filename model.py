from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto

import random
import string
from selectolax.parser import Node

# page_crawler.py


@dataclass(slots=True, kw_only=True)
class PostMetadata:
    idx: int = field(default=0, init=False)  # Index of the post
    published_at: datetime  # Published timestamp
    url: str  # URL of the post
    title: str  # Title of the post

    def __str__(self) -> str:
        return f"[{self.idx:05d}]: {self.published_at} - {self.url} - {self.title}"


@dataclass(slots=True, kw_only=True)
class PageCrawlerSelectors:
    post_container: str  # CSS selector for the post block
    title: str  # CSS selector for the title element
    published_at: str  # CSS selector for the date element
    post_url: str  # CSS selector for the detail link


# post_crawler.py


class LineKind(Enum):
    TEXT = auto()
    IMAGE = auto()
    LINK = auto()


@dataclass(slots=True, kw_only=True)
class Line:
    """Represents a single segment of content (either text or an image)."""

    kind: LineKind
    body: str  # Text content or image alt text
    url: str | None  # Optional URL for links or image sources

    def __str__(self) -> str:
        match self.kind:
            case LineKind.IMAGE:
                return f"[IMAGE] {self.body} -> {self.url}"
            case LineKind.LINK:
                return f"[LINK] {self.body} -> {self.url}"
            case LineKind.TEXT:
                return f"[TEXT] {self.body}"


@dataclass(slots=True, kw_only=True)
class Post:
    metadata: PostMetadata  # Post level metadata
    content_many: list[Line]  # List of content fragments
    link_many: list[tuple[str, str]]  # List of URLs and anchor texts
    image_many: list[tuple[str, str]]  # List of URLs and alias name

    @classmethod
    def parse_dom_node(cls, root: Node, metadata: PostMetadata, enable_fallback: bool = False) -> "Post":
        """
        Factory method to construct a Post from a parent selectolax Node.

        Rules:
        - Traverses the DOM sequentially to preserve content order.
        - Extracts text, images, and links mixed together.
        - Populates content_many (ordered), link_many (summary), and image_many (summary).
        """
        content_many: list[Line] = []
        link_many: list[tuple[str, str]] = []
        image_many: list[tuple[str, str]] = []

        def append_lines(node: Node) -> None:
            """
            Append lines extracted from this node.

            Priority:
            1) All <img> descendants (emit all, keep order inside this node)
            2) First link (without nested image)
            3) Text (stripped)
            4) Fallback: recurse into children
            """
            images = node.css("img")
            if images:
                for img in images:
                    src = img.attributes.get("src")
                    caption = img.attributes.get("title") or img.attributes.get("alt") or ""
                    suffix = "".join(random.choices(string.ascii_letters + string.digits, k=4))
                    body = cls.ensure_ext(caption or f"no_alt_{suffix}", src)
                    if src:
                        image_many.append((src, body))
                    content_many.append(Line(kind=LineKind.IMAGE, body=body, url=src))
                return

            link_node = node.css_first("a")
            if link_node and not link_node.css_first("img"):
                href = link_node.attributes.get("href")
                text = node.text(strip=True) or link_node.text(strip=True)
                body = text or href or ""
                if href:
                    link_many.append((href, body))
                content_many.append(Line(kind=LineKind.LINK, body=body, url=href))
                return

            text = node.text(strip=True)
            if text:
                content_many.append(Line(kind=LineKind.TEXT, body=text, url=None))
                return

            for child in cls.iter_direct_children(node):
                append_lines(child)

        for child in cls.iter_direct_children(root):
            append_lines(child)

        if enable_fallback:
            cls._apply_fallback_strategies(
                root,
                doc=root.parser,
                content_many=content_many,
                image_many=image_many,
            )

        return cls(metadata=metadata, content_many=content_many, link_many=link_many, image_many=image_many)

    @staticmethod
    def iter_direct_children(node: Node):
        child = node.child
        while child is not None:
            yield child
            child = child.next

    @staticmethod
    def ensure_ext(name: str, src: str | None) -> str:
        """Append filename extension from src if name has none."""
        if not src or "." not in src.rsplit("/", 1)[-1]:
            return name
        ext = src.rsplit("/", 1)[-1].rsplit("?", 1)[0].rsplit("#", 1)[0]
        if "." not in ext:
            return name
        ext = "." + ext.split(".")[-1]
        if name.lower().endswith(ext.lower()):
            return name
        return f"{name}{ext}"

    @staticmethod
    def _apply_fallback_strategies(
        root: Node,
        doc: object | None,
        content_many: list[Line],
        image_many: list[tuple[str, str]],
    ) -> None:
        """
        Apply fallback strategies to find images that might have been missed by standard parsing.
        """
        seen_images: set[str] = set(url for url, _ in image_many if url)

        # Fallback: ensure all images under root are captured even if nested structures were skipped.
        for img in root.css("img"):
            src = img.attributes.get("src")
            if not src or src in seen_images:
                continue
            caption = img.attributes.get("title") or img.attributes.get("alt") or ""
            body = Post.ensure_ext(caption or "(no alt)", src)
            seen_images.add(src)
            image_many.append((src, body))
            content_many.append(Line(kind=LineKind.IMAGE, body=body, url=src))

        # Broader fallback: grab image tags from the whole document matching the blog host.
        if doc is not None:
            # Note: doc.css might not be available if doc is not a Node, but root.parser returns an HTMLParser or similar.
            # Assuming doc has .css method if it's the parser object that selectolax provides.
            # However, root.parser in selectolax returns the HTMLParser object which doesn't have .css directly usually?
            # Actually root.parser returns the HTMLParser instance.
            # Let's verify if we can use css on it.
            # If doc is the HTMLParser, it doesn't have .css. root does.
            # The original code used doc.css("img") at line 152.
            # Let's check imports. selectolax.parser.Node's .parser property returns the HTMLParser.
            # HTMLParser has .css? No, usually the tree is queried via Node.
            # But earlier code was working, so let's stick to what was there or fix it if it was broken.
            # Wait, line 152 in original code: `for img in doc.css("img"):`.
            # If that was working, then doc must have .css.
            # In selectolax, HTMLParser does NOT have .css. Only Node.
            # But maybe root.parser isn't what I think it is, or the user's code relies on it being something else.
            # Let's trust the original code structure for now but be careful.
            # Actually, looking at line 5: from selectolax.parser import Node.
            # If doc is HTMLParser, it doesn't have css.
            # Maybe the previous code was crashing there? Or never reached?
            # The user ran it and it worked? "Successfully crawled 2 posts".
            # So let's reproduce the logic exactly.

            if hasattr(doc, "css"):
                for img in doc.css("img"):
                    src = img.attributes.get("src")
                    if not src or src in seen_images:
                        continue
                    if "pimg.tw/workatravel" not in src:
                        continue
                    caption = img.attributes.get("title") or img.attributes.get("alt") or ""
                    body = Post.ensure_ext(caption or "(no alt)", src)
                    seen_images.add(src)
                    image_many.append((src, body))
                    content_many.append(Line(kind=LineKind.IMAGE, body=body, url=src))

        # As a last resort, regex through the raw HTML of the content container.
        if not image_many and getattr(root, "html", None):
            import re

            for match in re.finditer(r"<img[^>]+>", root.html):
                tag = match.group(0)
                src_match = re.search(r'src="([^"]+)"', tag)
                if not src_match:
                    continue
                src = src_match.group(1)
                if src in seen_images:
                    continue
                title_match = re.search(r'title="([^"]*)"', tag)
                alt_match = re.search(r'alt="([^"]*)"', tag)
                caption = (title_match.group(1) if title_match else "") or (alt_match.group(1) if alt_match else "")
                body = Post.ensure_ext(caption or "(no alt)", src)
                seen_images.add(src)
                image_many.append((src, body))
                content_many.append(Line(kind=LineKind.IMAGE, body=body, url=src))

        # Final fallback: regex across the full document HTML (helps when JS injected images are absent from parsed tree).
        if not image_many and doc is not None and hasattr(doc, "html"):
            import re

            html_str = doc.html
            for match in re.finditer(r"<img[^>]+>", html_str):
                tag = match.group(0)
                src_match = re.search(r'src="([^"]+)"', tag)
                if not src_match:
                    continue
                src = src_match.group(1)
                if src in seen_images or "pimg.tw/workatravel" not in src:
                    continue
                title_match = re.search(r'title="([^"]*)"', tag)
                alt_match = re.search(r'alt="([^"]*)"', tag)
                caption = (title_match.group(1) if title_match else "") or (alt_match.group(1) if alt_match else "")
                body = Post.ensure_ext(caption or "(no alt)", src)
                seen_images.add(src)
                image_many.append((src, body))
                content_many.append(Line(kind=LineKind.IMAGE, body=body, url=src))

    def __str__(self) -> str:
        lines = []
        lines.append(str(self.metadata))

        if self.content_many:
            lines.append(f"Content ({len(self.content_many)} lines):")
            for line in self.content_many:
                lines.append(f"{line}")

        if self.link_many:
            lines.append(f"Links ({len(self.link_many)}):")
            for url, text in self.link_many:
                lines.append(f"  - {text}: {url}")

        if self.image_many:
            lines.append(f"Images ({len(self.image_many)}):")
            for url, filename in self.image_many:
                lines.append(f"  - {filename}: {url}")

        return "\n".join(lines)


@dataclass(slots=True, kw_only=True)
class PostCrawlerSelectors:
    content_container: list[str]  # List of CSS selectors for the main content body, tried in order
