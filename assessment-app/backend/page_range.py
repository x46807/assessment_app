"""Page scoping for paginated sources (PDFs).

A source can be restricted to a subset of its pages for generation:
the user enters a range like "1-3, 5, 8-10" (comma-separated page
numbers and dash ranges). The default is all pages. The raw string is
stored on the source; it is parsed (and validated against the source's
page count) when saved and again when used, so a stored range can
never break generation.
"""

from typing import Dict, List, Optional, Set


def parse_page_range(spec, max_page=None):
    """Parse a page-range string into a set of 1-based page numbers,
    or None when the spec is empty (meaning: all pages).

    Raises ValueError with a plain, user-facing message on bad input:
    non-numeric entries, zero or negative pages, backwards ranges,
    empty entries, or pages beyond max_page when it is given.
    """
    if spec is None:
        return None
    text = str(spec).strip()
    if not text:
        return None
    pages = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            raise ValueError("Empty entry in page range %r -- use numbers like 5 or ranges like 1-3, separated by commas." % text)
        if "-" in part:
            bits = part.split("-")
            if len(bits) != 2:
                raise ValueError("Could not read %r as a page range -- use a form like 1-3." % part)
            try:
                start = int(bits[0].strip())
                end = int(bits[1].strip())
            except ValueError:
                raise ValueError("Could not read %r as a page range -- use numbers like 1-3." % part)
            if start < 1 or end < 1:
                raise ValueError("Page numbers start at 1; %r is not a valid range." % part)
            if start > end:
                raise ValueError("Range %r is backwards -- the first page must come before the last." % part)
            pages.update(range(start, end + 1))
        else:
            try:
                number = int(part)
            except ValueError:
                raise ValueError("Could not read %r as a page number." % part)
            if number < 1:
                raise ValueError("Page numbers start at 1; %r is not valid." % part)
            pages.add(number)
    if max_page is not None:
        beyond = sorted(p for p in pages if p > max_page)
        if beyond:
            raise ValueError(
                "Page%s %s %s beyond this source, which has %d page%s."
                % ("s" if len(beyond) != 1 else "", ", ".join(str(p) for p in beyond),
                   "are" if len(beyond) != 1 else "is", max_page,
                   "s" if max_page != 1 else ""))
    return pages


def page_count_for_content(content):
    """Number of pages in a stored parse (the highest page number
    among its chunks), or None when the content has no page locators
    (non-paginated sources: Word, text, images, links)."""
    pages = set()
    for chunk in (content or {}).get("chunks", []) or []:
        if chunk.get("locator_type") == "page":
            try:
                pages.add(int(chunk.get("locator_value")))
            except (TypeError, ValueError):
                continue
    return max(pages) if pages else None


def filter_to_pages(result, pages):
    """Return a copy of an IngestionResult restricted to the given
    page numbers (None means: all pages, returned unchanged). Chunks
    whose locator is a page outside the set are dropped, as are
    embedded images from those pages; chunks with no page locator
    are kept."""
    if pages is None:
        return result
    copy = result.model_copy(deep=True)
    kept_chunks = []
    for chunk in copy.chunks or []:
        if getattr(chunk, "locator_type", None) != "page":
            kept_chunks.append(chunk)
            continue
        try:
            page = int(getattr(chunk, "locator_value", None))
        except (TypeError, ValueError):
            kept_chunks.append(chunk)
            continue
        if page in pages:
            kept_chunks.append(chunk)
    copy.chunks = kept_chunks
    copy.total_chunks = len(kept_chunks)
    if getattr(copy, "images", None):
        copy.images = [img for img in copy.images
                       if getattr(img, "page", None) is None or img.page in pages]
    return copy
