---
name: travel-journal-maker
description: 把用户的旅行/旅游计划做成「手帐」风格的移动端长图。触发场景：用户说"做旅行手帐""旅游行程手帐""把旅行计划做成图片/长图""帮我把XX几日游整理成手帐"等。会用免 API Key 的公网服务自动丰富内容：天气与穿衣（Open-Meteo）、驾车时长/距离（OSRM）、酒店搜索深度链接（携程/高德/百度，点击直达App看实时房价），最终用纯标准库把手帐渲染成一张移动端 SVG 长图（无需浏览器、无需第三方库）。
---

# 旅行手帐生成器

把一段旅行计划变成一张精致的移动端「手帐」长图。**零外部依赖**：内容增强只用免 API Key 的公开服务；渲染只用 Python 标准库生成 SVG，**不需要浏览器(chromium)、不需要第三方库(Pillow)、不改动系统环境**。

## 工作流

### 1. 收集行程信息
从用户 query 中提取以下要素；缺失的用常识补全或简要追问（不要为可推断的小事反复打断用户）：
- 目的地城市（可多个）
- 出行日期范围（入住首日 / 离店末日）
- 天数与每日大致安排（景点、活动、餐饮节奏）
- 出行方式偏好、同行人、特别偏好（可选）

### 2. 运行内容增强脚本
把行程要素拼成 plan JSON，运行 `scripts/enrich.py` 获取天气、路线、酒店深链：

```bash
python3 scripts/enrich.py '{"trip_title":"大连四日游","cities":["大连"],"dates":["2026-10-04","2026-10-07"],"routes":[{"from":"大连北站","to":"星海广场"}]}'
```

- 输出 JSON 含 `weather`（逐日天气+emoji）、`hotels`（携程/高德/百度搜索深链）、`routes`（驾车 km/分钟）、`notes`（数据可用性提示）。
- 天气预报仅约 16 天内准确；`notes` 若提示超范围，改用季节气候均值补充，并在手帐里注明"气候均值，非精确预报"。
- `routes` 的端点**坐标可给可不给**：给 `from_lonlat`/`to_lonlat`（`[lon,lat]`）最准；不给时用城市名自动地理编码兜底（仅城市级，POI 会偏，`note` 注明）；都拿不到就用打车常识估算并注明。
- API/深链细节与排障见 `references/apis-and-deeplinks.md`。

### 3. 填充手帐数据（journal.json）
把行程叙事 + 第 2 步的增强结果，合并成一个 `journal.json`。字段结构（可参考 `examples/sample_journal.json`）：

```jsonc
{
  "trip_title": "大连四日游",
  "en_tagline": "DALIAN TRAVEL 2026",       // 封面英文小标签
  "title_lines": ["大连", "海风四日慢游手帐"], // 封面主标题(可多行)
  "subtitle": "2026.09.26 – 09.29 · 一句话定位",
  "tags": ["海滨城市", "慢节奏", "海鲜控"],
  "days": [                                  // 每天一张卡片，配色 b1~b5 自动循环
    {"date_num":"26","weekday":"周六","theme":"抵达 · 海边初见","pace":"轻松踩点",
     "items":[{"time":"14:00","emoji":"🚄","title":"抵达大连北站","note":"地铁转酒店"}]}
  ],
  "weather": [                               // 用 enrich 的 weather 填(温度取整、加穿衣建议)
    {"date":"09-26","emoji":"☁️","desc":"阴","tmin":21,"tmax":26,"advice":"长袖+薄外套"}
  ],
  "weather_tip": "早晚温差大、海边风大…（数据来源与不确定性说明）",
  "hotels": [                                // 用 enrich 的 hotels 深链
    {"area":"星海广场片区","feature":"看海、离景点近",
     "links":{"携程":"<深链>","高德/百度":"<深链>"}}
  ],
  "info_cards": [                            // 可选:交通/美食等自定义卡片
    {"title":"🚗 交通提示","rows":[{"k":"大连北站→星海","v":"约 37.9km · 35 分钟"}],
     "tip":"旅顺方向公共交通少，建议打车。"}
  ],
  "footer": "✎ 用心整理 · 祝旅途愉快"
}
```

### 4. 渲染长图（纯标准库，无浏览器）
```bash
python3 scripts/render_journal.py journal.json out.svg [--png out.png]
```
- 产出自包含的 **`out.svg`** 移动端长图（480 宽，高度自适应），可直接在浏览器/预览打开看全图，也可作分享图。
- `--png` 为**可选**：仅当系统恰好装有 `rsvg-convert` / `cairosvg` / `inkscape`（或 macOS 自带 `qlmanage`，注意 `qlmanage` 对超长图会裁剪）时才导出 PNG；没有这些工具会静默跳过，仍保留 SVG。**不要为了 PNG 去装浏览器**。

### 5. 交付
- 直接把 `out.svg`（及可选 `out.png`）交给用户：给出文件路径，SVG 用浏览器/预览即可查看全图。
- 若需要公网链接，再按用户所在环境选择上传方式（本 skill 不绑定任何特定上传工具）。
- 最终回复中说明**数据来源与不确定性**：天气/路线来自公开 API，酒店是搜索入口链接、房价以 App 实时为准；超预报范围或坐标缺失处已按常识补充并注明。

## 参考资料
- **公网 API 与深度链接**（Open-Meteo / OSRM / 携程高德百度深链 / 沙箱连通性 / WMO 天气码）：见 `references/apis-and-deeplinks.md`
- **示例**：`examples/sample_journal.json`（输入）+ `examples/sample.svg`（渲染结果）。
