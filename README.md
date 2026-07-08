# CS2 Update Notifier

Posts Counter-Strike 2 patch notes to a Discord channel via webhook,
running for free on GitHub Actions every ~10 minutes.

## Setup

1. Create a Discord webhook: channel -> Edit Channel -> Integrations -> Webhooks -> New Webhook -> Copy URL.
2. Create a new GitHub repository and upload these files (keep the folder
   structure: `.github/workflows/cs2-updates.yml` must be in that exact path).
3. In the repo: Settings -> Secrets and variables -> Actions -> New repository secret.
   Name it `DISCORD_WEBHOOK_URL` and paste your webhook URL as the value.
4. Go to the Actions tab, enable workflows if prompted, then open
   "CS2 Update Notifier" and click "Run workflow" once to initialize.
   The first run records the current state without posting old updates.

That's it. New CS2 updates will appear in your channel within ~10-15 minutes
of Valve publishing them.

## Notes

- GitHub's cron scheduling is best-effort; runs can be delayed a few minutes.
- Scheduled workflows on free accounts are paused after 60 days of no repo
  activity, but the bot commits a state file whenever an update drops, which
  counts as activity. If CS2 somehow goes 60 days without an update, just
  press "Run workflow" manually once to re-enable it.
