# travel-journal-maker · 旅行手帐生成器

把一段旅行计划变成一张精致的移动端「手帐」风格长图。

**核心特色:零外部依赖。** 内容增强只用**免 API Key** 的公开服务;渲染只用 **Python 标准库**生成 SVG——不需要浏览器(chromium)、不需要第三方库(Pillow)、不改动系统环境。

## 能解决什么问题

用户手里有一份零散的旅行行程(去哪、几天、每天玩什么),想快速整理成一张好看、可分享、信息完整的手帐图。这个 skill 会自动:

- **丰富内容**:补全逐日天气与穿衣建议、驾车时长/距离、酒店搜索深度链接
- **排版渲染**:把行程叙事排成移动端长图,封面 + 每日卡片 + 天气 + 酒店 + 自定义信息卡
- **一键交付**:产出自包含 SVG(可选 PNG),浏览器/预览直接打开即可查看或分享

## 触发场景

当用户说这类话时会用到:

- "做旅行手帐" / "旅游行程手帐"
- "把旅行计划做成图片/长图"
- "帮我把大连四日游整理成手帐"

## 能力构成

| 能力 | 说明 | 数据来源 |
|------|------|----------|
| 逐日天气 + 穿衣建议 | 温度、天气 emoji、着装提示 | [Open-Meteo](https://open-meteo.com/)(免 Key) |
| 驾车路线 | 两点间 km / 分钟 | [OSRM](http://project-osrm.org/)(免 Key) |
| 酒店深度链接 | 携程/高德/百度搜索深链,点击直达 App 看实时房价 | 深链构造(见 references) |
| 手帐渲染 | 480 宽移动端 SVG 长图,配色卡片自动循环 | Python 标准库,无浏览器 |

## 工作流

1. **收集行程信息**:目的地、日期范围、每日安排、出行偏好(缺失项用常识补全或简要追问)
2. **运行内容增强**:`scripts/enrich.py` 获取天气/路线/酒店深链
   ```bash
   python3 scripts/enrich.py '{"trip_title":"大连四日游","cities":["大连"],"dates":["2026-10-04","2026-10-07"],"routes":[{"from":"大连北站","to":"星海广场"}]}'
   ```
3. **填充手帐数据**:把行程叙事 + 增强结果合并成 `journal.json`(结构见 [examples/sample_journal.json](examples/sample_journal.json))
4. **渲染长图**:
   ```bash
   python3 scripts/render_journal.py journal.json out.svg [--png out.png]
   ```
   - 产出自包含的 `out.svg`(高度自适应),浏览器/预览可看全图
   - `--png` 可选,仅当系统装有 `rsvg-convert`/`cairosvg`/`inkscape` 时导出,否则静默跳过
5. **交付**:给出文件路径,并说明数据来源与不确定性(天气/路线来自公开 API,酒店为搜索入口链接、房价以 App 实时为准)

## 目录结构

```
travel-journal-maker/
├── SKILL.md                          # skill 定义与详细工作流
├── scripts/
│   ├── enrich.py                     # 内容增强:天气/路线/酒店深链
│   └── render_journal.py             # 渲染:journal.json → SVG 长图
├── examples/
│   ├── sample_journal.json           # 示例输入
│   ├── enrich_out.json               # enrich 输出示例
│   └── sample.svg                    # 渲染结果示例
└── references/
    └── apis-and-deeplinks.md         # 公网 API 与深链细节、排障、WMO 天气码
```

## 使用须知

- 天气预报仅约 **16 天内**准确;超范围时改用季节气候均值补充,并在手帐里注明"气候均值,非精确预报"
- 路线端点坐标可给可不给:给 `from_lonlat`/`to_lonlat` 最准,不给时用城市名地理编码兜底(仅城市级)
- 酒店链接是**搜索入口**,实时房价以 App 为准
- 详细 API 说明与排障见 [references/apis-and-deeplinks.md](references/apis-and-deeplinks.md)
