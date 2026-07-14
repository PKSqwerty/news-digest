# 📰 Daily News Digest → KakaoTalk + Web (100% free)

Every morning 07:00 KST:
RSS (wire services & trade press) → free LLM (GitHub Models) → your KakaoTalk (나와의 채팅) + web version with tap-to-translate words.

- Korea section in 한국어, everything else in English
- Kakao message: quick plain-text version, ends with a link to the web version
- Web version: dotted-underline words → tap to see translation (EN↔KR both directions). Auto-archives past digests.
- Cost: **$0.** GitHub Actions (runner), GitHub Models (LLM), GitHub Pages (web) are all free. Kakao 나에게 보내기 is free.

## Setup (one time, ~20 min)

### 1. Kakao app (~10 min)
Follow instructions at the top of `kakao_setup.py`:
- Create app at https://developers.kakao.com
- 카카오 로그인 ON, redirect URI `http://localhost:5000/callback`
- 동의항목 → 카카오톡 메시지 전송 (talk_message) → 선택 동의
- Locally: `pip install requests` then `python kakao_setup.py YOUR_REST_API_KEY`
- It prints your `KAKAO_REFRESH_TOKEN`

### 2. GitHub repo
- Create a repo (public or private*) and push these files
- Settings → Secrets and variables → Actions → **Secrets**:
  - `KAKAO_REST_API_KEY`
  - `KAKAO_REFRESH_TOKEN`
  - (optional) `GH_PAT` — classic token with `repo` scope, enables auto-rotation of the Kakao token. Without it, re-run `kakao_setup.py` every ~2 months when warned.
- Same page → **Variables**:
  - `PAGES_URL` = `https://YOURUSERNAME.github.io/REPONAME/` (set after step 3)

### 3. GitHub Pages
- Settings → Pages → Source: "Deploy from a branch" → Branch: `main`, folder: `/docs` → Save
- Your digest URL: `https://YOURUSERNAME.github.io/REPONAME/`

*Private repo + Pages requires GitHub Pro. On a free account, make the repo public — it only contains code and news summaries, no secrets.

### 4. Test
- Actions → "Daily News Digest" → **Run workflow**
- Check KakaoTalk (나와의 채팅) and the web URL

## Source philosophy (bias)
Wire services first — 연합뉴스, BBC — plus Google News aggregation (dilutes single-outlet slant) and trade press (Variety/THR/Screen Daily, CNBC). The prompt enforces fact-only summarization: no opinion, no loaded language, disputes labeled as disputed. No source is perfectly neutral; this is about as 중도 as an automated pipeline gets. Edit `FEEDS` in `digest.py` anytime.

## Customizing
- Feeds → `FEEDS` in `digest.py`
- Interests/weighting → `USER_CONTEXT`
- Send time → cron in `.github/workflows/daily.yml` (UTC; 07:00 KST = 22:00 UTC)
- Model → free by default; add `ANTHROPIC_API_KEY` secret to switch to Claude (better summaries, ~$0.5–1/month). Falls back to free automatically if Claude errors.
- Topics → edit `interests.txt` on github.com anytime (pencil icon), takes effect next morning

## Known limitations
- Kakao length cap → digest arrives as 2–4 messages
- Actions cron can drift 5–15 min. Normal.
- GitHub Models free tier has rate limits (irrelevant at 1 run/day) and could change terms someday — if so, swap `summarize()` back to a paid API (a Claude API version is a small edit away)
- Kakao refresh token expires ~2 months; auto-rotated if `GH_PAT` set, otherwise the log warns you
- GitHub emails you automatically when a run fails, so breakage won't be silent
