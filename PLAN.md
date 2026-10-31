# PLAN: Personal morning news digest

Fork of `giftedunicorn/ai-news-bot`. Goal: every day at 07:00 São Paulo time (10:00 UTC),
send one English digest of 16-20 items in four topics to email and Discord, using GitHub Actions
and the free Gemini API.

## Rules for the work

- Edit files locally, then test on GitHub Actions (the "server" for this project). Local runs are optional.
- One finished to-do item = one commit with a short, clear message, then push to `origin`
  (your own copy). The original repo is never pushed to.
- No keys, passwords, webhook URLs or personal data in code, config or commits. All of them go to GitHub Secrets.
- Check Python syntax (`python -m py_compile`) and YAML syntax before every commit.
- License stays GPL-3.0.

## What the project has today (findings)

| Area | Current state | Needed change |
|---|---|---|
| Workflow | `.github/workflows/daily-news.yml` deleted on 2026-07-20 (commit `bc7c323`) | Restore from `bc7c323^`, new cron, Discord secret |
| Gemini | Old `google-generativeai` SDK, default model `gemini-3-pro-preview` (paid) | Move to `google-genai` SDK, free Flash model by default |
| Sources | ~25 AI-only English feeds + 12 non-English feed groups in `src/news/fetcher.py` | Remove all; add topic-based Google News / Reddit / YouTube |
| Time filter | None (takes the first N items of a feed) | Only items from the last 24 hours |
| Stage 1 | Picks 15-20 AI items; pads with random items if fewer | Per-topic picks (4-5 each), never pad |
| Stage 2 | Long 4-6 sentence analyst summaries; LLM writes links itself | 1-2 sentences, friendly tone; links inserted by code from feeds |
| Memory | No "already covered" memory | New feature: 5-day sent-history file committed by the workflow |
| Dry run | None | New feature: `--dry-run` / `DRY_RUN` and a workflow input |
| Discord | Up to 10 embeds x 4096 chars per message (over Discord's 6000-char total limit) | Split safely, never exceed limits |
| Email | Subject `AI News Digest - <date>` | Subject `Morning digest - <date>` |

---

## Phase 1: bot running with Gemini on GitHub Actions (email + Discord)

### [x] 1.1 Restore the workflow
- **Files:** `.github/workflows/daily-news.yml` (restored from `git show bc7c323^:.github/workflows/daily-news.yml`).
- **Changes:** cron `0 10 * * *`; keep `workflow_dispatch` and add a boolean input `dry_run` (default `false`);
  pass only the secrets we use (`LLM_PROVIDER`, `GOOGLE_API_KEY`, `LLM_MODEL`, `NOTIFICATION_METHODS`,
  `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `EMAIL_TO`, `DISCORD_WEBHOOK_URL`); set `AI_RESPONSE_LANGUAGE: en`;
  `TZ: America/Sao_Paulo`; update action versions if needed.
- **Check:** the workflow "Daily News Digest" appears in the Actions tab with a "Run workflow" button
  and a `dry_run` checkbox. YAML passes a syntax check.

### [x] 1.2 Move Gemini to the current Google SDK
- **Files:** `requirements.txt` (`google-generativeai` → `google-genai`), `src/llm_providers/gemini_provider.py`,
  `.env.example`.
- **Changes:** use `from google import genai` / `client.models.generate_content(...)` with
  `GenerateContentConfig(max_output_tokens, temperature)`; default model = a free Flash model
  (confirm the current free-tier name with `client.models.list()` during implementation; overridable by `LLM_MODEL`);
  retry once on 429/503 with a short wait; clear error when the response is empty or blocked.
- **Check:** the Actions log shows `Gemini provider initialized with model: ...` and both stages finish without errors.

### [x] 1.3 Dry run mode (new feature)
- **Files:** `main.py`, `src/config.py`, `.github/workflows/daily-news.yml`, `Makefile` (`make dry-run`).
- **Changes:** `python main.py --dry-run` or `DRY_RUN=true` → fetch + both Gemini stages, print the full digest
  to the log, send nothing, do not update the memory file. The workflow input `dry_run` sets `DRY_RUN`.
- **Check:** a manual run with `dry_run` checked shows the full digest in the log; nothing arrives by email or
  in Discord; there is no new commit.

### [x] 1.4 Reliable delivery to email and Discord
- **Files:** `main.py`, `src/notifiers/email_notifier.py`, `src/notifiers/discord_notifier.py`.
- **Changes:**
  - Email subject `Morning digest - YYYY-MM-DD` (date in São Paulo time).
  - Discord: split the digest into messages that respect all limits (4096 chars per embed, 6000 chars total
    per message, 10 embeds per message), splitting on item boundaries, never in the middle of a link.
  - Each channel is sent in its own `try`; a failure in one is logged with the reason, the other still sends.
    Exit code is non-zero only if every channel failed.
  - Slack/Telegram/webhook code stays, just not enabled.
- **Check:** a manual run sends one email and one Discord post (long digest arrives as several messages
  in order). Test with a wrong `DISCORD_WEBHOOK_URL` for one run: the email still arrives and the log shows
  the Discord error.

### [x] 1.5 README: secrets and how to run (first version)
- **Files:** `README.md` (new short section at the top for this fork; the original text stays below).
- **Changes:** simple steps: get a free Gemini key, create a Gmail App Password, create a Discord webhook,
  add each secret in *Settings → Secrets and variables → Actions*, run manually from the Actions tab
  (with and without dry run). Note: GitHub pauses scheduled workflows after 60 days without activity in a public
  repo; the daily memory commit (step 2.5) keeps the repo active. Scheduled runs can start late.
- **Check:** follow the README from a clean state; every secret name in the README matches the workflow.

**Phase 1 done when:** a manual run on GitHub sends one digest to both email and Discord, and a dry run
only prints it.

---

## Phase 2: my topics and sources

### [x] 2.1 Topic-based source config; remove old feeds
- **Files:** `config.yaml` (new `topics:` section), `src/news/fetcher.py`, `src/config.py`.
- **Changes:** delete all AI-only and non-English feed dictionaries. Add four topics (`world`, `sports`,
  `ai_tech`, `cars`), each with its sources:
  - Google News RSS (English), one search per phrase:
    `https://news.google.com/rss/search?q=<phrase>&hl=en-US&gl=US&ceid=US:en`
    - World: world news, politics, geopolitics
    - Sports: Brazilian football, Brasileirao, Brazil national team, Copa Libertadores, NBA, NBA playoffs,
      NBA trades, Formula 1, F1 race, F1 qualifying (each tagged with sub-topic `football` / `nba` / `f1`)
    - AI and tech: artificial intelligence, OpenAI Google Gemini, tech launches
    - Cars: new car launches, car market, electric cars
  - Reddit top of the day: `https://www.reddit.com/r/<sub>/top/.rss?t=day`
    (worldnews, soccer, nba, formula1, technology, artificial, cars)
  - YouTube: `https://www.youtube.com/feeds/videos.xml?channel_id=<ID>`
    (BBC News, ESPN FC, NBA, Formula 1, Marques Brownlee, Fireship, Top Gear — YouTube via free RSS, no API key)
- **Check:** `grep` for old feed domains (techcrunch, arxiv, 36kr, ...) finds nothing; the dry-run log lists the
  sources per topic.

### [x] 2.2 Verify Reddit and YouTube sources
- **Files:** `scripts/check_sources.py` (new), `config.yaml` (real YouTube channel IDs),
  workflow step or `make check-sources`.
- **Changes:** find and fill in the channel ID of each YouTube channel; the script fetches every source and prints
  OK / FAILED / item count. Sources that do not exist are removed from the config, with a comment.
- **Check:** run `make check-sources` locally; every remaining source is OK, or is known to be blocked
  sometimes (Reddit).

### [x] 2.3 New fetcher: 24-hour window, fault tolerance
- **Files:** `src/news/fetcher.py`.
- **Changes:** parse with `feedparser` (already in requirements); keep only items published in the last 24 hours;
  per-source timeout + one retry; a failed source is logged as `SKIPPED <source>: <reason>` and the run continues;
  the run fails only if no source returned anything. Read the real publisher name from Google News `<source>`;
  use the channel name for YouTube and `r/<sub>` for Reddit. Links come only from the feed.
- **Check:** the dry-run log shows a summary table "source → items in last 24h"; if Reddit is blocked, the log shows
  SKIPPED lines and the digest is still produced.

### [x] 2.4 Local de-duplication before Gemini
- **Files:** `src/news/dedupe.py` (new), `src/news/generator.py`.
- **Changes:** merge items with the same URL or a very similar normalized title (strip " - Publisher" suffixes,
  punctuation, case); keep the version from the best source (original outlet > Google News aggregate > Reddit/YouTube).
- **Check:** the dry-run log shows "N items → M after de-duplication"; no story appears twice in the digest.

### [x] 2.5 "Already covered" memory (new feature)
- **Files:** `src/news/history.py` (new), `data/sent_history.json` (new, only links/title hashes and dates,
  no personal data), `src/news/generator.py`, `main.py`, `.github/workflows/daily-news.yml`.
- **Changes:** before Stage 1, drop items whose URL or normalized title was sent in the last 5 days.
  After at least one channel succeeds, add the sent items and prune entries older than 5 days.
  The workflow gets `permissions: contents: write` and commits the file as `github-actions[bot]`
  ("chore: update sent history"); this also keeps the repo active. Skipped in dry run.
- **Check:** after a real run there is a new history commit on `main`; a second manual run the same day does not
  repeat items (the log shows "K items skipped as already covered").

### [x] 2.6 Stage 1: pick the best items per topic
- **Files:** `config.yaml` (`stage1_prompt_template`), `src/news/generator.py`.
- **Changes:** Stage 1 receives items grouped by topic with IDs and returns JSON
  `{"world": [...], "sports": [...], "ai_tech": [...], "cars": [...]}` with up to 5 IDs per topic.
  Rules in the prompt: original reporting over reposts/opinion, no clickbait/rumors/celebrity gossip,
  one item per story, sports balanced across football/NBA/F1 when there is news, strongest stories for AI & tech
  (still not more items). Code removes the padding fallback, enforces at most 5 per topic and at most 20 in total,
  and accepts fewer when news is thin. If the JSON cannot be parsed, retry once; if it fails again, take the
  newest items from the best sources per topic (up to 4), without padding.
- **Check:** the dry-run log shows "selected: world 5, sports 4, ai_tech 5, cars 4"; total 16-20 on a normal day.

**Phase 2 done when:** the digest uses only the new sources, has items only from the last 24 hours, has no repeats
from the last 5 days, and works when Reddit is blocked.

---

## Phase 3: style and personalization

### [x] 3.1 Personalization block + Stage 1 ranking by about_me
- **Files:** `config.yaml` (`personalization:`), `src/config.py`, `src/news/generator.py`.
- **Check:** Stage 1 prompt includes `{about_me}`; JSON arrays preserve relevance order per topic.

### [x] 3.2 Stage 2 JSON (top_of_day + headline + summary)
- **Files:** `config.yaml` (`stage2_prompt_template`), `src/news/generator.py`.
- **Check:** Stage 2 returns JSON only; fallback uses feed title/description if parse fails.

### [x] 3.3 Renderer: full digest (email) with topic sections and feed links
- **Files:** `src/news/renderer.py`, `src/news/generator.py`.
- **Check:** local render test; four topic headings only; links from fetched items.

### [x] 3.4 Discord short version + NOTIFICATION_METHODS switch
- **Files:** `src/news/renderer.py`, `main.py`, `src/notifiers/discord_notifier.py`.
- **Check:** Discord gets headlines+links only; email gets full text; secret `email`, `discord`, or `email,discord`.

### [x] 3.5 README style/about-me + cleanup
- **Files:** `README.md`, `.env.example`, `Makefile`.
- **Check:** user knows where `personalization:` lives; one dry run + one real run on Actions.

---

## "Done when" checklist (from the spec)

- [ ] 1. `daily-news.yml` restored from history with cron `0 10 * * *` and a manual trigger (1.1)
- [ ] 2. Gemini works with the current Google SDK (1.2)
- [ ] 3. Dry run shows the digest without sending (1.3)
- [ ] 4. A manual run sends one digest to both email and Discord (1.4)
- [ ] 5. 16-20 items in four topics, 1-2 sentences, source name and working link each (2.6, 3.1, 3.2)
- [ ] 6. Everything in English, no old AI-only feed left (2.1, 3.1)
- [ ] 7. README explains secrets and running in simple steps (1.5, 3.3)

## What I need from you (only in the browser)

- Phase 1: add the secrets in *Settings → Secrets and variables → Actions* (I give exact names and where to
  get each value). Values never go through the repo.
- Enable workflows on the fork's Actions tab (GitHub disables them on forks by default) if the button is shown.
