"""Render design drafts as a self-contained HTML page of mockup frames.

The mockups approximate the After Effects treatments closely enough to choose between
directions: real frames from the footage, the draft's palette, and the installed fonts by
family name. The chosen direction is always confirmed with a real After Effects still.
"""
import html
import json
import shutil
from pathlib import Path

DEFAULT_LINES = [["이 화면의 글자 크기와"], ["색이 ", {"hl": "잘 보이는지"}, " 확인해 주세요."]]
END_ROWS = [("안내", ["첫째 줄", "둘째 줄"]), ("문의", ["예시 · 000-0000-0000"])]


def _family(postscript: str) -> str:
    """'Paperlogy-7Bold' -> 'Paperlogy' — last resort when a recipe carries no family name."""
    return postscript.split("-")[0]


def _family_of(spec: dict) -> str:
    """Browsers match installed fonts by family name ('NanumSquare Neo'), not by the
    PostScript name After Effects needs ('NanumSquareNeoTTF-bRg')."""
    return spec.get("family") or _family(spec["font"])


def _tokens(draft):
    tokens = draft.recipe["tokens"]
    return tokens["palette"], tokens["type"]


def _is_paper(draft) -> bool:
    return draft.recipe["components"]["caption"]["treatment"] == "paper-card"


def mockup_css(draft) -> str:
    palette, type_block = _tokens(draft)
    head, body, quote = (_family_of(type_block[r]) for r in ("headline", "body", "quote"))
    return f"""
.d-{draft.id} {{ --paper: {palette['paper']}; --ink: {palette['ink']}; --accent: {palette['accent']};
  --accent2: {palette['accent2']}; --rule: {palette['rule']}; --shade: {palette['shade']};
  --head: '{head}', system-ui, sans-serif; --body: '{body}', system-ui, sans-serif;
  --quote: '{quote}', Georgia, serif; }}
.d-{draft.id} .cap {{ font-family: var(--body); color: var(--ink); }}
.d-{draft.id} .cap .hl {{ background: var(--accent); padding: 0 .12em; border-radius: .06em; }}
.d-{draft.id} .card {{ background: var(--paper); box-shadow: 0 10px 30px rgba(0,0,0,.25); }}
.d-{draft.id} .lt {{ font-family: var(--head); color: var(--ink); background: var(--paper); }}
.d-{draft.id} .lt .role {{ font-family: var(--body); color: var(--paper); background: var(--ink); }}
.d-{draft.id} .end {{ background: var(--paper); color: var(--ink); font-family: var(--body); }}
.d-{draft.id} .end h3 {{ font-family: var(--head); }}
.d-{draft.id} .end .year {{ background: var(--ink); color: var(--paper); }}
.d-{draft.id} .end .label {{ color: var(--accent2); }}
.d-{draft.id} .rule {{ background: var(--accent); }}
""".strip()


def caption_html(draft, lines=None) -> str:
    out = []
    for line in (lines or DEFAULT_LINES):
        parts = []
        for segment in line:
            if isinstance(segment, dict):
                parts.append(f'<span class="hl">{html.escape(segment["hl"])}</span>')
            else:
                parts.append(html.escape(segment))
        out.append('<span class="line">' + "".join(parts) + "</span>")
    return "".join(out)


def _frames(log, out_dir) -> list:
    root = Path(log.get("root") or ".")
    copied = []
    (out_dir / "frames").mkdir(parents=True, exist_ok=True)
    for clip in log.get("clips", []):
        for frame in clip.get("frames", []):
            src = root / frame["file"]
            if not src.exists():
                continue
            dest = out_dir / "frames" / Path(frame["file"]).name
            shutil.copyfile(src, dest)
            copied.append(f"frames/{dest.name}")
            break
    return copied


def _draft_section(draft, frame_rel, lines) -> str:
    palette, type_block = _tokens(draft)
    paper = _is_paper(draft)
    background = (f'<img class="bg" src="{html.escape(frame_rel)}" alt="">' if frame_rel
                  else '<div class="bg placeholder"></div>')
    caption_block = (f'<div class="card cap">{caption_html(draft, lines)}</div>' if paper
                     else f'<div class="cap centered">{caption_html(draft, lines)}</div>')
    rows = "".join(f'<div class="row"><span class="label">{html.escape(label)}</span>'
                   f'<span class="values">{"<br>".join(html.escape(v) for v in values)}</span></div>'
                   for label, values in END_ROWS)
    notes = "".join(f'<li>{html.escape(n)}</li>' for n in draft.notes)
    fonts_used = ", ".join(dict.fromkeys(_family_of(spec) for spec in type_block.values()))
    return f"""
<section class="draft d-{html.escape(draft.id)}" data-id="{html.escape(draft.id)}">
  <header>
    <h2>{html.escape(draft.name)}</h2>
    <p class="mood">{html.escape(" · ".join(draft.mood[:5]))}</p>
    <p class="fonts">{html.escape(fonts_used)}</p>
    {f'<ul class="notes">{notes}</ul>' if notes else ''}
  </header>
  <div class="frames">
    <figure class="frame">{background}<div class="overlay {'paper' if paper else 'cine'}">{caption_block}
      <div class="lt"><span class="role">역할 예시</span><span class="name">이름 예시</span></div></div>
      <figcaption>caption + lower third</figcaption></figure>
    <figure class="frame"><div class="end">
      <span class="year">2027</span><h3>제목 예시</h3><div class="rule"></div>
      <p class="tag">한 줄 설명이 들어갑니다</p>{rows}</div><figcaption>end card</figcaption></figure>
  </div>
  <footer>
    <input class="note" type="text" placeholder="바꾸고 싶은 점 (선택)">
    <button class="choose" data-id="{html.escape(draft.id)}">Choose this</button>
  </footer>
</section>""".strip()


