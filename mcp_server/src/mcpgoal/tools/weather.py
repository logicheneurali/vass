"""Weather tool for the MCP server.

Fetches current weather for a location. Same source cascade and cache policy
as the VASScript get_weather() builtin (Open-Meteo -> met.no -> wttr.in),
implemented standalone so the AI in chat can call it directly.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

_GEONAMES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "config", "cities500.txt",
)
_geonames = {}
_geonames_loaded = False
_cache = {}
_CACHE_TTL = 900  # 15 minutes, same as the VASScript weather cache

_WMO = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


def _load_geonames():
    global _geonames_loaded
    if _geonames_loaded:
        return
    if os.path.exists(_GEONAMES_PATH):
        try:
            with open(_GEONAMES_PATH, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    p = line.strip().split("\t")
                    if len(p) >= 6:
                        _geonames[p[1].lower()] = (float(p[4]), float(p[5]),
                                                    p[8] if len(p) > 8 else "")
        except Exception:
            pass
    _geonames_loaded = True


def _fuzzy_ratio(a, b):
    """Simple subsequence similarity in [0,1] (no external dep)."""
    a, b = a.lower(), b.lower()
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return min(len(a), len(b)) / max(len(a), len(b))
    # shared character bigrams
    sa = {a[i:i + 2] for i in range(len(a) - 1)}
    sb = {b[i:i + 2] for i in range(len(b) - 1)}
    if not sa or not sb:
        return 1.0 if a == b else 0.0
    return len(sa & sb) / max(1, len(sa | sb))


def resolve_coordinates(location):
    _load_geonames()
    if not _geonames:
        return None
    key = location.strip().lower()
    if key in _geonames:
        return _geonames[key]
    best, best_r = None, 0.0
    for name in _geonames:
        r = _fuzzy_ratio(key, name)
        if r > best_r:
            best_r, best = r, name
    if best and best_r >= 0.7:
        return _geonames[best]
    return None


def _degrees_compass(deg):
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[round(float(deg) / 22.5) % 16]


def _parse_time_variants(raw, date_str=""):
    """Split "hh:mm AM/PM" or ISO into (12h, 24h, unix-ts-or-empty)."""
    if not raw:
        return "", "", ""
    raw = raw.strip()
    ts = ""
    h24 = ""
    t = re.search(r"(\d{1,2}):(\d{2})\s*([APap][Mm])?", raw)
    if t:
        hh, mm = int(t.group(1)), t.group(2)
        ampm = (t.group(3) or "").lower()
        h24 = f"{hh:02d}:{mm}"
        if ampm:
            h24 = f"{hh % 12:02d}:{mm}" if ampm == "am" else f"{(hh % 12) + 12:02d}:{mm}"
            if date_str:
                try:
                    import datetime
                    ts = str(int(datetime.datetime.strptime(
                        f"{date_str} {h24}", "%Y-%m-%d %H:%M").timestamp()))
                except Exception:
                    ts = ""
        return raw, h24, ts
    # ISO with T
    m = re.match(r"(\d{4}-\d{2}-\d{2})T?(\d{2}:\d{2})(?::\d{2})?", raw)
    if m:
        h24 = m.group(2)
        try:
            import datetime
            ts = str(int(datetime.datetime.strptime(
                f"{m.group(1)} {h24}", "%Y-%m-%d %H:%M").timestamp()))
        except Exception:
            ts = ""
        hh = int(h24[:2])
        return f"{(hh % 12) or 12}:{h24[3:]} {'PM' if hh >= 12 else 'AM'}", h24, ts
    return raw, "", ""


def _weather_wttr(location):
    encoded = urllib.parse.quote(location.strip()) if location.strip() else ""
    base = f"https://wttr.in/{encoded}" if encoded else "https://wttr.in/"
    r = urllib.request.urlopen(f"{base}?format=j1", timeout=10)
    data = json.loads(r.read().decode())
    nearest = (data.get("nearest_area") or [{}])[0]
    cc = (data.get("current_condition") or [{}])[0]
    weather_day = (data.get("weather") or [{}])[0]
    date_str = weather_day.get("date", "")
    astro = weather_day.get("astronomy", [{}])[0] or {}
    sr, sr_24h, sr_ts = _parse_time_variants(astro.get("sunrise", ""), date_str)
    ss, ss_24h, ss_ts = _parse_time_variants(astro.get("sunset", ""), date_str)
    ot, ot_24h, ot_ts = _parse_time_variants(cc.get("observation_time", ""), date_str)
    return {
        "city": (nearest.get("areaName") or [{}])[0].get("value", ""),
        "region": (nearest.get("region") or [{}])[0].get("value", ""),
        "country": (nearest.get("country") or [{}])[0].get("value", ""),
        "temperature": float(cc.get("temp_C", 0)),
        "feels_like": float(cc.get("FeelsLikeC", 0)),
        "humidity": int(cc.get("humidity", 0)),
        "description": (cc.get("weatherDesc") or [{}])[0].get("value", ""),
        "wind_speed": float(cc.get("windspeedKmph", 0)),
        "wind_direction": cc.get("winddir16Point", ""),
        "observation_time": ot, "observation_time_24h": ot_24h,
        "observation_time_timestamp": ot_ts,
        "temperature_unit_system": "Celsius",
        "sunrise": sr, "sunrise_24h": sr_24h, "sunrise_timestamp": sr_ts,
        "sunset": ss, "sunset_24h": ss_24h, "sunset_timestamp": ss_ts,
    }


def _weather_openmeteo(lat, lon):
    url = (f"https://api.open-meteo.com/v1/forecast"
           f"?latitude={lat}&longitude={lon}"
           f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
           f"weather_code,wind_speed_10m,wind_direction_10m"
           f"&daily=sunrise,sunset&timezone=auto&forecast_days=1")
    r = urllib.request.urlopen(url, timeout=10)
    data = json.loads(r.read().decode())
    cur = data.get("current", {})
    daily = data.get("daily", {})
    sunrise = (daily.get("sunrise") or [""])[0]
    sunset = (daily.get("sunset") or [""])[0]
    desc = _WMO.get(int(cur.get("weather_code", 0)), "N/A")
    wind_dir = _degrees_compass(cur.get("wind_direction_10m", 0))
    sr, sr_24h, sr_ts = _parse_time_variants(re.sub(r"T", " ", sunrise) if sunrise else "")
    ss, ss_24h, ss_ts = _parse_time_variants(re.sub(r"T", " ", sunset) if sunset else "")
    obs_ts = int(time.time())
    return {
        "city": "", "region": "", "country": "",
        "temperature": cur.get("temperature_2m", 0),
        "feels_like": cur.get("apparent_temperature", 0),
        "humidity": cur.get("relative_humidity_2m", 0),
        "description": desc,
        "wind_speed": cur.get("wind_speed_10m", 0),
        "wind_direction": wind_dir,
        "observation_time": time.strftime("%I:%M %p", time.localtime(obs_ts)),
        "observation_time_24h": time.strftime("%H:%M", time.localtime(obs_ts)),
        "observation_time_timestamp": str(obs_ts),
        "temperature_unit_system": "Celsius",
        "sunrise": sr, "sunrise_24h": sr_24h, "sunrise_timestamp": sr_ts,
        "sunset": ss, "sunset_24h": ss_24h, "sunset_timestamp": ss_ts,
    }


def _weather_metno(lat, lon):
    url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}"
    req = urllib.request.Request(url, headers={"User-Agent": "VASS/0.5 github.com/logicheneurali/vass"})
    r = urllib.request.urlopen(req, timeout=10)
    data = json.loads(r.read().decode())
    ts = data.get("properties", {}).get("timeseries", [])
    if not ts:
        raise RuntimeError("No timeseries data")
    inst = ts[0].get("data", {}).get("instant", {}).get("details", {})
    temp_c = inst.get("air_temperature", 0)
    sym = ts[0].get("data", {}).get("next_1_hours", {}).get("summary", {}).get("symbol_code", "")
    desc = sym.replace("_", " ").title() if sym else "N/A"
    sun = ts[0].get("data", {}).get("next_6_hours", {}).get("details", {})
    sr, sr_24h, sr_ts = _parse_time_variants(re.sub(r"T", " ", sun.get("sunrise", "")))
    ss, ss_24h, ss_ts = _parse_time_variants(re.sub(r"T", " ", sun.get("sunset", "")))
    obs_ts = int(time.time())
    return {
        "city": "", "region": "", "country": "",
        "temperature": temp_c, "feels_like": temp_c,
        "humidity": inst.get("relative_humidity", 0),
        "description": desc,
        "wind_speed": inst.get("wind_speed", 0) * 3.6,
        "wind_direction": _degrees_compass(inst.get("wind_from_direction", 0)),
        "observation_time": time.strftime("%I:%M %p", time.localtime(obs_ts)),
        "observation_time_24h": time.strftime("%H:%M", time.localtime(obs_ts)),
        "observation_time_timestamp": str(obs_ts),
        "temperature_unit_system": "Celsius",
        "sunrise": sr, "sunrise_24h": sr_24h, "sunrise_timestamp": sr_ts,
        "sunset": ss, "sunset_24h": ss_24h, "sunset_timestamp": ss_ts,
    }


def get_weather(location: str):
    """Current weather for a location. Returns a compact dict or None."""
    if not location or not location.strip():
        return {"error": "empty location"}
    key = location.strip().lower()
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]

    coords = resolve_coordinates(location)
    result = None
    if coords:
        lat, lon, _ = coords
        for fn in (_weather_openmeteo, _weather_metno):
            try:
                result = fn(lat, lon)
                if result:
                    break
            except Exception:
                continue
    if result is None:
        try:
            result = _weather_wttr(location)
        except Exception:
            result = None
    if result is None:
        return {"error": "all weather sources failed", "location": location}

    # Fill city/region/country when the coordinate sources leave them empty.
    if coords and not result.get("city"):
        result["city"] = location
        result["country"] = coords[2]
    result["location"] = location
    _cache[key] = (now, result)
    return result
