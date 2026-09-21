#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_journal.py — 把旅行手帐 JSON 渲染成移动端 SVG 长图。

设计目标：**零外部依赖**。只用 Python 标准库，不需要浏览器(chromium)、
不需要第三方库(Pillow 等)、不改动系统环境。产出一个自包含 .svg 长图，
可直接在预览/浏览器中查看，也可当作分享图。

可选：若系统恰好装有 rsvg-convert / inkscape / cairosvg / (macOS)qlmanage，
用 --png 可顺带导出一张 PNG；没有这些工具时静默跳过，仍保留 SVG。

用法:
  python3 render_journal.py journal.json out.svg [--png out.png]
  cat journal.json | python3 render_journal.py - out.svg

journal.json 结构见 SKILL.md「填充手帐数据」一节。
"""
import sys, json, argparse, subprocess, shutil, os

W = 480
PAD = 16
CW = W - 2 * PAD  # 内容宽度 448

C = {
    "paper": "#fdf6ec", "ink": "#33302b", "sub": "#8a8478",
    "sea": "#2a7f8f", "sea_d": "#1f5f6b", "coral": "#e9765b",
    "sun": "#f2a950", "leaf": "#5a9e6f", "violet": "#8a6fb0",
    "line": "#e7ddc9", "bg": "#efe7d6", "card": "#ffffff",
}
BADGE = [C["coral"], C["sea"], C["leaf"], C["violet"], C["sun"]]
FONTS = ["PingFang SC", "Hiragino Sans GB", "Heiti SC", "STHeiti",
         "Microsoft YaHei", "Noto Sans CJK SC", "Apple Color Emoji", "sans-serif"]
FONT_CSS = ",".join(f"'{f}'" if " " in f else f for f in FONTS)


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def char_w(ch, fs):
    o = ord(ch)
    if o < 0x2E80:                                    # ASCII / 拉丁 / 半角标点
        return fs * 0.56
    if o >= 0x1F000 or 0x2600 <= o <= 0x27BF:         # emoji 区
        return fs * 1.15
    return fs                                         # CJK 全角


def wrap(text, max_w, fs):
    lines, cur, cw = [], "", 0.0
    for ch in str(text):
        if ch == "\n":
            lines.append(cur); cur, cw = "", 0.0; continue
        w = char_w(ch, fs)
        if cw + w > max_w and cur:
            lines.append(cur); cur, cw = ch, w
        else:
            cur += ch; cw += w
    if cur:
        lines.append(cur)
    return lines or [""]


class Doc:
    """向下堆叠布局的 SVG 构建器；self.y 是当前笔触的纵向游标。"""

    def __init__(self):
        self.el = []
        self.y = 0.0

    def add(self, s):
        self.el.append(s)

    def rrect(self, x, y, w, h, r, fill, stroke=None, sw=1.0, opacity=None):
        s = (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
             f'rx="{r}" ry="{r}" fill="{fill}"')
        if stroke:
            s += f' stroke="{stroke}" stroke-width="{sw}"'
        if opacity is not None:
            s += f' opacity="{opacity}"'
        self.add(s + "/>")

    def shadow(self, x, y, w, h, r):
        """卡片下方的轻微投影(手绘一个偏移暗块，任何查看器都能渲染)。"""
        self.rrect(x, y + 3, w, h, r, "#000000", opacity=0.06)

    def line(self, x1, y1, x2, y2, color, w=1.0, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                 f'stroke="{color}" stroke-width="{w}"{d}/>')

    def circle(self, cx, cy, r, fill, stroke=None, sw=1.0):
        s = f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{fill}"'
        if stroke:
            s += f' stroke="{stroke}" stroke-width="{sw}"'
        self.add(s + "/>")

    def txt(self, x, top, s, fs, fill, weight=400, anchor="start", spacing=None, href=None):
        """按『文字顶端 y=top』放置一行(内部换算基线)。"""
        base = top + fs * 0.82
        extra = f' letter-spacing="{spacing}"' if spacing else ""
        t = (f'<text x="{x:.1f}" y="{base:.1f}" font-size="{fs}" fill="{fill}" '
             f'font-weight="{weight}" text-anchor="{anchor}"{extra}>{esc(s)}</text>')
        if href:
            t = f'<a href="{esc(href)}">{t}</a>'
        self.add(t)

    def paragraph(self, x, top, text, fs, fill, max_w, lh=1.5, weight=400):
        """自动换行段落，返回占用高度。"""
        lines = wrap(text, max_w, fs)
        step = fs * lh
        for i, ln in enumerate(lines):
            self.txt(x, top + i * step + (step - fs) / 2, ln, fs, fill, weight)
        return len(lines) * step


def pill_w(text, fs, padx):
    return sum(char_w(c, fs) for c in str(text)) + 2 * padx


def split_pills(tags, fs, padx, gap, avail):
    rows, row, x = [], [], 0.0
    for tg in tags:
        w = pill_w(tg, fs, padx)
        if row and x + w > avail:
            rows.append(row); row, x = [], 0.0
        row.append((tg, w)); x += w + gap
    if row:
        rows.append(row)
    return rows


def render_cover(d, j):
    top = d.y
    ix = 22
    mw = W - 2 * ix
    tagline = j.get("en_tagline", "")
    titles = j.get("title_lines") or [j.get("trip_title", "旅行手帐")]
    subtitle = j.get("subtitle", "")
    tags = j.get("tags") or []
    sub_lines = wrap(subtitle, mw, 14) if subtitle else []
    tag_rows = split_pills(tags, 12.5, 12, 8, mw) if tags else []

    cur = 34.0
    if tagline:
        cur += 26 + 14
    cur += len(titles) * 38
    if sub_lines:
        cur += 10 + len(sub_lines) * 20
    if tag_rows:
        cur += 16 + len(tag_rows) * 34 - 4
    cover_h = cur + 30

    r = 26
    b = top + cover_h
    d.add(f'<path d="M0,{top:.1f} H{W} V{b - r:.1f} Q{W},{b:.1f} {W - r},{b:.1f} '
          f'H{r} Q0,{b:.1f} 0,{b - r:.1f} Z" fill="url(#cg)"/>')

    cy = top + 34
    if tagline:
        pw = pill_w(tagline, 12, 14)
        d.rrect(ix, cy, pw, 26, 13, "#ffffff", opacity=0.18)
        d.txt(ix + 14, cy + 5, tagline, 12, "#ffffff", spacing=2)
        cy += 26 + 14
    for t in titles:
        d.txt(ix, cy, t, 30, "#ffffff", weight=800, spacing=1)
        cy += 38
    if sub_lines:
        cy += 10
        for ln in sub_lines:
            d.txt(ix, cy, ln, 14, "#e9f3f5")
            cy += 20
    for row in tag_rows:
        cy += 16 if row is tag_rows[0] else 0
        px = ix
        for tg, pw in row:
            d.rrect(px, cy, pw, 30, 15, "#ffffff", opacity=0.16)
            d.txt(px + 12, cy + 7, tg, 12.5, "#ffffff")
            px += pw + 8
        cy += 34
    d.y = top + cover_h + 4


def activity_text(it):
    emoji, title, note = it.get("emoji", ""), it.get("title", ""), it.get("note", "")
    s = (emoji + " " if emoji else "") + title
    if note:
        s += f"（{note}）"
    return s


def render_day(d, day, idx):
    x, w = PAD, CW
    il = x + 16
    ax = il + 70
    max_w = w - 32 - 70
    items = day.get("items") or []
    heights = [max(len(wrap(activity_text(it), max_w, 14)) * 21, 22) for it in items]
    head_h = 18 + 56 + 6
    card_h = head_h + sum(heights) + 6 * len(items) + 8

    top = d.y
    d.shadow(x, top, w, card_h, 18)
    d.rrect(x, top, w, card_h, 18, C["card"], stroke="#f0e8d8", sw=1)

    bc = BADGE[idx % 5]
    d.rrect(il, top + 18, 56, 56, 14, bc)
    d.txt(il + 28, top + 18 + 8, str(day.get("date_num", idx + 1)), 22, "#ffffff",
          weight=800, anchor="middle")
    d.txt(il + 28, top + 18 + 34, day.get("weekday", ""), 11, "#eef6f7", anchor="middle")
    bx = il + 70
    d.txt(bx, top + 18 + 6, day.get("theme", ""), 18, C["ink"], weight=700)
    d.txt(bx, top + 18 + 32, f"Day {idx + 1} · {day.get('pace', '')}", 12.5, C["sub"])

    cy = top + head_h
    for i, it in enumerate(items):
        h = heights[i]
        d.txt(il + 40, cy + 2, it.get("time", ""), 12, C["coral"], weight=700, anchor="end")
        if i < len(items) - 1:
            d.line(il + 52, cy + 16, il + 52, cy + h + 9, C["line"], w=2)
        d.circle(il + 52, cy + 9, 6, C["sea"], stroke="#ffffff", sw=2)
        d.paragraph(ax, cy, activity_text(it), 14, C["ink"], max_w, weight=500)
        cy += h + 6
    d.y = top + card_h + 16


def render_footer(d, text):
    d.y += 8
    d.line(PAD + 8, d.y, W - PAD - 8, d.y, C["line"], w=1, dash="3,3")
    d.txt(W / 2, d.y + 12, text, 12, C["sub"], anchor="middle")
    d.y += 12 + 24


def render_info(d, title, rows, tip=None):
    x, w = PAD, CW
    il = x + 16
    ir = x + w - 16
    vx = il + 92
    vmax = ir - vx
    tip_w = w - 32 - 24

    row_lines = [wrap(r.get("v", ""), vmax, 13.5) for r in rows]
    row_h = [max(len(ls) * 20, 20) + 8 for ls in row_lines]
    tip_lines = wrap(tip, tip_w, 12.5) if tip else []
    tip_h = (len(tip_lines) * 18 + 18 + 10) if tip else 0
    card_h = 16 + 30 + sum(row_h) + tip_h + 12

    top = d.y
    d.shadow(x, top, w, card_h, 18)
    d.rrect(x, top, w, card_h, 18, C["card"], stroke="#f0e8d8", sw=1)

    d.txt(il, top + 16, title, 17, C["sea_d"], weight=700)
    cy = top + 16 + 30
    for i, r in enumerate(rows):
        d.txt(il, cy + 4, r.get("k", ""), 13.5, C["sea"], weight=600)
        color = C["coral"] if r.get("href") else C["ink"]
        yy = cy
        for ln in row_lines[i]:
            d.txt(vx, yy + 4, ln, 13.5, color, href=r.get("href"))
            yy += 20
        cy += row_h[i]
        if i < len(rows) - 1:
            d.line(il, cy - 4, ir, cy - 4, C["line"], w=1, dash="3,3")
    if tip:
        ty = cy + 4
        th = len(tip_lines) * 18 + 16
        d.rrect(x + 8, ty, w - 16, th, 8, "#fff8ee")
        d.rrect(x + 8, ty, 3, th, 1, C["sun"])
        for k, ln in enumerate(tip_lines):
            d.txt(x + 20, ty + 8 + k * 18, ln, 12.5, "#7a6a4d")
    d.y = top + card_h + 16


def build_svg(j):
    d = Doc()
    render_cover(d, j)
    for i, day in enumerate(j.get("days") or []):
        render_day(d, day, i)

    weather = j.get("weather") or []
    if weather:
        rows = []
        for wd in weather:
            v = f"{wd.get('emoji', '')}{wd.get('desc', '')} " \
                f"{wd.get('tmin', '')}~{wd.get('tmax', '')}℃"
            if wd.get("advice"):
                v += f" · {wd['advice']}"
            rows.append({"k": wd.get("date", ""), "v": v})
        render_info(d, "🌤 天气 & 穿衣", rows, j.get("weather_tip"))

    for h in j.get("hotels") or []:
        rows = []
        if h.get("area") or h.get("feature"):
            rows.append({"k": h.get("area", "片区"), "v": h.get("feature", "")})
        for name, link in (h.get("links") or {}).items():
            rows.append({"k": name, "v": f"打开{name}看实时房价 →", "href": link})
        render_info(d, "🏨 住宿 · 点链接看实时房价", rows)

    for card in j.get("info_cards") or []:
        rows = [{"k": r.get("k", ""), "v": r.get("v", ""), "href": r.get("href")}
                for r in card.get("rows") or []]
        render_info(d, card.get("title", ""), rows, card.get("tip"))

    render_footer(d, j.get("footer", "✎ 用心整理 · 祝旅途愉快"))

    H = d.y + 8
    defs = ('<defs>'
            '<linearGradient id="cg" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0" stop-color="#2a7f8f"/>'
            '<stop offset="0.7" stop-color="#1f5f6b"/>'
            '<stop offset="1" stop-color="#17454f"/></linearGradient>'
            '<pattern id="dots" width="16" height="16" patternUnits="userSpaceOnUse">'
            '<circle cx="1" cy="1" r="0.6" fill="#e7ddc9"/></pattern></defs>')
    bg = (f'<rect width="{W}" height="{H:.0f}" fill="{C["paper"]}"/>'
          f'<rect width="{W}" height="{H:.0f}" fill="url(#dots)"/>')
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{W}" height="{H:.0f}" viewBox="0 0 {W} {H:.0f}" '
            f'font-family="{FONT_CSS}">')
    return head + defs + bg + "".join(d.el) + "</svg>"


def to_png(svg_path, png_path):
    """尽力而为地把 SVG 转 PNG；找不到任何工具就返回 None(仍保留 SVG)。"""
    if shutil.which("rsvg-convert"):
        if subprocess.run(["rsvg-convert", "-o", png_path, svg_path]).returncode == 0:
            return "rsvg-convert"
    if shutil.which("cairosvg"):
        if subprocess.run(["cairosvg", svg_path, "-o", png_path]).returncode == 0:
            return "cairosvg"
    if shutil.which("inkscape"):
        if subprocess.run(["inkscape", svg_path, "--export-type=png",
                           f"--export-filename={png_path}"]).returncode == 0:
            return "inkscape"
    if shutil.which("qlmanage"):  # macOS 自带
        outdir = os.path.dirname(os.path.abspath(png_path)) or "."
        subprocess.run(["qlmanage", "-t", "-s", "960", "-o", outdir, svg_path],
                       capture_output=True)
        produced = os.path.join(outdir, os.path.basename(svg_path) + ".png")
        if os.path.exists(produced):
            os.replace(produced, png_path)
            return "qlmanage"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("journal", help="journal JSON 路径，或 - 表示 stdin")
    ap.add_argument("out_svg")
    ap.add_argument("--png", help="可选:同时导出 PNG(需系统有转换工具)")
    a = ap.parse_args()

    raw = sys.stdin.read() if a.journal == "-" else open(a.journal, encoding="utf-8").read()
    svg = build_svg(json.loads(raw))
    with open(a.out_svg, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"OK svg -> {a.out_svg}")
    if a.png:
        via = to_png(a.out_svg, a.png)
        if via:
            print(f"OK png -> {a.png} (via {via})")
        else:
            print("[warn] 未找到 SVG→PNG 转换工具，仅输出 SVG(可直接在浏览器/预览中查看)")


if __name__ == "__main__":
    main()
