import requests
from typing import List, Optional, Dict, Any

class WikimediaProvider:
    COMMONS_API = "https://commons.wikimedia.org/w/api.php"
    USER_AGENT = "AssessmentEngine/1.0 (educational quiz app)"
    # Image files the quiz frontend can display. PDFs are excluded even
    # though Commons returns them: a scanned book's first page is not a
    # map or illustration.
    IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml", "image/tiff"}

    @classmethod
    def search_media(cls, query: str, exclude_urls: Optional[List[str]] = None,
                     exclude_titles: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Find a usable map/illustration on Wikimedia Commons.

        Two attempts: first with the (valid, single-value) filetype:bitmap
        filter, then unfiltered. The previous query used
        "filetype:bitmap|drawing", which is not valid CirrusSearch syntax
        and returned zero hits for every query, so the map path silently
        degraded to a text passage on every generation.

        exclude_urls / exclude_titles skip images already used for an
        earlier chunk of the same generation (John, 2026-11-15: no
        image shared by more than 3 questions), so each chunk gets a
        fresh image; every returned title is tried, not just the
        first three.
        """
        excluded_urls = set(exclude_urls or [])
        excluded_titles = set(exclude_titles or [])
        for srsearch in (f"{query} filetype:bitmap", query):
            titles = cls._search_titles(srsearch)
            for title in titles:
                if title in excluded_titles:
                    continue
                info = cls._image_info(title)
                if not info:
                    continue
                if info.get("mime") not in cls.IMAGE_MIMES:
                    continue
                media_url = info.get("thumburl") or info.get("url")
                if not media_url or media_url in excluded_urls:
                    continue
                artist = info.get("extmetadata", {}).get("Artist", {}).get("value", "Public Domain")
                print(f"[Wikimedia] {title} ({info.get('mime')}) -> {media_url[:100]}")
                return {
                    "media_url": media_url,
                    "attribution": f"{artist} via Wikimedia Commons",
                    "title": title,
                }
            print(f"[Wikimedia] no usable image for query: {srsearch!r}")
        return None

    @classmethod
    def _search_titles(cls, srsearch: str):
        headers = {"User-Agent": cls.USER_AGENT}
        params = {
            "action": "query",
            "list": "search",
            "srsearch": srsearch,
            "srnamespace": 6,
            "srlimit": 5,
            "format": "json",
        }
        try:
            res = requests.get(cls.COMMONS_API, params=params, headers=headers, timeout=8)
            return [hit["title"] for hit in res.json().get("query", {}).get("search", [])]
        except Exception as e:
            print(f"[Wikimedia] search failed for {srsearch!r}: {e}")
            return []

    @classmethod
    def _image_info(cls, title: str) -> Optional[Dict[str, Any]]:
        headers = {"User-Agent": cls.USER_AGENT}
        params = {
            "action": "query",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime",
            "iiurlwidth": 800,
            "format": "json",
        }
        try:
            res = requests.get(cls.COMMONS_API, params=params, headers=headers, timeout=8)
            pages = res.json().get("query", {}).get("pages", {})
            if not pages:
                return None
            info = next(iter(pages.values())).get("imageinfo")
            return info[0] if info else None
        except Exception as e:
            print(f"[Wikimedia] imageinfo failed for {title!r}: {e}")
            return None
