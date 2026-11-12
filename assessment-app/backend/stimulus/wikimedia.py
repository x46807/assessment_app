import requests
from typing import Optional, Dict, Any

class WikimediaProvider:
    COMMONS_API = "https://commons.wikimedia.org/w/api.php"
    USER_AGENT = "AssessmentEngine/1.0"

    @classmethod
    def search_media(cls, query: str) -> Optional[Dict[str, Any]]:
        headers = {"User-Agent": cls.USER_AGENT}
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": f"{query} filetype:bitmap|drawing",
            "srnamespace": 6,
            "srlimit": 1,
            "format": "json"
        }
        try:
            res = requests.get(cls.COMMONS_API, params=search_params, headers=headers, timeout=8)
            results = res.json().get("query", {}).get("search", [])
            if not results:
                return None
            best_title = results[0]["title"]

            info_params = {
                "action": "query",
                "titles": best_title,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": 800,
                "format": "json"
            }
            info_res = requests.get(cls.COMMONS_API, params=info_params, headers=headers, timeout=8)
            pages = info_res.json().get("query", {}).get("pages", {})
            info = next(iter(pages.values()))["imageinfo"][0]
            artist = info.get("extmetadata", {}).get("Artist", {}).get("value", "Public Domain")
            return {
                "media_url": info.get("thumburl") or info.get("url"),
                "attribution": f"{artist} via Wikimedia Commons"
            }
        except Exception:
            return None
