from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
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


@dataclass(slots=True, kw_only=True)
class Line:
    """Represents a single segment of content (either text or an image)."""

    kind: LineKind
    body: str  # Text content or image alt text
    url: str | None  # Optional URL for links or image sources

    def __str__(self) -> str:
        if self.kind == LineKind.IMAGE:
            return f"[IMAGE] {self.body or '(no alt)'} -> {self.url}"
        elif self.url:
            return f"[TEXT+LINK] {self.body} -> {self.url}"
        else:
            return f"[TEXT] {self.body}"


@dataclass(slots=True, kw_only=True)
class Post:
    metadata: PostMetadata  # Post level metadata
    content_many: list[Line]  # List of content fragments
    reference_many: list[tuple[str, str]]  # List of URLs and anchor texts
    image_many: list[tuple[str, str]]  # List of URLs and alias name

    def __str__(self) -> str:
        lines = []
        lines.append(str(self.metadata))
        
        if self.content_many:
            lines.append(f"Content ({len(self.content_many)} lines):")
            for i, line in enumerate(self.content_many):
                lines.append(f"{line}")
        
        if self.reference_many:
            lines.append(f"References ({len(self.reference_many)}):")
            for url, text in self.reference_many:
                lines.append(f"  - {text}: {url}")
        
        if self.image_many:
            lines.append(f"Images ({len(self.image_many)}):")
            for url, filename in self.image_many:
                lines.append(f"  - {filename}: {url}")
        
        return "\n".join(lines)

    @classmethod
    def parse_dom_node(cls, root: Node, metadata: PostMetadata) -> "Post":
        """
        Factory method to construct a Post from a parent selectolax Node.

        Rules:
        - Traverses the DOM sequentially to preserve content order.
        - Extracts text, images, and links mixed together.
        - Populates content_many (ordered), reference_many (summary), and image_many (summary).
        """
        content_many: list[Line] = []
        reference_many: list[tuple[str, str]] = []
        image_many: list[tuple[str, str]] = []

        def _traverse(node: Node, current_link: str | None = None):
            print(f"DEBUG Traversal: {node.tag}")
            # Handle Text Nodes
            if node.tag == "-text":
                text = node.text()
                # Skip empty whitespace, but maybe keys non-breaking spaces if separate?
                # User preference seemed to be preserving structure.
                # Adjusting logic: collapse whitespace but keep meaningful text.
                # If text is non-empty after strip, use the original (or stripped) text?
                # Let's clean it up slightly but preserve line breaks if they were separate nodes.
                if text.strip():
                    content_many.append(Line(kind=LineKind.TEXT, body=text, url=current_link))
                return

            # Handle Elements
            tag = node.tag
            
            # Update Link Context
            if tag == "a":
                href = node.attributes.get("href", "")
                if href:
                    current_link = href
                    # Add to summary list
                    text_summary = node.text(deep=True).strip()
                    if text_summary:
                        reference_many.append((href, text_summary))

            # Handle Images
            if tag == "img":
                print(f"DEBUG Found IMG: {node.attributes}")
                src = node.attributes.get("src", "")
                if src:
                    alt = node.attributes.get("alt", "")
                    
                    # Generate filename
                    ext = src.split('.')[-1].split('?')[0].lower()
                    if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                        ext = 'jpg'
                    filename = f"{len(image_many) + 1}.{ext}"
                    
                    image_many.append((src, filename))
                    content_many.append(Line(kind=LineKind.IMAGE, body=alt, url=src))
                return # Img is self-closing, no children to traverse usually

            # Recurse for children
            for child in node.iter(include_text=True):
                 # selectolax iter(include_text=True) yields text nodes as well
                _traverse(child, current_link)

            # Block-level elements might imply a newline, but Line object structure handles segregation.
            # no explicit action needed for p/div closing unless we want empty lines.

        # Start traversal directly on children to avoid processing the container itself if not needed
        # Or just pass root.
        _traverse(root)

        return cls(metadata=metadata, content_many=content_many, reference_many=reference_many, image_many=image_many)


@dataclass(slots=True, kw_only=True)
class PostCrawlerSelectors:
    content_container: str  # CSS selector for the main content body
