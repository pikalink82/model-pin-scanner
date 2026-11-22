# Decisions

Choices made while building `model-pin-scanner`, with the reason for each. Dated 2026-11-21 unless noted.

## Deprecation data

- **Anthropic dates are verified from Anthropic's SDK (2026-11-22).** Anthropic's Python SDK ships a deprecation table that warns on each deprecated model with its end-of-life date ([`messages.py` at 8baaef1, 2026-11-20](https://github.com/anthropics/anthropic-sdk-python/blob/8baaef1c4d23b2e4861d05da0dca65252e879eb8/src/anthropic/resources/messages/messages.py#L71-L92)). That is Anthropic's own published data, so the 15 entries it covers are `verified: true` with `verified_by` linking it. It matched every Anthropic date already in the file and added `claude-mythos-preview` (2026-06-30) plus the 100k and Instant 1.1 variants. It names no replacements, so verified entries have `replacement: null`; the replacements that search results attributed to the docs page are kept in `notes`. The table is not a complete history (it omits Claude 3.5 Sonnet, retired 2025-10-22), so a model missing from it is not proof that it is still served.
- **Removed 2026-11-22: `claude-opus-4-5-20251101` (2026-11-24) and `claude-opus-4-1-20250805` (2026-08-05).** Both came from trackers or a single snippet. The SDK table, updated 2026-11-20, lists Sonnet 4.5 retiring 2026-11-30 but neither Opus model, and it lists Opus 4 and Sonnet 4 since their retirement was announced. A retirement four days after that commit would be in it. Keeping them would fail people's CI on a date that is most likely wrong.
- **Every other entry is `verified: false`.** The build sandbox could not reach `platform.openai.com`, `developers.openai.com`, `platform.claude.com`, `docs.anthropic.com` or `ai.google.dev` (DNS blocked by the network policy). The only research tool that worked was a web search, which returns summarised snippets of those pages plus third-party trackers. That is not the same as reading the official page, so no entry is marked verified. Each entry still records the official page as `source_url`, because that is where a human should confirm it.
- **Snippets disagreed on several facts.** Where they did, the data file uses the value attributed to the official page and puts the conflict in `notes`. Where no value could be pinned down, `replacement` is `null` and reports say "not confirmed" rather than guessing.
- **Floating aliases are not entries unless the provider retires them.** OpenAI announced dated snapshots only, so `gpt-5`, `gpt-4o`, `o3` and so on are listed under "Other model IDs found" and never fail CI. Anthropic aliases such as `claude-sonnet-4-5` are added as `aliases` of their snapshot because Anthropic's aliases point at exactly one snapshot and stop with it. The SDK table confirms this: it gives each alias (`claude-sonnet-4-5`, `claude-opus-4-0`, `claude-3-7-sonnet-latest`, ...) the same date as its snapshot.
- **Already-retired models (added 2026-11-22).** Running the scanner on real SDK repos showed long-dead pins (`claude-3-opus-20240229`, `gpt-4-32k`, `gemini-1.5-flash`, ...) were not flagged at all, because the data only held upcoming shutdowns. The official pages still could not be fetched, so these entries came from training knowledge of those pages (to mid-2026). The Anthropic ones were then confirmed by the SDK table and are now verified; the 17 OpenAI, Google and Claude 3.5 Sonnet entries remain unverified. Only models whose retirement is certainly in the past were added; a wrong date changes the day count, not the SHUT DOWN status. No replacement is given, since the replacements recommended at the time are mostly retired too.
- **Entries left out on purpose:** `claude-haiku-4-5-20251001` (sources conflict: one says retired 2026-10-15, another says only a "not sooner than" date; the SDK table of 2026-11-20 does not list it) and `gpt-4.1-nano` (reported as not on the January list).
- **Cloud resellers are out of scope for dates.** Azure OpenAI, AWS Bedrock and Vertex AI run their own retirement schedules. The scanner still recognises Bedrock (`anthropic.<id>-v1:0`, `us.anthropic.<id>-v1:0`) and Vertex (`<name>@YYYYMMDD`) spellings and maps them to the first-party ID, so the reported date is the first-party date. The README says so.

### Unverified entries

Every ID below is `verified: false` in `src/model_pin_scanner/data/deprecations.yaml`. A test fails if an unverified entry is missing from this list.

| ID | Shutdown used | Replacement used | What is uncertain |
| --- | --- | --- | --- |
| `gpt-5-2025-08-07` | 2026-12-11 | gpt-5.6-sol | Replacement: sources say gpt-5.6-sol, gpt-6.1-sol or gpt-5.5; one forum post says 2026-12-10 |
| `gpt-5-mini-2025-08-07` | 2026-12-11 | none | Replacement |
| `gpt-5-nano-2025-08-07` | 2026-12-11 | none | Replacement |
| `gpt-5-pro-2025-10-06` | 2026-12-11 | none | Replacement |
| `o3-2025-04-16` | 2026-12-11 | none | Replacement |
| `o3-pro-2025-06-10` | 2026-12-11 | none | Replacement |
| `gpt-4o-2024-08-06` | 2027-01-14 | gpt-6-luna | Read from search snippets only |
| `gpt-4o-2024-11-20` | 2027-01-14 | gpt-6-luna | Read from search snippets only |
| `gpt-4o-mini-2024-07-18` | 2027-01-14 | gpt-6-luna | Sources say "GPT-4o mini" without the snapshot ID |
| `gpt-4.1-2025-04-14` | 2027-01-14 | gpt-6-luna | Read from search snippets only |
| `gpt-4.1-mini-2025-04-14` | 2027-01-14 | gpt-6-luna | Read from search snippets only |
| `gemini-2.0-flash-001` | 2026-06-01 | gemini-2.5-flash | Earlier reports said 2026-03-31 |
| `gemini-2.0-flash-lite-001` | 2026-06-01 | gemini-2.5-flash-lite | Read from search snippets only |
| `gemini-2.5-pro` | 2026-10-16 | none | Page snapshots say 2026-10-16, 2026-06-17 or no date |
| `gemini-2.5-flash` | 2026-10-16 | gemini-3.5-flash | Page snapshots say 2026-10-16 or 2026-06-17 |
| `claude-3-5-sonnet-20240620` | 2025-10-22 | none | Already retired; date from training knowledge, not the live page |
| `claude-3-5-sonnet-20241022` | 2025-10-22 | none | Already retired; date from training knowledge, not the live page |
| `gpt-4.5-preview-2025-02-27` | 2025-07-14 | none | Already retired; date from training knowledge, not the live page |
| `gpt-4-32k-0613` | 2025-06-06 | none | Already retired; date from training knowledge, not the live page |
| `gpt-4-32k-0314` | 2025-06-06 | none | Already retired; date from training knowledge, not the live page |
| `gpt-4-vision-preview` | 2024-12-06 | none | Already retired; date from training knowledge, not the live page |
| `gpt-4-1106-vision-preview` | 2024-12-06 | none | Already retired; date from training knowledge, not the live page |
| `gpt-3.5-turbo-0613` | 2024-09-13 | none | Already retired; date from training knowledge, not the live page |
| `gpt-3.5-turbo-16k-0613` | 2024-09-13 | none | Already retired; date from training knowledge, not the live page |
| `gpt-3.5-turbo-0301` | 2024-09-13 | none | Already retired; date from training knowledge, not the live page |
| `o1-preview-2024-09-12` | 2025-07-28 | none | Already retired; date from training knowledge, not the live page |
| `o1-mini-2024-09-12` | 2025-10-27 | none | Already retired; date from training knowledge, not the live page |
| `gemini-1.5-pro-002` | 2025-09-24 | none | Already retired; date from training knowledge, not the live page |
| `gemini-1.5-flash-002` | 2025-09-24 | none | Already retired; date from training knowledge, not the live page |
| `gemini-1.5-flash-8b-001` | 2025-09-24 | none | Already retired; date from training knowledge, not the live page |
| `gemini-1.5-pro-001` | 2025-05-24 | none | Already retired; date from training knowledge, not the live page |
| `gemini-1.5-flash-001` | 2025-05-24 | none | Already retired; date from training knowledge, not the live page |

## Scanner

- **Pattern-based discovery, then lookup.** The scanner finds anything shaped like a model ID from known families (OpenAI `gpt-*`, `o1`-`o9`, embeddings, Anthropic `claude-*`, Google `gemini-*`, Mistral, Cohere `command-r`, DeepSeek, xAI `grok-*`), normalises it, and looks it up in the data file. Unknown IDs still appear in an inventory so a reviewer sees every pin, not just the risky ones.
- **Lowercase only.** Real API model IDs are lowercase. Matching case-sensitively keeps prose such as "GPT-4o is great" out of the report.
- **Boundaries.** An ID must not be preceded or followed by a letter, digit, underscore or hyphen. That rejects `algo3-2025-04-16`, `my_gpt-4o_backup` and `gpt-5-2025-08-07-preview` (a different ID, reported as unknown). `/`, `.` and `:` are allowed before an ID so `openai/gpt-4o-...`, `anthropic.claude-...`, `models/gemini-...` and `ft:gpt-4o-...:org::id` all match.
- **Bare `o1`..`o9`** only count inside matching quotes (`"o3"`), because a bare `o3` in text is usually not a model.
- **`claude-` and `gemini-` need a version or family word next** (`claude-3`, `claude-sonnet`, `gemini-2`), so `claude-code` and `gemini-cli` are ignored.
- **Default file set** is code, config, env files, Dockerfiles, Terraform and notebooks. Markdown and plain text are skipped by default because they mostly mention models rather than pin them; `--all-files` includes them. Vendored and build directories (`node_modules`, `.venv`, `dist`, ...) are always skipped. Files over 2 MB and binary files (NUL byte in the first 8 KB) are skipped.
- **Line-level opt-out**: a line containing `model-pin-scanner: ignore` is skipped.
- **Day 0 counts as shut down.** On the shutdown date the provider stops serving the model, so `days_remaining <= 0` is "shut down" and always fails when a threshold is set.
- **`--fail-within` is opt-in on the CLI** (report-only by default) and defaults to 30 in the GitHub Action, where failing CI is the point.
- **"Today" is the UTC date** unless `--today` is given, so CI runners in any time zone agree.

## Regress

- **Standard-library HTTP only.** The providers use `urllib` so the package has one dependency (PyYAML). Each provider takes an injectable transport, which is how the tests mock the network.
- **No temperature is sent.** OpenAI reasoning models reject `temperature`; sending none keeps one code path. Outputs are therefore not deterministic, and the README says to treat `minor` and `changed` as signals for human review.
- **Status ladder:** identical (same after collapsing whitespace) < minor (similarity at or above `--threshold`, default 0.9, using `difflib`) < changed < regressed (an `expect_contains` string the old model produced is missing from the new output). A provider error on either side is `error` and ranks with regressed.
- **`--fail-on` defaults to `never`** so a first run only reports.
- **Provider auto-detection** is by ID prefix (`gpt-`/`o<n>`/`chatgpt-`/`ft:` OpenAI, `claude-` Anthropic, `gemini-` Google); anything else needs `--provider`.
- **API shapes used** (from my knowledge, not checked against live docs in this session): OpenAI Chat Completions with `max_completion_tokens`, Anthropic Messages with `anthropic-version: 2023-06-01`, Gemini `v1beta/models/{model}:generateContent` with `x-goog-api-key`. Only exercised against mocked transports.
- **Custom base URLs** (`OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL`, `GEMINI_BASE_URL`) must be https so keys are never sent in clear text.

## Packaging and CI

- **Hatchling build backend, `src/` layout**, entry point `model-pin-scanner`, data file shipped inside the package. Installable with `pipx install .` or from a Git URL.
- **Composite action** installs the package from the action's own checkout (`github.action_path`) so it needs no PyPI release, passes every input through environment variables (never `${{ inputs.* }}` inside a script, which would allow shell injection), writes the Markdown report to the job summary, and emits file annotations.
- **Repository was local only at first.** `gh` was not authenticated in the build environment. Pikalink created the GitHub repos on 2026-11-21 and they were pushed then; this one is public, at Pikalink's request.
- **The action pins `actions/setup-python@v5` by tag**, not by commit SHA, because the SHA could not be looked up from the sandbox. HUMAN_TODO.md has the item to pin it.
