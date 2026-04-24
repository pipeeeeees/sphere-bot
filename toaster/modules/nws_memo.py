import sys
import json
import urllib.request
import urllib.error


NWS_API_BASE = "https://api.weather.gov"

# Mapping of well-known cities to their NWS office IDs (WFO codes)
# This is used as a fast-path fallback. The primary method uses the NWS points API.
KNOWN_WFO = {
    "new york":     "OKX",
    "los angeles":  "LOX",
    "chicago":      "LOT",
    "houston":      "HGX",
    "phoenix":      "PSR",
    "philadelphia": "PHI",
    "san antonio":  "EWX",
    "san diego":    "SGX",
    "dallas":       "FWD",
    "seattle":      "SEW",
    "denver":       "BOU",
    "boston":       "BOX",
    "atlanta":      "FFC",
    "miami":        "MFL",
    "minneapolis":  "MPX",
    "portland":     "PQR",
    "las vegas":    "VEF",
    "detroit":      "DTX",
    "memphis":      "MEG",
    "nashville":    "OHX",
    "st. louis":    "LSX",
    "kansas city":  "EAX",
    "salt lake city": "SLC",
    "albuquerque":  "ABQ",
    "sacramento":   "STO",
    "san francisco": "MTR",
    "oklahoma city": "OUN",
    "new orleans":  "LIX",
    "raleigh":      "RAH",
    "charlotte":    "GSP",
    "pittsburgh":   "PBZ",
    "cincinnati":   "ILN",
    "cleveland":    "CLE",
    "columbus":     "ILN",
    "indianapolis": "IND",
    "milwaukee":    "MKX",
    "richmond":     "AKQ",
    "washington":   "LWX",
    "baltimore":    "LWX",
    "jacksonville": "JAX",
    "tampa":        "TBW",
    "orlando":      "MLB",
    "buffalo":      "BUF",
    "albany":       "ALY",
    "hartford":     "BOX",
    "providence":   "BOX",
    "burlington":   "BTV",
    "portland me":  "GYX",
    "boise":        "BOI",
    "billings":     "BYZ",
    "fargo":        "FGF",
    "omaha":        "OAX",
    "des moines":   "DMX",
    "sioux falls":  "FSD",
    "wichita":      "ICT",
    "tulsa":        "TSA",
    "little rock":  "LZK",
    "birmingham":   "BMX",
    "jackson ms":   "JAN",
    "shreveport":   "SHV",
    "corpus christi": "CRP",
    "lubbock":      "LUB",
    "el paso":      "EPZ",
    "tucson":       "TWC",
    "fresno":       "HNX",
    "bakersfield":  "HNX",
    "reno":         "REV",
    "spokane":      "OTX",
    "anchorage":    "AFC",
    "honolulu":     "HFO",
}


def fetch_json(url: str) -> dict:
    """Fetch a URL and return parsed JSON."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "nws-memo-script/1.0 (python)"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def geocode_city(city: str) -> tuple[float, float]:
    """
    Geocode a city name to (lat, lon) using the US Census Geocoder.
    Returns the coordinates of the best match.
    """
    encoded = urllib.parse.quote(city)
    url = (
        f"https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
        f"?address={encoded}&benchmark=Public_AR_Current&format=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "nws-memo-script/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    matches = data.get("result", {}).get("addressMatches", [])
    if not matches:
        raise ValueError(f"Could not geocode city: '{city}'")

    coords = matches[0]["coordinates"]
    return float(coords["y"]), float(coords["x"])   # lat, lon


def get_wfo_for_city(city: str) -> str:
    """
    Resolve a city name to a NWS Weather Forecast Office (WFO) code.
    First tries the known-WFO table, then falls back to the NWS points API
    via Census geocoding.
    """
    # Fast path: normalise and look up
    key = city.lower().split(",")[0].strip()
    if key in KNOWN_WFO:
        return KNOWN_WFO[key]

    # Slow path: geocode → NWS /points
    import urllib.parse  # imported here so it's only needed for this branch
    lat, lon = geocode_city(city)
    points_url = f"{NWS_API_BASE}/points/{lat:.4f},{lon:.4f}"
    try:
        data = fetch_json(points_url)
        wfo = data["properties"]["cwa"]   # e.g. "FFC"
        return wfo
    except Exception as exc:
        raise RuntimeError(
            f"NWS points lookup failed for '{city}' ({lat:.4f}, {lon:.4f}): {exc}"
        ) from exc


def get_latest_afd(wfo: str) -> str:
    """
    Fetch the latest Area Forecast Discussion (AFD) for the given WFO.
    Returns the full memo text.
    """
    url = f"{NWS_API_BASE}/products/types/AFD/locations/{wfo}"
    data = fetch_json(url)

    graph = data.get("@graph", [])
    if not graph:
        raise RuntimeError(f"No AFD products found for WFO '{wfo}'.")

    # The first entry is the most recent
    product_url = graph[0]["@id"]
    product = fetch_json(product_url)
    return product["productText"]

import re

def extract_key_messages(afd_text: str) -> list[str]:
    """
    Extract bullet points from the .KEY MESSAGES... section of an NWS AFD.
    Returns a list of message strings.
    """
    # Grab everything between .KEY MESSAGES... and the next &&
    match = re.search(r'\.KEY MESSAGES\.\.\.(.*?)&&', afd_text, re.DOTALL | re.IGNORECASE)
    if not match:
        return []

    block = match.group(1)

    # Each bullet starts with "- " (possibly with leading whitespace)
    # Multi-line bullets are indented with spaces on continuation lines
    messages = []
    current = []

    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            if current:
                messages.append(" ".join(current))
            current = [stripped[2:].strip()]
        elif stripped and current:
            # Continuation line of the current bullet
            current.append(stripped)

    if current:
        messages.append(" ".join(current))

    return messages

def get_atl_key_messages():
    wfo = get_wfo_for_city("Atlanta, GA")
    memo = get_latest_afd(wfo)
    key_messages = extract_key_messages(memo)
    return key_messages

def get_atl_key_messages_formatted():
    key_messages = get_atl_key_messages()
    if not key_messages:
        return "No key messages found in the latest AFD for Atlanta."
    
    formatted = "**Key Messages from the National Weather Service for Atlanta:**"
    for msg in key_messages:
        formatted += f"\n- {msg}"
    return formatted

if __name__ == "__main__":
    print(get_atl_key_messages_formatted())