# 公网 API 与深度链接参考

本 skill 全部使用**免 API Key** 的公开服务。本文件是 `enrich.py` 背后的接口说明与排障指南，需要调整数据源或 URL 模式时读取。

## 目录
- 天气 / 地理编码：Open-Meteo
- 驾车路线：OSRM
- 酒店 / 地图深度链接（携程 / 高德 / 百度）
- 沙箱连通性与排障
- WMO 天气代码对照

## 天气 / 地理编码：Open-Meteo（无需 Key）

- 地理编码（城市名 → 经纬度）：
  `https://geocoding-api.open-meteo.com/v1/search?name={城市}&count=10&language=zh&format=json`
  返回 `results[]`。`enrich.py` 取 `count=10` 后**优先中国(CN)结果、按人口从高到低**选一个（裸名如"大连"会把同名小村排前面）；裸名查不到有人口的地方会自动追加"市"重试。仅到城市级，POI（如"星海广场"）不一定命中。
- 逐日预报：
  `https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,weathercode,precipitation_probability_max&timezone=Asia/Shanghai&start_date={YYYY-MM-DD}&end_date={YYYY-MM-DD}`
- **限制**：预报只在**约 16 天内**准确。出行日期超出范围时，`enrich.py` 会在 `notes` 里提示，此时应改用季节气候常识补充，并在手帐里注明“气候均值，非精确预报”。

## 驾车路线：OSRM demo（无需 Key）

- `https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false`
- 返回 `routes[0].distance`（米）、`routes[0].duration`（秒）。`enrich.py` 换算成 km / 分钟。
- 只吃**经纬度**，不吃地名。`enrich.py` 会先解析端点坐标：优先用调用方给的 `from_lonlat`/`to_lonlat`，否则用 Open-Meteo 地理编码把城市名兜底成坐标（仅城市级）。
- 是公益 demo 服务器，偶发限流；失败时用打车常识估算并注明。

## 酒店 / 地图深度链接（携程 / 高德 / 百度，无需 Key）

`enrich.py` 的 `deep_links()` 生成以下**搜索入口链接**，用户在手机点击后跳转 App / 网页看**实时房价与真实房源**（skill 本身不解析房价）：

| 平台 | URL 模式 | 说明 |
| --- | --- | --- |
| 百度地图 | `https://map.baidu.com/search/{城市酒店}` | 打开地图搜周边酒店 |
| 高德地图 | `https://uri.amap.com/search?keyword={城市酒店}&city={城市}` | 高德官方 URI，唤起 App/网页 |
| 携程目的地 | `https://you.ctrip.com/searchsite/?query={城市酒店}` | 携程站内搜索 |
| 携程酒店列表 | `https://hotels.ctrip.com/hotels/list?city=&keyword={城市酒店}&checkin={YYYYMMDD}&checkout={YYYYMMDD}` | 带入住/离店日期 |

- 所有关键词都要 `urllib.parse.quote` 转义。日期格式化为 `YYYYMMDD`。
- 这些是**入口链接**，不保证深链到某具体酒店；房价、可订状态以 App 实时为准。手帐里应写“点链接看实时房价”。
- 需要更结构化的酒店 POI（名称/评分/坐标）时，需用户提供高德 Web 服务 Key，另行扩展；本版不含。

## 沙箱连通性与排障

- 已验证在本沙箱可达：`geocoding-api.open-meteo.com`、`api.open-meteo.com`、`router.project-osrm.org`。
- 可能被限：`nominatim.openstreetmap.org`（常返回空）、`overpass-api.de`（返回 406）。因此地理编码统一用 Open-Meteo，不依赖 OSM。
- 深度链接是给**用户手机**用的，不需要沙箱能打开；沙箱内 curl 打不开不代表链接无效。
- API 全部失败时，不要编造数据：用季节气候/打车常识补充并在手帐与回复中注明来源与不确定性。

## WMO 天气代码对照（Open-Meteo weathercode）

0 晴 / 1 多云转晴 / 2 多云 / 3 阴 / 45,48 雾 / 51-55 毛毛雨 / 61-65 雨（小中大）/ 66-67 冻雨 / 71-77 雪 / 80-82 阵雨 / 85-86 阵雪 / 95-99 雷阵雨（含冰雹）。`enrich.py` 内含完整映射与 emoji。
