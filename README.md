# AI News Digest

Your own AI agent that reads the news for you. Every morning it collects news on your topics from Google News, Reddit and YouTube, picks the important stuff with AI and sends you a short digest to email and Discord.

No server. It runs for free on GitHub Actions, with the free Gemini API.

This is the finished project from my Udemy course **Build Your Own AI Agent with Claude & Cursor, Free on GitHub**. In the course we build it step by step, with AI writing all the code. If you got stuck, compare your version with this one. Or just take it and make it yours.

## What it does

- Four topics in one digest: World news, Sports, AI and technology, Cars. You change them in `config.yaml`
- Sources: Google News search, subreddits, YouTube channels. No extra keys needed
- Only news from the last 24 hours, no duplicates, and it remembers what it already sent
- "Top of the day" on top, then 1-2 sentences per item with a link
- Email gets the full digest, Discord gets a short version with headlines
- If something fails, the run shows a red X, not a fake green check

## Get your own copy

1. Click **Use this template** → **Create a new repository** at the top of this page. Public or private, both work
2. In your new repo open **Settings → Secrets and variables → Actions** and add these secrets:

| Secret | What to put there |
|---|---|
| `LLM_PROVIDER` | `gemini` |
| `GOOGLE_API_KEY` | your free key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| `NOTIFICATION_METHODS` | `email,discord` (or just `email`, or just `discord`) |
| `GMAIL_ADDRESS` | the Gmail you send from |
| `GMAIL_APP_PASSWORD` | an app password from [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), not your normal password |
| `EMAIL_TO` | where the digest goes, can be the same Gmail |
| `DISCORD_WEBHOOK_URL` | Discord: channel settings → Integrations → Webhooks → New Webhook → Copy URL |

Keys go only to GitHub Secrets. Never put them in the code.

3. Open the **Actions** tab, pick **Daily News Digest** and press **Run workflow**. In a couple of minutes the digest is in your email and Discord
4. After that it runs by itself every day

## Make it yours

Everything you'd want to change is in `config.yaml`, no code:

- `personalization` - language, a few lines about you, the style (short, detailed, funny, serious...)
- `news.topics` - your topics, search phrases, subreddits and YouTube channels

The time is in `.github/workflows/daily-news.yml`, the `cron` line. It's in UTC. `0 10 * * *` means 10:00 UTC every day.

## Easiest way: ask AI

Open the project in Cursor (or any AI coding tool) and paste this:

```
I want my own copy of this project: https://github.com/maxisurfer/ai-news-digest
1. Tell me step by step how to create my copy with "Use this template" on GitHub. Wait until I say "done".
2. Clone my copy and open it here.
3. Tell me which GitHub Secrets I need to add and where to get each key. Never put keys in the code.
4. Ask me about my topics, my sources and the style I want, and change config.yaml for me.
5. Commit, push, and tell me when to press Run workflow.
```

## Free Gemini limits

The free Gemini key has a daily limit. One digest a day fits easily. If you test a lot and get a limit error, just wait until tomorrow.

## Credits and license

Based on [giftedunicorn/ai-news-bot](https://github.com/giftedunicorn/ai-news-bot), licensed under GPL-3.0. Thanks to the author!

Changed by Max Flinn in 2026: restored the GitHub Actions workflow, switched to Gemini, made failed runs show as failed, added Discord delivery from secrets, Google News / Reddit / YouTube RSS sources with topics in `config.yaml`, 24-hour freshness and sent-history memory, the new digest style and personalization. See `PLAN.md` for the full plan.

This project is under the same license, GPL-3.0. See `LICENSE`.
