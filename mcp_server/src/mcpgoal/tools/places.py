"""OSM Nominatim + Overpass tools — search places, shops, addresses via OpenStreetMap."""
import json
import math
import httpx

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_HEADERS = {
    "User-Agent": "VASS/1.0 (voice assistant; github.com/logicheneurali/vass)",
    "Accept": "application/json",
}


async def _geocode(place: str) -> tuple:
    params = {"q": place.strip(), "format": "json", "limit": 1}
    async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
        resp = await client.get(_NOMINATIM_URL, params=params)
        data = resp.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    return None, None


async def _overpass_query(lat: float, lon: float, osm_key: str, osm_value: str, radius_m: int = 3000, limit: int = 10) -> list:
    delta = radius_m / 111000.0
    bbox = f"{lat - delta},{lon - delta},{lat + delta},{lon + delta}"
    tag = f'["{osm_key}"="{osm_value}"]'
    query = f"[out:json];(node{tag}({bbox});way{tag}({bbox}););out body {limit};"
    async with httpx.AsyncClient(timeout=20, headers=_HEADERS) as client:
        resp = await client.post(_OVERPASS_URL, content=query)
        resp.raise_for_status()
        data = resp.json()
    return data.get("elements", [])


def _distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def search_nearby(osm_key: str, osm_value: str, near: str, radius: int = 3000, limit: int = 10) -> str:
    """Search nearby places by OpenStreetMap tag. Use osm_key + osm_value.
    Common tags: amenity=pharmacy, amenity=restaurant, shop=supermarket, shop=hardware,
    amenity=bank, amenity=cafe, tourism=hotel, amenity=hospital, shop=bakery, etc.
    Always provide 'near' with a city/address. Returns name, address, distance, map link sorted by distance.
    Examples: search_nearby('amenity', 'pharmacy', 'Messina')
              search_nearby('shop', 'supermarket', 'via Roma, Milano', 1000)"""
    try:
        radius = max(500, min(10000, int(radius)))
        limit = max(1, min(15, int(limit)))
    except (ValueError, TypeError):
        radius = 3000
        limit = 10

    try:
        lat, lon = await _geocode(near)
    except Exception as e:
        return json.dumps({"error": f"Geocoding failed: {e}"}, ensure_ascii=False)

    if lat is None:
        return json.dumps({"error": f"Location '{near}' not found"}, ensure_ascii=False)

    try:
        elements = await _overpass_query(lat, lon, osm_key, osm_value, radius, limit)
    except Exception as e:
        return json.dumps({"error": f"Overpass query failed: {e}"}, ensure_ascii=False)

    if not elements:
        return json.dumps({"results": [], "message": f"No {osm_key}={osm_value} found near {near}"}, ensure_ascii=False)

    results = []
    for e in elements:
        tags = e.get("tags", {})
        elat = e.get("lat") or (e.get("center", {}).get("lat") if "center" in e else None) or lat
        elon = e.get("lon") or (e.get("center", {}).get("lon") if "center" in e else None) or lon
        try:
            elat, elon = float(elat), float(elon)
        except (ValueError, TypeError):
            continue
        dist = _distance(lat, lon, elat, elon)
        street = tags.get("addr:street", "")
        number = tags.get("addr:housenumber", "")
        addr = f"{street} {number}".strip()
        results.append({
            "name": tags.get("name", "") or tags.get("brand", "") or tags.get("operator", "") or "?",
            "type": f"{osm_key}={osm_value}",
            "address": addr,
            "distance_m": round(dist),
            "lat": str(elat),
            "lon": str(elon),
            "maps_url": f"https://www.openstreetmap.org/?mlat={elat}&mlon={elon}",
        })

    results.sort(key=lambda r: r["distance_m"])

    return json.dumps({"results": results}, ensure_ascii=False)


async def search_places(query: str, near: str = "", limit: int = 5) -> str:
    """Search for places, shops, or addresses using OpenStreetMap Nominatim.
    Args:
        query: what to find (e.g. "farmacia", "ristorante", "supermercato")
        near: location to search in (e.g. "Messina", "Roma", "Milano, Italia").
              Always use this to specify the city/area, otherwise results may be wrong.
        limit: max results (1-10, default 5)
    """
    try:
        limit = max(1, min(10, int(limit)))
    except (ValueError, TypeError):
        limit = 5

    q = f"{query.strip()}, {near.strip()}" if near and near.strip() else query.strip()

    params = {
        "q": q,
        "format": "json",
        "limit": limit,
        "addressdetails": 1,
        "namedetails": 1,
        "accept-language": "it,en",
    }

    try:
        async with httpx.AsyncClient(timeout=15, headers=_HEADERS) as client:
            resp = await client.get(_NOMINATIM_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return json.dumps({"error": f"Search failed: {e}"}, ensure_ascii=False)

    if not data:
        return json.dumps({"results": [], "message": "No places found"}, ensure_ascii=False)

    results = []
    for place in data:
        addr = place.get("address", {})
        results.append({
            "name": _best_name(place),
            "type": place.get("type", ""),
            "category": place.get("category", ""),
            "display_name": place.get("display_name", ""),
            "lat": place.get("lat", ""),
            "lon": place.get("lon", ""),
            "street": addr.get("road") or addr.get("pedestrian") or "",
            "city": addr.get("city") or addr.get("town") or addr.get("village") or "",
            "postcode": addr.get("postcode", ""),
            "country": addr.get("country", ""),
            "maps_url": f"https://www.openstreetmap.org/?mlat={place.get('lat','')}&mlon={place.get('lon','')}",
        })

    return json.dumps({"results": results}, ensure_ascii=False)


def _best_name(place):
    namedetails = place.get("namedetails", {})
    if not namedetails:
        namedetails = {}
    for lang in ("name:it", "name:en", "name:de", "name:fr", "name:es", "name", "official_name", "localname", "alt_name"):
        if namedetails.get(lang):
            return namedetails[lang]
    return place.get("name", place.get("display_name", "Unknown"))