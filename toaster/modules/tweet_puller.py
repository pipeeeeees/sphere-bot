"""Simple utility to fetch the latest tweet link for an X (twitter) username.

Functions:
 - `get_latest_tweet_link(username)` -> str | None

CLI usage:
    python -m toaster.modules.tweet_puller Braves
"""

from typing import Optional
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def _search_for_status_links(text: str, username: str) -> Optional[str]:
    # Try to find absolute x.com links first
    patterns = [
        rf"https?://(?:www\.)?x\.com/{re.escape(username)}/status/\d+",
        rf"https?://(?:mobile\.)?twitter\.com/{re.escape(username)}/status/\d+",
        rf"/{re.escape(username)}/status/\d+",
        rf"https?://nitter\.net/{re.escape(username)}/status/\d+",
        rf"https?://vxtwitter\.com/{re.escape(username)}/status/\d+",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            link = m.group(0)
            # If relative path like "/username/status/123" make it absolute to x.com
            if link.startswith("/"):
                return f"https://x.com{link}"
            return link
    return None


def get_latest_tweet_link(username: str, timeout: int = 10, try_nitter: bool = True) -> Optional[str]:
    """Return the URL of the latest tweet for `username`, or None if not found.

    This attempts to fetch `https://x.com/{username}` and parse the HTML for
    the first status URL. If that fails and `try_nitter` is True, it falls back
    to `https://nitter.net/{username}`.
    """
    if not username or not username.strip():
        raise ValueError("username must be a non-empty string")
    username = username.strip().lstrip("@")

    # Try X (x.com)
    urls_to_try = [f"https://x.com/{username}", f"https://mobile.twitter.com/{username}"]
    for url in urls_to_try:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            link = _search_for_status_links(resp.text, username)
            if link:
                return link
        except Exception:
            # ignore and try next
            continue

    # Fallback to nitter if available
    if try_nitter:
        try:
            nitter_url = f"https://nitter.net/{username}"
            resp = requests.get(nitter_url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            link = _search_for_status_links(resp.text, username)
            if link:
                return link
        except Exception:
            pass

    return None


def get_fixvx_equivalent(x_link: str, provider: str = "fxtwitter") -> Optional[str]:
    """Convert an X/Twitter status URL (or path) to an alternative frontend.

    Supported `provider` values: "fxtwitter", "vxtwitter", "nitter".
    Returns the converted URL or None if the input couldn't be parsed.
    """
    if not x_link or not x_link.strip():
        return None
    x_link = x_link.strip()

    # Find username and status id in common URL formats
    m = re.search(r"https?://(?:www\.)?(?:x\.com|twitter\.com|mobile\.twitter\.com)/(?P<user>[^/]+)/status(?:es)?/(?P<id>\d+)", x_link, flags=re.IGNORECASE)
    if not m:
        # Try relative path like /user/status/123
        m = re.search(r"/(?P<user>[^/]+)/status(?:es)?/(?P<id>\d+)", x_link)
    if not m:
        return None

    user = m.group("user")
    status_id = m.group("id")

    provider = (provider or "fxtwitter").lower()
    if provider == "fxtwitter":
        return f"https://fxtwitter.com/{user}/status/{status_id}"
    if provider == "vxtwitter":
        return f"https://vxtwitter.com/{user}/status/{status_id}"
    if provider == "nitter":
        return f"https://nitter.net/{user}/status/{status_id}"
    # unknown provider -> return original x.com normalized
    return f"https://x.com/{user}/status/{status_id}"


if __name__ == "__main__":
    
    print(get_latest_tweet_link("Braves"))
    print(get_fixvx_equivalent(r"https://x.com/Braves/status/2088771820757336419"))