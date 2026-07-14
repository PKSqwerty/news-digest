"""
Daily News Digest v2 — 100% free
RSS feeds -> GitHub Models (free LLM) -> KakaoTalk (나에게 보내기) + web version with tap-to-translate

- Korean news in Korean, foreign news in English
- Terms marked {{term|translation}} by the model:
    * Kakao version: markers stripped to plain term
    * Web version (GitHub Pages): tap the underlined term to see the translation
"""

import os
import re
import json
import time
import html
import requests
import feedparser
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

# ============================================================
# CONFIG
# ============================================================
# Source philosophy: wire services & trade press first (fact-first, minimal slant).
FEEDS = {
    "World": [
        "http://feeds.bbci.co.uk/news/world/rss.xml",              # BBC World (center, high-factual)
        "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",   # Google News aggregate (dilutes single-outlet slant)
    ],
    "Korea": [
        "https://www.yna.co.kr/rss/news.xml",       # 연합뉴스 주요뉴스 (wire service = 최대한 중도)
        "https://www.yna.co.kr/rss/economy.xml",    # 연합뉴스 경제
        "https://www.yna.co.kr/rss/politics.xml",   # 연합뉴스 정치
        "https://www.yna.co.kr/rss/society.xml",    # 연합뉴스 사회
        "http://www.khan.co.kr/rss/rssdata/total_news.xml",   # 경향 (좌측) — 비교용
        "https://www.chosun.com/arc/outboundfeeds/rss/?outputType=xml",  # 조선 (우측) — 비교용
    ],
    "Film / Entertainment": [
        "https://variety.com/feed/",
        "https://www.hollywoodreporter.com/feed/",
        "https://www.screendaily.com/full-rss",
        "https://news.google.com/rss/search?q=%EC%98%81%ED%99%94%EA%B3%84%20OR%20%EC%98%81%ED%99%94%EC%A0%9C%20OR%20%ED%95%9C%EA%B5%AD%EC%98%81%ED%99%94&hl=ko&gl=KR&ceid=KR:ko",  # 국내 영화계/영화제 뉴스
    ],
    "Camera / Gear": [
        "https://www.cined.com/feed/",
        "https://www.newsshooter.com/feed/",
        "https://petapixel.com/feed/",
    ],
    "Tech & AI": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
    ],
    "Markets": [
        "https://www.cnbc.com/id/15839069/device/rss/rss.html",    # CNBC Markets
    ],
}

# Short outlet labels used for source attribution in the digest
SOURCE_LABELS = {
    "bbci.co.uk": "BBC", "news.google.com": "GoogleNews", "yna.co.kr": "연합",
    "khan.co.kr": "경향", "chosun.com": "조선", "variety.com": "Variety",
    "hollywoodreporter.com": "THR", "screendaily.com": "Screen",
    "techcrunch.com": "TC", "theverge.com": "Verge", "cnbc.com": "CNBC",
    "cined.com": "CineD", "newsshooter.com": "Newsshooter", "petapixel.com": "PetaPixel",
}

# How the digest is delivered to KakaoTalk:
#   "sections" = one message per topic section (scroll-friendly, subtext allowed)
#   "single"   = everything compressed into one ~900-char message
SEND_MODE = "sections"

