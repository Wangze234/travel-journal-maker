#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enrich.py — 旅行手帐内容增强器（全部使用免 Key 公网 API / 深度链接）

数据来源（均无需 API Key）：
  - 天气 / 地理编码: Open-Meteo (https://open-meteo.com)
  - 驾车路线时长距离: OSRM demo server (https://router.project-osrm.org)
  - 酒店/地图: 携程 / 高德 / 百度地图 深度搜索链接（用户点击后在 App / 网页看实时房价）

用法:
  python3 enrich.py '<plan_json>'          # 直接传 JSON 字符串
  python3 enrich.py --file plan.json       # 从文件读取
  echo '<plan_json>' | python3 enrich.py   # 从 stdin 读取

输入 plan JSON 结构（字段均可选，尽量提供 cities/dates）:
{
  "trip_title": "大连四日游",
  "cities": ["大连"],                     # 目的地城市（用于天气/酒店）
  "dates": ["2026-10-04", "2026-10-07"],  # [入住/首日, 离店/末日]，用于天气与酒店 checkin/checkout
  "routes": [                              # 可选：需要计算驾车时长的点对（经纬度或城市名）
    {"from": "大连北站", "from_lonlat": [121.79,39.03], "to": "星海广场", "to_lonlat": [121.53,38.88]}
  ]
}

输出: JSON（stdout），包含 weather / hotels / routes / notes 字段，供填充手帐模板。
"""
import sys, json, urllib.parse, urllib.request, datetime

TIMEOUT = 15
UA = "travel-journal-maker/1.0"

WMO = {
    0: ("晴", "☀️"), 1: ("多云转晴", "🌤"), 2: ("多云", "⛅"), 3: ("阴", "☁️"),
    45: ("雾", "🌫"), 48: ("雾凇", "🌫"),
    51: ("小毛雨", "🌦"), 53: ("毛毛雨", "🌦"), 55: ("大毛雨", "🌧"),
    61: ("小雨", "🌦"), 63: ("中雨", "🌧"), 65: ("大雨", "🌧"),
    66: ("冻雨", "🌧"), 67: ("强冻雨", "🌧"),
    71: ("小雪", "🌨"), 73: ("中雪", "🌨"), 75: ("大雪", "❄️"), 77: ("雪粒", "🌨"),
    80: ("阵雨", "🌦"), 81: ("中阵雨", "🌧"), 82: ("强阵雨", "⛈"),
    85: ("阵雪", "🌨"), 86: ("强阵雪", "❄️"),
    95: ("雷阵雨", "⛈"), 96: ("雷阵雨伴冰雹", "⛈"), 99: ("强雷雨冰雹", "⛈"),
}


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _geo_query(name):
    """单次地理编码查询，返回候选列表（原始 dict）。"""
    try:
        u = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
            {"name": name, "count": 10, "language": "zh", "format": "json"})
        return http_get(u).get("results") or []
    except Exception as e:
        sys.stderr.write(f"[geocode] {name}: {e}\n")
        return []


def geocode(city):
    """用 Open-Meteo 地理编码，返回 (lat, lon, 名称) 或 None。
    Open-Meteo 对裸城市名（如"大连"）会把同名小村排在真实城市前面，
    因此：优先中国(CN)结果，并按人口从高到低选取；若裸名查不到有人口的地方，
    自动追加"市"重试，尽量命中地级市。"""
    candidates = _geo_query(city)
    if not any((r.get("population") or 0) > 0 for r in candidates) and not city.endswith(("市", "县", "区")):
        candidates = _geo_query(city + "市") or candidates
    if not candidates:
        return None
    cn = [r for r in candidates if r.get("country_code") == "CN"] or candidates
    r = max(cn, key=lambda x: x.get("population") or 0)
    return (r["latitude"], r["longitude"], r.get("name", city))


def weather_for(city, start=None, end=None):
    """返回城市的逐日天气预报（Open-Meteo，最多约16天内准确；超出范围返回 note）。"""
    g = geocode(city)
    if not g:
        return {"city": city, "ok": False, "note": "未能定位该城市坐标"}
    lat, lon, name = g
    params = {
        "latitude": lat, "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,weathercode,precipitation_probability_max",
        "timezone": "Asia/Shanghai",
    }
    if start and end:
        params["start_date"] = start
        params["end_date"] = end
    else:
        params["forecast_days"] = 7
    try:
        d = http_get("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params))
        daily = d.get("daily", {})
        days = []
        for i, day in enumerate(daily.get("time", [])):
            code = daily["weathercode"][i]
            desc, emoji = WMO.get(code, ("未知", "🌡"))
            days.append({
                "date": day,
                "tmax": daily["temperature_2m_max"][i],
                "tmin": daily["temperature_2m_min"][i],
                "desc": desc, "emoji": emoji,
                "pop": (daily.get("precipitation_probability_max") or [None])[i]
                       if daily.get("precipitation_probability_max") else None,
            })
        return {"city": name, "lat": lat, "lon": lon, "ok": True, "days": days}
    except Exception as e:
        sys.stderr.write(f"[weather] {city}: {e}\n")
        return {"city": name, "lat": lat, "lon": lon, "ok": False,
                "note": "预报超出可用范围（约16天）或接口异常，请用季节气候常识补充"}


def resolve_lonlat(point_name, given):
    """把路线端点解析成 [lon, lat]:优先用调用方给的坐标，否则用地理编码兜底。"""
    if given and len(given) == 2:
        return list(given), False
    if not point_name:
        return None, False
    g = geocode(point_name)
    if g:
        lat, lon, _ = g
        return [lon, lat], True   # 地理编码只到城市级，POI 会有偏差
    return None, False


def osrm_route(from_lonlat, to_lonlat):
    """OSRM 驾车路线：返回 {distance_km, duration_min}。经纬度为 [lon, lat]。"""
    try:
        coords = f"{from_lonlat[0]},{from_lonlat[1]};{to_lonlat[0]},{to_lonlat[1]}"
        u = f"https://router.project-osrm.org/route/v1/driving/{coords}?overview=false"
        d = http_get(u)
        if d.get("code") == "Ok" and d.get("routes"):
            r = d["routes"][0]
            return {"distance_km": round(r["distance"] / 1000, 1),
                    "duration_min": round(r["duration"] / 60)}
    except Exception as e:
        sys.stderr.write(f"[osrm] {e}\n")
    return None


def deep_links(city, checkin=None, checkout=None):
    """生成携程 / 高德 / 百度地图 酒店搜索深度链接（无需 Key，用户点击直达）。"""
    q = urllib.parse.quote(f"{city}酒店")
    cq = urllib.parse.quote(city)
    links = {
        "百度地图_酒店搜索": f"https://map.baidu.com/search/{q}",
        "高德地图_酒店搜索": f"https://uri.amap.com/search?keyword={q}&city={cq}",
        "携程_目的地搜索": f"https://you.ctrip.com/searchsite/?query={q}",
    }
    ctrip_hotel = f"https://hotels.ctrip.com/hotels/list?city=&keyword={q}"
    if checkin and checkout:
        ci = checkin.replace("-", "")
        co = checkout.replace("-", "")
        ctrip_hotel += f"&checkin={ci}&checkout={co}"
    links["携程_酒店列表"] = ctrip_hotel
    return links


def main():
    raw = None
    args = sys.argv[1:]
    if args and args[0] == "--file":
        if len(args) < 2:
            sys.exit("用法: enrich.py --file plan.json")
        with open(args[1], "r", encoding="utf-8") as f:
            raw = f.read()
    elif args:
        raw = args[0]
    else:
        raw = sys.stdin.read()
    plan = json.loads(raw)

    cities = plan.get("cities") or []
    dates = plan.get("dates") or []
    checkin = dates[0] if len(dates) >= 1 else None
    checkout = dates[-1] if len(dates) >= 2 else None

    out = {"generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
           "weather": [], "hotels": [], "routes": [], "notes": []}

    for c in cities:
        out["weather"].append(weather_for(c, checkin, checkout))
        out["hotels"].append({"city": c, "links": deep_links(c, checkin, checkout)})

    for r in plan.get("routes", []):
        fl, from_geo = resolve_lonlat(r.get("from"), r.get("from_lonlat"))
        tl, to_geo = resolve_lonlat(r.get("to"), r.get("to_lonlat"))
        route = osrm_route(fl, tl) if (fl and tl) else None
        if route:
            note = "端点坐标由城市名地理编码估算，仅到城市级、非精确门到门" \
                if (from_geo or to_geo) else None
        else:
            note = "缺少可用坐标或路线接口不可用，可用打车常识估算"
        out["routes"].append({"from": r.get("from"), "to": r.get("to"),
                              "result": route, "note": note})

    if checkin and checkout:
        try:
            d0 = datetime.date.fromisoformat(checkin)
            if (d0 - datetime.date.today()).days > 15:
                out["notes"].append("出行日期距今超过约16天，Open-Meteo 无法给出精确预报，天气以季节气候均值补充并注明。")
        except Exception:
            pass

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
