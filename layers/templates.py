"""HTML templates for overlay layers. Each returns (css, body). Colours come from CSS variables
set from the brand (see render.py). Text fields may contain <b> for the accent colour and <br>."""

def _bg():
    return ("background: radial-gradient(1200px 900px at 50% 40%, var(--bg-0) 0%, var(--bg-1) 55%, "
            "var(--bg-2) 100%);")

def window(edit, brand, size):
    w = edit["window"]
    icon = (f'<div class="ext"><img src="{brand["toolbarIcon"]}"></div>' if brand.get("toolbarIcon") else "")
    pix = "image-rendering: pixelated;" if brand.get("pixelated") else ""
    css = f"""
body {{ {_bg()} }}
.win {{ position: absolute; left: {w['x']}px; top: {w['y']}px; width: {w['w']}px; height: {w['h']}px;
       border-radius: {w['r']}px; background: #fff;
       box-shadow: 0 2px 3px rgba(13,40,38,.10), 0 18px 40px -8px rgba(13,40,38,.22),
                   0 50px 90px -30px rgba(13,60,56,.30); }}
.bar {{ position: absolute; left: 0; right: 0; top: 0; height: {w['bar']}px; border-radius: {w['r']}px {w['r']}px 0 0;
       background: linear-gradient(#f7f8f9, #eef0f2); border-bottom: 1px solid #dfe3e6; }}
.dots {{ position: absolute; left: 22px; top: {w['bar'] // 2 - 7}px; display: flex; gap: 9px; }}
.dots i {{ width: 14px; height: 14px; border-radius: 50%; display: block; }}
.url {{ position: absolute; left: 50%; top: {w['bar'] // 2 - 15}px; transform: translateX(-50%); height: 30px;
       max-width: {w['w'] - 240}px; padding: 0 22px; border-radius: 9px; background: #fff; border: 1px solid #e1e5e8;
       font-size: 15px; color: #5b6470; display: flex; align-items: center; gap: 8px; white-space: nowrap; overflow: hidden; }}
.url svg {{ width: 12px; height: 12px; flex: none; }}
.ext {{ position: absolute; right: 18px; top: {w['bar'] // 2 - 14}px; width: 28px; height: 28px; border-radius: 8px;
       background: color-mix(in srgb, var(--accent-2) 18%, white); display: flex; align-items: center; justify-content: center; }}
.ext img {{ width: 20px; {pix} }}
"""
    lock = ('<svg viewBox="0 0 12 12"><rect x="2" y="5.2" width="8" height="5.8" rx="1.3" fill="#7b8490"/>'
            '<path d="M4 5.5V3.8a2 2 0 0 1 4 0v1.7" stroke="#7b8490" stroke-width="1.4" fill="none"/></svg>')
    body = (f'<div class="win"><div class="bar"><div class="dots"><i style="background:#ff5f57"></i>'
            f'<i style="background:#febc2e"></i><i style="background:#28c840"></i></div>'
            f'<div class="url">{lock}{w.get("url", "")}</div>{icon}</div></div>')
    return css, body

def caption(c, brand, size, lay=None):
    L = {"left": 64, "top": 76, "width": size[0] - 128, "height": 250, "size": 58, "align": "left",
         **((lay or {}).get("caption", {}))}
    top = c.get("top", L["top"])
    css = f"""
.cap {{ position: absolute; left: {L['left']}px; top: {top}px; width: {L['width']}px; height: {L['height']}px;
       display: flex; flex-direction: column; justify-content: center; text-align: {L['align']}; }}
.kick {{ font-weight: 600; font-size: {round(L['size'] * 0.38)}px; line-height: 1; letter-spacing: 3px; color: var(--accent);
        text-transform: uppercase; margin-bottom: {round(L['size'] * 0.31)}px; display: flex; align-items: center; gap: 14px; }}
.kick::before {{ content: ""; width: 34px; height: 3px; border-radius: 2px; background: var(--accent-2); }}
h2 {{ margin: 0; font-size: {c.get('size', L['size'])}px; line-height: 1.12; letter-spacing: -1.4px; font-weight: 700; }}
"""
    kick = f'<div class="kick mono">{c["kicker"]}</div>' if c.get("kicker") else ""
    return css, f'<div class="cap">{kick}<h2>{c["text"]}</h2></div>'