def load_interests():
    """Reads interests.txt — one topic per line, '-' prefix = de-prioritize."""
    want, avoid = [], []
    try:
        with open("interests.txt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                (avoid if line.startswith("-") else want).append(line.lstrip("- ").strip())
    except FileNotFoundError:
        pass
    ctx = "The reader is a Seoul-based freelance cinematographer / DOP.\nExtra weight on:\n"
    ctx += "".join(f"- {t}\n" for t in want)
    if avoid:
        ctx += "De-prioritize: " + ", ".join(avoid) + ".\n"
    return ctx

MAX_ITEMS_PER_FEED = 8
LOOKBACK_HOURS = 26

PAGES_URL = os.environ.get("PAGES_URL", "")  # e.g. https://username.github.io/news-digest/

# ============================================================
# 1. FETCH
# ============================================================

def fetch_articles():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    sections = {}
    for section, urls in FEEDS.items():
        items = []
        for url in urls:
            label = next((v for k, v in SOURCE_LABELS.items() if k in url), "src")
            try:
                feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"})
                for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
                    published = entry.get("published_parsed") or entry.get("updated_parsed")
                    if published:
                        pub_dt = datetime.fromtimestamp(time.mktime(published), tz=timezone.utc)
                        if pub_dt < cutoff:
                            continue
                    items.append({
                        "source": label,
                        "title": entry.get("title", "").strip(),
                        "summary": re.sub(r"<[^>]+>", "", entry.get("summary", "") or "")[:400],
                        "link": entry.get("link", ""),
                    })
            except Exception as e:
                print(f"[warn] feed failed: {url} -> {e}")
        sections[section] = items
        print(f"[fetch] {section}: {len(items)} items")
    return sections

# ============================================================
# 2. SUMMARIZE — Claude API if ANTHROPIC_API_KEY is set,
#                otherwise GitHub Models (free) as fallback
# ============================================================

GH_MODELS_URL = "https://models.github.ai/inference/chat/completions"
MODEL_CANDIDATES = ["openai/gpt-4.1", "openai/gpt-4o", "openai/gpt-4.1-mini"]

def build_prompt(sections):
    corpus = ""
    for section, items in sections.items():
        corpus += f"\n## {section}\n"
        for it in items:
            corpus += f"- [{it['source']}] {it['title']} :: {it['summary']}\n"

    today = datetime.now(KST).strftime("%Y-%m-%d (%a)")
    if SEND_MODE == "single":
        budget = "STRICT LIMIT: total under 880 characters — it must fit ONE KakaoTalk message. One line per story, no subtext lines."
        per_section = "1-3 stories per section, single line each"
    else:
        budget = "STRICT LIMIT: each section under 800 characters; total under 2600 characters."
        per_section = ("2-4 stories per section. Each story: '• headline — micro-context clause (src)'. "
                       "For ★ stories and the day's 1-2 biggest stories, add ONE short indented subtext line below (start it with '  ↳ ')")

    return f"""You are writing a personal morning news digest for {today} KST.

{load_interests()}

RULES:
- STRICTLY fact-first: no opinion, no editorializing, no loaded adjectives. If something is disputed/unconfirmed, say so.
- SOURCE ATTRIBUTION: each headline is tagged [source]. End each line with source(s) in parentheses, e.g. (연합) or (BBC/Verge).
- CROSS-OUTLET: when the SAME story appears from multiple outlets, merge into ONE item listing all sources; if outlets differ in numbers/framing, note it in a short clause. Never adopt one framing as fact.
- LANGUAGE: Korean-origin stories in Korean (한국어), foreign stories in English. Gloss genuinely difficult terms with {{{{term|translation}}}} markers (max 8 total).
- STRUCTURE (plain text, no markdown):
  Line 1: "📰 {today}"
  Then these sections, in this order, each as "▎헤더" on its own line:
  ▎세계 / ▎한국 / ▎영화 / ▎장비 / ▎Tech·AI / ▎시장
  {per_section}, formatted "• headline — micro-context clause (src)".
  Selection bar: pick what a well-informed person MUST know today + what matters to this reader. Skip filler; skip a section entirely if nothing meets the bar.
  Flag stories directly relevant to the reader (film industry, DGRO/VIG/AAPL/MSFT/V, filmmaking gear/AI tools) with ★ at line start.
- {budget}
- No preamble, no sign-off.

HEADLINES:
{corpus}
"""

def summarize_claude(prompt):
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    print("[llm] used Claude (claude-sonnet-4-6)")
    return "".join(b["text"] for b in resp.json()["content"] if b["type"] == "text")

def summarize_github_models(prompt):
    token = os.environ["GITHUB_TOKEN"]
    last_err = None
    for model in MODEL_CANDIDATES:
        try:
            resp = requests.post(
                GH_MODELS_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/vnd.github+json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2000,
                    "temperature": 0.3,
                },
                timeout=120,
            )
            resp.raise_for_status()
            print(f"[llm] used {model} (free)")
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[warn] model {model} failed: {e}")
            last_err = e
    raise RuntimeError(f"All models failed: {last_err}")

def summarize(sections):
    prompt = build_prompt(sections)
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return summarize_claude(prompt)
        except Exception as e:
            print(f"[warn] Claude failed ({e}) — falling back to free GitHub Models")
    return summarize_github_models(prompt)

# ============================================================
# 3a. WEB VERSION (GitHub Pages, tap-to-translate)
# ============================================================

MARKER_RE = re.compile(r"\{\{(.+?)\|(.+?)\}\}")

def render_web(digest, date_str):
    def to_span(m):
        term, gloss = html.escape(m.group(1)), html.escape(m.group(2))
        return f'<span class="g" onclick="t(this)" data-g="{gloss}">{term}</span>'

    body = html.escape(digest)
    # unescape our markers that got escaped, then convert
    body = body.replace("{{", "\x01").replace("}}", "\x02")
    body = re.sub(r"\x01(.+?)\|(.+?)\x02",
                  lambda m: f'<span class="g" onclick="t(this)" data-g="{html.escape(m.group(2))}">{m.group(1)}</span>',
                  body)
    body = body.replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Digest {date_str}</title>
