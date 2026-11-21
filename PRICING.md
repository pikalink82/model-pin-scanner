# Pricing

**One-line pitch:** a CI check that tells you which LLM model IDs in your code are about to be switched off, how many days you have, and what your prompts return on the replacement.

## Who pays

- **Buyers:** engineering leads and platform teams at companies with several services calling OpenAI, Anthropic or Gemini, where a retired snapshot means a production outage. Agencies that maintain LLM features for many clients are a second group.
- **Not buyers:** solo developers and hobby projects. They get the open-source CLI and action for free, which is also the distribution channel.

## What to charge

| Tier | Price | What it includes |
| --- | --- | --- |
| Open source | Free | CLI, GitHub Action, bundled data file updated by releases. |
| Team | $19 per month per organisation (or $190 per year) | Hosted, human-checked deprecation feed the action pulls daily, so a new notice fails CI without upgrading the action; Slack or email alert when a new notice affects a scanned repo; up to 25 repos. |
| Business | $99 per month | Unlimited repos, org-wide dashboard of pins and deadlines, Azure, Bedrock and Vertex schedules, scheduled `regress` runs with stored history. |
| Migration audit | $500 to $1,500 one-off | Scan, golden-prompt set written with the client, regression report and a migration plan for a specific shutdown date. |

## Why these numbers

- The cost of one missed shutdown (an outage plus an emergency migration) is far above $19 a month, so the price is set to be an easy expense-card purchase, not to capture that value.
- The paid value is the curated, verified data and alerts, not the scanner code; that is what a free fork cannot copy cheaply.
- The one-off audit fits the deadline-driven demand around big shutdown dates such as 2026-12-11 and 2027-01-14.

These prices are a starting guess, not market-tested. Nothing in the repo takes payment, and no paid service exists yet.