def toast(k, brand, size, lay=None):
    T = {"bottom": 112, **((lay or {}).get("toast", {}))}
    left = f"{T['cx']}px" if "cx" in T else "50%"
    css = f"""
.t {{ position: absolute; left: {left}; bottom: {k.get('bottom', T['bottom'])}px; transform: translateX(-50%); display: flex;
     align-items: center; gap: 14px; padding: 16px 26px 16px 18px; background: rgba(22,24,29,.92); color: #fff;
     border-radius: 18px; font-size: 30px; font-weight: 500; box-shadow: 0 12px 30px -6px rgba(0,0,0,.35); white-space: nowrap; }}
kbd {{ font: 700 30px/1 -apple-system, sans-serif; color: #16181d; background: linear-gradient(#fff, #e9ecef);
      border-radius: 10px; padding: 10px 16px; box-shadow: 0 3px 0 #b8bec5; }}
.plus {{ color: #9aa3ad; }}
"""
    keys = '<span class="plus">+</span>'.join(f"<kbd>{x}</kbd>" for x in k.get("keys", []))
    label = f'<span style="margin-left:8px">{k["text"]}</span>' if k.get("text") else ""
    return css, f'<div class="t">{keys}{label}</div>'

def _logo(brand, width):
    if not brand.get("logo"): return ""
    pix = "image-rendering: pixelated;" if brand.get("pixelated") else ""
    return f'<img class="logo" src="{brand["logo"]}" style="width:{width}px;{pix}">'

def title(s, brand, size):
    t = s.get("title", {})
    css = f"""
body {{ {_bg()} display: flex; flex-direction: column; align-items: center; justify-content: center; }}
.logo {{ margin-bottom: 52px; }}
h1 {{ font-size: 120px; margin: 0; letter-spacing: -3px; display: flex; align-items: baseline; }}
h1 span {{ font-family: {t.get('altFont', 'inherit')}; color: var(--accent); font-weight: 600; margin-left: 30px; }}
.badge {{ margin-top: 30px; font-weight: 600; font-size: 26px; line-height: 1; letter-spacing: 3px; color: #fff;
         background: var(--accent); padding: 12px 20px; border-radius: 10px; text-transform: uppercase; }}
p {{ font-size: 50px; margin: 40px 0 0; color: var(--muted); text-align: center; line-height: 1.25; letter-spacing: -.6px; }}
"""
    alt = f'<span>{t["alt"]}</span>' if t.get("alt") else ""
    badge = f'<div class="badge mono">{t["badge"]}</div>' if t.get("badge") else ""
    line = f'<p>{t["tagline"]}</p>' if t.get("tagline") else ""
    return css, f'{_logo(brand, t.get("logoWidth", 300))}<h1>{t.get("name", brand.get("name", ""))}{alt}</h1>{badge}{line}'

def end(s, brand, size):
    e = s.get("end", {})
    css = f"""
body {{ {_bg()} display: flex; flex-direction: column; align-items: center; justify-content: center; }}
.logo {{ margin-bottom: 34px; }}
h1 {{ font-size: 92px; margin: 0 0 46px; letter-spacing: -2px; }}
ul {{ list-style: none; padding: 0; margin: 0 0 60px; font-size: 44px; line-height: 1.65; color: var(--muted); letter-spacing: -.4px; }}
li::before {{ content: "✓"; color: var(--accent); font-weight: 700; margin-right: 22px; }}
.pill {{ font-size: 36px; background: var(--accent); color: #fff; padding: 20px 34px; border-radius: 14px; }}
.sub {{ font-size: 30px; color: var(--soft); margin-top: 28px; }}
"""
    items = "".join(f"<li>{x}</li>" for x in e.get("points", []))
    pill = f'<div class="pill mono">{e["pill"]}</div>' if e.get("pill") else ""
    sub = f'<div class="sub">{e["sub"]}</div>' if e.get("sub") else ""
    return css, f'{_logo(brand, e.get("logoWidth", 190))}<h1>{e.get("name", brand.get("name", ""))}</h1><ul>{items}</ul>{pill}{sub}'

def subtitle(cue, brand, size, win):
    """One cue: light text on a dark pill, centred near the bottom of the window."""
    fs = 34 if size[0] <= 1080 else 38
    css = f"""
.s {{ position: absolute; left: {win['x'] + win['w'] / 2}px; bottom: {size[1] - (win['y'] + win['h']) + 30}px;
     transform: translateX(-50%); max-width: {win['w'] - 100}px; width: max-content; text-align: center;
     background: rgba(16,18,22,.82); color: #fff; border-radius: 12px; padding: 10px 20px;
     font-size: {fs}px; line-height: 1.25; font-weight: 600; letter-spacing: -.2px;
     box-shadow: 0 6px 18px -6px rgba(0,0,0,.35); }}
"""
    import html as _h
    return css, f'<div class="s">{_h.escape(cue["text"])}</div>'

TEMPLATES = {"subtitle": subtitle, "window": window, "caption": caption, "toast": toast, "title": title, "end": end}