<style>
  body {{ font-family: -apple-system, "Apple SD Gothic Neo", sans-serif; max-width: 640px;
         margin: 0 auto; padding: 20px 16px 60px; line-height: 1.65; color: #1a1a1a; background: #fafaf8; }}
  .g {{ border-bottom: 2px dotted #b8860b; cursor: pointer; position: relative; }}
  .g.on::after {{ content: attr(data-g); position: absolute; left: 0; top: 1.5em;
         background: #222; color: #fff; padding: 4px 10px; border-radius: 8px;
         font-size: 0.85em; white-space: nowrap; z-index: 9; }}
  .nav {{ margin-top: 40px; font-size: 0.9em; }} a {{ color: #b8860b; }}
  .hint {{ color:#999; font-size:0.8em; }}
</style></head><body>
<p class="hint">밑줄 친 단어를 탭하면 번역이 보입니다 · tap dotted words for translation</p>
{body}
<p class="nav"><a href="archive.html">← past digests</a></p>
<script>function t(el){{document.querySelectorAll('.g.on').forEach(x=>{{if(x!==el)x.classList.remove('on')}});el.classList.toggle('on')}}</script>
</body></html>"""

def write_site(digest, date_str):
    os.makedirs("docs", exist_ok=True)
    page = render_web(digest, date_str)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(page)
    with open(f"docs/{date_str}.html", "w", encoding="utf-8") as f:
        f.write(page)
    # rebuild archive list
    days = sorted([f[:-5] for f in os.listdir("docs")
                   if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.html", f)], reverse=True)
    links = "".join(f'<li><a href="{d}.html">{d}</a></li>' for d in days)
    with open("docs/archive.html", "w", encoding="utf-8") as f:
        f.write(f'<!DOCTYPE html><html><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width, initial-scale=1">'
                f'<title>Archive</title></head><body style="font-family:sans-serif;max-width:640px;'
                f'margin:0 auto;padding:20px;line-height:2"><h3>📰 Digest archive</h3><ul>{links}</ul></body></html>')
    print(f"[web] wrote docs/index.html + {date_str}.html + archive ({len(days)} days)")

# ============================================================
# 3b. KAKAO (나에게 보내기)
# ============================================================

def strip_markers(text):
    return MARKER_RE.sub(r"\1", text)

def kakao_access_token():
    resp = requests.post("https://kauth.kakao.com/oauth/token", data={
        "grant_type": "refresh_token",
        "client_id": os.environ["KAKAO_REST_API_KEY"],
        "refresh_token": os.environ["KAKAO_REFRESH_TOKEN"],
    }, timeout=30)
    resp.raise_for_status()
    tokens = resp.json()
    if "refresh_token" in tokens:
        print("::warning::Kakao issued a NEW refresh token. Update the KAKAO_REFRESH_TOKEN secret!")
        with open("new_refresh_token.txt", "w") as f:
            f.write(tokens["refresh_token"])
    return tokens["access_token"]

def chunk_text(text, size):
    paras, chunks, current = text.split("\n"), [], ""
    for p in paras:
        if len(current) + len(p) + 1 > size and current:
            chunks.append(current.rstrip()); current = ""
        current += p + "\n"
    if current.strip():
        chunks.append(current.rstrip())
    return chunks

def split_sections(text):
    """Split the digest into one chunk per ▎section; title line joins the first section."""
    lines = text.split("\n")
    chunks, current = [], ""
    for line in lines:
        if line.startswith("▎") and "▎" in current:
            chunks.append(current.rstrip())
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current.rstrip())
    # safety: if any section still exceeds Kakao's cap, sub-split it by size
    final = []
    for c in chunks:
        final.extend(chunk_text(c, 950) if len(c) > 950 else [c])
    return final

def send_kakao(text):
    token = kakao_access_token()
    link = PAGES_URL or "https://news.google.com"
    chunks = split_sections(text) if SEND_MODE == "sections" else chunk_text(text, 950)
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1 and PAGES_URL:
            chunk += f"\n\n🔗 웹 버전 (단어 탭 번역): {PAGES_URL}"
        template = {"object_type": "text", "text": chunk,
                    "link": {"web_url": link, "mobile_web_url": link}}
        resp = requests.post(
            "https://kapi.kakao.com/v2/api/talk/memo/default/send",
            headers={"Authorization": f"Bearer {token}"},
            data={"template_object": json.dumps(template, ensure_ascii=False)},
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"[error] kakao send failed ({resp.status_code}): {resp.text}")
            resp.raise_for_status()
        print(f"[send] kakao {i+1}/{len(chunks)}")
        time.sleep(0.5)

# ============================================================

if __name__ == "__main__":
    date_str = datetime.now(KST).strftime("%Y-%m-%d")
    sections = fetch_articles()
    if sum(len(v) for v in sections.values()) == 0:
        print("[abort] no articles fetched — check feeds")
        raise SystemExit(1)
    digest = summarize(sections)
    print("---- DIGEST ----\n" + digest + "\n----------------")
    write_site(digest, date_str)
    send_kakao(strip_markers(digest))
    print("[done]")
