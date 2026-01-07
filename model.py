from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PostMetadata:
    index: int
    published_at: str | None
    title: str | None
    url: str


@dataclass(frozen=True, slots=True)
class PostMetadataSelectors:
    title: str
    published_at: str


@dataclass(frozen=True, slots=True)
class PostMetadataResult:
    url: str
    post: PostMetadata | None
    ok: bool
    status_code: int | None
    error: str | None
    final_url: str | None = None
    elapsed_ms: int | None = None
