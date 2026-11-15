"""Content-addressed dedup for uploads.

A file's identity is the SHA-256 of its bytes; a link's identity is the
SHA-256 of its normalized URL. Uploading the same content again reuses
the stored parse from the shared store (parsed_sources) instead of
ingesting and parsing it a second time.

PARSER_VERSION must be bumped whenever any parser changes what a parse
produces (document_parser, image_parser, media_parser, web_parser, or
the pipeline's routing). A stored parse from an older version is
re-parsed, never reused, so parser improvements reach re-uploads
instead of being frozen in by dedup.
"""

import hashlib
from urllib.parse import parse_qs, urlparse, urlunparse

PARSER_VERSION = 1


def hash_file_path(path: str) -> str:
    """SHA-256 of a file's bytes, streamed so large files stay cheap."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_url(url: str) -> str:
    """Canonical form of a URL for dedup: strip whitespace, lowercase
    the scheme and host, drop the fragment, drop a trailing slash. A
    YouTube link is reduced to its video id, so the same video pasted
    with different parameters (start time, playlist) still matches."""
    raw = (url or "").strip()
    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    if "youtube.com" in host:
        video_id = parse_qs(parsed.query).get("v", [None])[0]
        if video_id:
            return "https://www.youtube.com/watch?v=" + video_id
    if host == "youtu.be":
        video_id = parsed.path.strip("/")
        if video_id:
            return "https://www.youtube.com/watch?v=" + video_id
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (parsed.scheme.lower(), host, path, "", parsed.query, "")
    )


def url_content_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()
