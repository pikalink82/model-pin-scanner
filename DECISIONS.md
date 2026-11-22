# Decisions

Choices made while building `model-pin-scanner`, with the reason for each. Dated 2026-11-21 unless noted.

## Deprecation data

- **Rebuilt from the official pages on 2026-11-22.** Once the build network could reach them, every entry was regenerated from OpenAI's deprecations page (upcoming and past tables), Anthropic's model deprecations page (status table and deprecation history) and Google's Gemini deprecations page (now served from aistudio.google.com). 140 of the 145 entries are `verified: true`; the five that are not are listed below. The earlier data, built from search snippets and training knowledge, had the right OpenAI dates but wrong replacements, wrong Gemini 2.5 dates (2026-10-16 instead of 2026-12-01), and missed the aliases below.
- **Floating aliases follow the page.** OpenAI's page retires many aliases together with their snapshots: `gpt-5`, `gpt-5-mini`, `gpt-5-nano`, `gpt-5-pro`, `o3` and `o3-pro` on 2026-12-11, and `gpt-4`, `gpt-4-turbo`, `gpt-3.5-turbo`, `gpt-4.1-nano`, `o1`, `o1-pro`, `o3-mini` and `o4-mini` already on 2026-10-23. Those are now aliases of their entries. The GPT-4o and GPT-4.1 rows (2027-01-14) list snapshots only, so `gpt-4o`, `gpt-4o-mini`, `gpt-4.1` and `gpt-4.1-mini` are not entries and never fail CI. The earlier assumption that "OpenAI announced dated snapshots only" was wrong and hid the most common pins.
- **Anthropic aliases.** The page names `claude-sonnet-4-5` as part of the Sonnet 4.5 retirement. `claude-opus-4-0`, `claude-sonnet-4-0`, `claude-3-7-sonnet-latest` and `claude-3-5-haiku-latest` come from the deprecation table in Anthropic's Python SDK, and `claude-opus-4-1`, `claude-3-opus-latest` and `claude-3-5-sonnet-latest` from training knowledge of what those aliases pointed at; each entry's `notes` says which.
- **`verified_by`** links an official source other than the docs page. Only `claude-1.3-100k` and `claude-instant-1.1-100k` use it: the docs page lists the Claude 1 family but not these two, and Anthropic's SDK table gives the same 2024-11-06 date.
- **Corrections from the 2026-11-22 pass, for the record.** `claude-opus-4-1-20250805` was briefly removed because the SDK table did not list it; the page shows it retired 2026-08-05, so it is back. `claude-opus-4-5-20251101` stays out (active; 2026-11-24 was a "not sooner than" date). `claude-mythos-preview` is out: deprecated with retirement "to be announced", so the SDK's 2026-06-30 date was not a shutdown. Claude 3.5 Sonnet retired 2025-10-28, not 2025-10-22.
- **Google dates are earliest possible shutdowns**, as the page says; Google promises advance notice of the exact date. Several Gemini models are routed to a newer model on that date instead of failing (`gemini-2.5-pro` to `gemini-3.8-flash`, `gemini-2.5-flash` to `gemini-3.5-flash-lite`); `notes` says so. Models that already route with no shutdown date (`gemini-3.5-flash`, `gemini-3.7-flash`) are not entries.
- **Only IDs the scanner can detect are included.** Image, video, music and robotics models (Imagen, Veo, Lyria) and old completions models (`babbage-002`, `davinci-002`) are left out. The scanner's pattern was widened the same day for `gpt-image-*`, `gpt-realtime*`, `gpt-audio*`, `chatgpt-image-latest`, `codex-mini-latest` and `computer-use-preview`, which have upcoming shutdowns.
- **Entries left out on purpose:** `claude-haiku-4-5-20251001` is active ("not sooner than" 2026-10-15 on the page).
- **Cloud resellers are out of scope for dates.** Azure OpenAI, AWS Bedrock and Vertex AI run their own retirement schedules. The scanner still recognises Bedrock (`anthropic.<id>-v1:0`, `us.anthropic.<id>-v1:0`) and Vertex (`<name>@YYYYMMDD`) spellings and maps them to the first-party ID, so the reported date is the first-party date. The README says so.

### Unverified entries

Every ID below is `verified: false` in `src/model_pin_scanner/data/deprecations.yaml`. A test fails if an unverified entry is missing from this list.

| ID | Shutdown used | Replacement used | What is uncertain |
| --- | --- | --- | --- |
| `gemini-1.5-pro-002` | 2025-09-24 | none | Not on Google's current page (it starts at Gemini 2.0); date from training knowledge |
| `gemini-1.5-flash-002` | 2025-09-24 | none | Same |
| `gemini-1.5-flash-8b-001` | 2025-09-24 | none | Same |
| `gemini-1.5-pro-001` | 2025-05-24 | none | Same |
| `gemini-1.5-flash-001` | 2025-05-24 | none | Same |

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