PAGE_CSS = """
:root { color-scheme: light dark; }
body { margin: 0; padding: 24px; font: 15px/1.5 system-ui, sans-serif; background: #14161a; color: #e8e6e1; }
h1 { font-size: 20px; margin: 0 0 4px; }
.lede { color: #a9a6a0; margin: 0 0 20px; }
.draft { border: 1px solid #2a2d33; border-radius: 10px; padding: 16px; margin-bottom: 20px; }
.draft h2 { font-size: 17px; margin: 0; }
.mood, .fonts { color: #a9a6a0; margin: 2px 0; font-size: 13px; }
.notes { color: #ffcf6b; font-size: 13px; margin: 6px 0 0; padding-left: 18px; }
.frames { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; margin-top: 12px; }
.frame { margin: 0; position: relative; }
.frame figcaption { color: #7e7b76; font-size: 12px; margin-top: 4px; }
.bg, .end { width: 100%; aspect-ratio: 16 / 9; display: block; object-fit: cover; border-radius: 6px; }
.bg.placeholder { background: linear-gradient(135deg, #2b2f36, #14161a); }
.overlay { position: absolute; inset: 0; padding: 5%; box-sizing: border-box; }
.overlay .cap { position: absolute; left: 6%; bottom: 12%; max-width: 62%; font-size: clamp(13px, 2.1vw, 22px); }
.overlay .card { padding: .5em .7em; border-radius: .25em; }
.overlay.cine .cap { left: 50%; transform: translateX(-50%); text-align: center; color: #fff;
  text-shadow: 0 2px 12px rgba(0,0,0,.6); }
.cap .line { display: block; }
.overlay .lt { position: absolute; left: 6%; top: 14%; padding: .4em .6em; border-radius: .25em; font-size: clamp(11px, 1.6vw, 16px); }
.overlay .lt .role { display: inline-block; padding: 0 .5em; border-radius: 1em; font-size: .8em; }
.overlay .lt .name { display: block; font-weight: 700; }
.end { padding: 6% 7%; box-sizing: border-box; }
.end .year { display: inline-block; padding: .1em .7em; border-radius: 1em; font-size: .8em; }
.end h3 { font-size: clamp(18px, 3vw, 34px); margin: .2em 0 .1em; }
.end .rule { width: 28%; height: 3px; margin: .2em 0 .5em; }
.end .row { display: flex; gap: 10px; font-size: clamp(11px, 1.4vw, 14px); margin-top: .25em; }
.end .label { min-width: 5em; }
footer { display: flex; gap: 8px; margin-top: 12px; }
.note { flex: 1; padding: 8px; border-radius: 6px; border: 1px solid #2a2d33; background: #0f1114; color: inherit; }
button { padding: 8px 14px; border-radius: 6px; border: 0; background: #e8e6e1; color: #14161a; font-weight: 600; cursor: pointer; }
button:disabled { opacity: .45; cursor: default; }
.picked { outline: 2px solid #7fd1a8; }
"""

PAGE_JS = """
const offline = location.protocol === 'file:';
document.querySelectorAll('button.choose').forEach(function (b) {
  if (offline) { b.disabled = true; b.textContent = 'open via the preview server to click'; return; }
  b.addEventListener('click', async function () {
    const section = b.closest('.draft');
    const note = section.querySelector('.note').value;
    b.disabled = true;
    try {
      await fetch('/choose', {method: 'POST', headers: {'Content-Type': 'application/json'},
                              body: JSON.stringify({id: b.dataset.id, note: note})});
      document.querySelectorAll('.draft').forEach(function (d) { d.classList.remove('picked'); });
      section.classList.add('picked');
      b.textContent = 'Chosen — you can close this tab';
    } catch (e) { b.disabled = false; b.textContent = 'Choose this (retry)'; }
  });
});
"""


def render_mockups(drafts, log, out_dir, script_lines=None, title="Design directions") -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = _frames(log, out_dir)
    sections, css = [], []
    for i, draft in enumerate(drafts):
        sections.append(_draft_section(draft, frames[i % len(frames)] if frames else None, script_lines))
        css.append(mockup_css(draft))
    page = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>{PAGE_CSS}\n{chr(10).join(css)}</style></head>
<body><h1>{html.escape(title)}</h1>
<p class="lede">Mockups from your own footage. Pick one, or type what you would change.
The chosen direction is confirmed with a real After Effects still before anything is built.</p>
{chr(10).join(sections)}
<script>{PAGE_JS}</script></body></html>
"""
    index = out_dir / "index.html"
    index.write_text(page, encoding="utf-8")
    # "_notes" carries "install this font first" to design-choose; load_design ignores it.
    saved = [{**d.recipe, "_notes": list(d.notes)} for d in drafts]
    (out_dir / "drafts.json").write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
    return index
