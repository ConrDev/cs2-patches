# CS2 Update Notifier
[![CS2 Update Notifier](https://github.com/ConrDev/cs2-patches/actions/workflows/cs2-updates.yml/badge.svg?event=schedule)](https://github.com/ConrDev/cs2-patches/actions/workflows/cs2-updates.yml)

Posts Counter-Strike 2 patch notes to one or more Discord channels via webhook,
running for free on GitHub Actions every ~10 minutes.

## Setup

1. Create a Discord webhook for each channel you want to post to:
   channel -> Edit Channel -> Integrations -> Webhooks -> New Webhook -> Copy URL.
2. Create a new GitHub repository and upload these files (keep the folder
   structure: `.github/workflows/cs2-updates.yml` must be in that exact path).
3. In the repo: Settings -> Secrets and variables -> Actions -> New repository secret.
   Name it `DISCORD_WEBHOOK_URL` and paste your webhook URL(s) as the value.
   For multiple webhooks, put one per line (commas or pipes also work).
4. Go to the Actions tab, enable workflows if prompted, then open
   "CS2 Update Notifier" and click "Run workflow" once to initialize.
   The first run records the current state without posting old updates.

That's it. New CS2 updates will appear in your channel(s) within ~10-15 minutes
of Valve publishing them.

## Behavior notes

- **Multiple webhooks:** separate them with newlines, commas, or pipes. A dead
  webhook logs an error but doesn't stop the others.
- **Reliable delivery:** the "last seen update" state only advances past posts
  that were actually delivered to at least one webhook. If Discord or the network
  hiccups, the run leaves state unchanged and retries on the next run instead of
  silently skipping a patch note.
- **Long pauses:** if the workflow was disabled long enough that more than ~10
  updates shipped (so the last-seen post scrolled out of the feed window), it
  posts only the newest item and re-baselines rather than dumping the backlog.

## Cost / plan notes

- **Public repo:** Actions minutes are free and unlimited — run every 10 minutes
  forever at no cost. Recommended.
- **Private repo:** the free plan includes 2,000 minutes/month and bills each run
  rounded up to a full minute. Every 10 minutes (~4,320 runs) exceeds that, so use
  `*/30 * * * *` in the workflow instead (~1,440 minutes) to stay under the cap.
  GitHub simply pauses workflows at the cap; it never charges you unless you've
  set a spending limit above $0.

## Scheduling quirks

- GitHub's cron scheduling is best-effort; runs can be delayed a few minutes.
- Scheduled workflows on free accounts are paused after 60 days of no repo
  activity, but the bot commits a state file whenever an update drops, which
  counts as activity. If CS2 ever goes 60 days without an update, press
  "Run workflow" manually once to re-enable it.