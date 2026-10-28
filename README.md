# Daily Digest

Tech and AI news for a Discord channel, checked every 30 minutes. Each post has a headline, a short summary, a link to the source, a trust badge (Official, Known voice or Press), and a note on what the item means for Agora.

It runs entirely on free tiers: GitHub Actions, a Discord webhook, and a free-tier language model.

## How it works

1. Reads the feeds listed in `config/sources.yaml`: official blogs and release feeds, known people, press, and news-search feeds.
2. Drops anything already posted, too old, or off-topic (keywords in `config/channels/news.yaml`).
3. Items found through a news search or Hacker News are posted only when the publisher is in `trusted_domains`. Everything else is dropped.
4. A language model writes the summary and the Agora note, using `config/agora-context.md` as background. Items below the relevance threshold are not posted.
5. Posts go to Discord through a webhook. A daily digest lists the top items of the last 24 hours with a ready-to-paste blurb for each.

If no model is reachable, up to two official items per run are posted marked "Analysis pending". Other items wait for the next run.

## Setup

1. In your Discord server, open the channel settings, then Integrations, then Webhooks, and create a webhook. Copy its URL.
2. In this repository, open Settings, then Secrets and variables, then Actions, and add:
   - `DISCORD_WEBHOOK_URL`: the webhook URL.
   - `GEMINI_API_KEY`: a free key from Google AI Studio (optional but recommended).
   - `GROQ_API_KEY`: a free key from the Groq console (optional, used as a fallback).

   These are the same names as in `.env.example`, so a local `.env` and the repository secrets stay in step.
3. Open the Actions tab, choose `radar`, and run it once with "Run workflow". The first run only records what already exists, so it posts nothing. Later runs post new items.
4. Choose `digest` and run it once to check the daily digest.

Providers are tried in the order listed in `config/channels/news.yaml`. A provider without its key is skipped.

## Customize

- Add or remove sources in `config/sources.yaml`. To follow a person, add their Bluesky, Mastodon or Medium feed as a tier 2 source.
- Add publishers you trust to `trusted_domains`.
- Edit `config/agora-context.md` when Agora's products change. It steers every note.
- Change `threshold`, `max_posts_per_run` and the keywords in `config/channels/news.yaml`.
- The digest runs at 00:00 UTC. Change the cron line in `.github/workflows/digest.yml`.

## Run locally

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env   # then fill in your keys
.venv/bin/pytest
.venv/bin/python -m radar run --channel config/channels/news.yaml --dry-run
```

The program reads `.env` from the current directory (use `--env-file` for another path). Variables already set in the shell win over the file, and empty values are ignored. `.env` is listed in `.gitignore`; never commit it.

`--dry-run` prints the posts instead of sending them and saves nothing. It still calls the language model, so it needs a Gemini or Groq key, but it does not need the webhook.

## Notes

- Keep the repository public. Actions minutes are unlimited for public repositories. A private repository gets 2,000 free minutes a month, and a run every 30 minutes can use more than that.
- Create the Gemini key in Google AI Studio under a project that has no billing account attached, so it can only use the free tier.
- A run fails (and GitHub emails you) when Discord rejects posts, for example after the webhook was deleted.
- Processed items are kept in a `state` branch that the workflow maintains. Do not edit it by hand.
- GitHub pauses scheduled workflows in repositories with no activity for 60 days. The `keepalive` workflow re-enables the schedule weekly. If posts stop, open the Actions tab and re-enable the workflows.
- Free-tier limits of the model providers change. If a provider starts failing, the next one in the list is used.

## License

MIT
