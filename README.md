# model-pin-scanner

Find pinned LLM model IDs in a repo before the provider switches them off, and diff what your prompts return when you move to the replacement.

## What this does and who it's for

Teams that call OpenAI, Anthropic or Google models usually pin a dated snapshot (`gpt-5-2025-08-07`, `claude-sonnet-4-5-20250929`) in code, config, `.env` files, Dockerfiles or Terraform. Providers retire those snapshots on fixed dates, often with 60 to 180 days' notice, and the first sign is usually a 404 in production.

`model-pin-scanner` has three commands:

- `scan` walks a directory, finds every model ID it recognises, checks each against a `deprecations.yaml` data file (model ID, shutdown date, recommended replacement, source URL), and reports what is at risk and how many days remain, in Markdown or JSON. With `--fail-within N` it exits 1 when anything shuts down within N days, which is what the bundled GitHub Action uses to fail CI.
- `regress` runs a file of golden prompts against the old and the new model through a pluggable provider (OpenAI, Anthropic, Gemini, or canned mock responses) and writes a diff report: identical, minor, changed, or regressed (an expected phrase disappeared).
- `data` validates and lists the deprecation data.

It is for developers and platform teams who own LLM integrations and want a CI check plus a quick way to see what an upgrade changes. It needs no API keys to scan.

## Install

Python 3.11 or newer.

```bash
pipx install git+https://github.com/pikalink82/model-pin-scanner.git
```

From a checkout:

```bash
pipx install .
```

For development:

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

## Usage

```bash
model-pin-scanner scan .
model-pin-scanner scan . --fail-within 30
model-pin-scanner scan src --format json --output pin-report.json
model-pin-scanner scan . --exclude "tests/*" --exclude legacy --all-files
model-pin-scanner scan . --data my-deprecations.yaml --today 2026-12-01
model-pin-scanner data
```

`scan` options:

| Option | Meaning |
| --- | --- |
| `--fail-within DAYS` | Exit 1 if a pinned model shuts down within DAYS days or already has. Without it, `scan` only reports. |
| `--warn-within DAYS` | Window for the WARNING status (default 90). |
| `--format markdown\|json` | Output format (default Markdown). |
| `--output FILE` | Write the report to FILE. |
| `--data FILE` | Use your own deprecations file instead of the bundled one. |
| `--exclude GLOB` | Skip matching paths (repeatable). Matches the path as reported or the path under the scan root. |
| `--all-files` | Also scan Markdown, text and other files outside the default code and config set. |
| `--today YYYY-MM-DD` | Evaluate days remaining as of this date (default: today in UTC). |
| `--github-annotations` | Print `::error`/`::warning` lines to stderr for GitHub file annotations. |

Exit codes: 0 fine, 1 threshold hit (or `regress --fail-on` triggered), 2 bad input (missing path, malformed data or golden file, missing API key).

To silence one line, put `model-pin-scanner: ignore` on it.

### What gets matched

- Dated snapshots and aliases from OpenAI (`gpt-*` including `gpt-image-*`, `gpt-realtime*` and `gpt-audio*`, `o1`..`o9`, `chatgpt-4o-latest`, `chatgpt-image-latest`, `codex-mini-latest`, `computer-use-preview`, embeddings, `whisper-*`, `tts-*`, `dall-e-*`), Anthropic (`claude-*`), Google (`gemini-*`), Mistral, Cohere `command-r`, DeepSeek and xAI `grok-*`.
- Provider spellings are mapped back to the first-party ID: `openai/gpt-4o-2024-08-06`, `ft:gpt-4o-2024-08-06:org::id` (fine-tunes), `models/gemini-2.0-flash-001`, Vertex `claude-sonnet-4@20250514`, Bedrock `anthropic.claude-3-7-sonnet-20250219-v1:0` and `us.anthropic....`. The date reported is the first-party date; Azure, Bedrock and Vertex run their own schedules.
- Not matched: IDs inside longer words (`algo3-2025-04-16`, `my_gpt-4o_backup`), longer IDs that merely start with a known one (`gpt-5-2025-08-07-preview` is reported as a separate, unknown ID), capitalised prose (`GPT-4o`), a bare `o3` outside quotes, and tool names such as `claude-code` or `gemini-cli`.
- Floating aliases are flagged when the provider's page retires them: OpenAI retired `gpt-4`, `gpt-4-turbo`, `gpt-3.5-turbo`, `o1`, `o3-mini` and `o4-mini` on 2026-10-23 and retires `gpt-5`, `gpt-5-mini`, `o3` and others on 2026-12-11. Aliases the page does not list, such as `gpt-4o` and `gpt-4.1`, appear under "Other model IDs found" and never fail CI.
- Skipped: `.git`, `node_modules`, virtualenvs, build output, binary files and files over 2 MB. Markdown and plain text are skipped unless `--all-files` is set.

### Regress

Golden prompts are YAML (or JSONL, one object per line):

```yaml
system: You are a concise support assistant.
prompts:
  - id: refund-policy
    prompt: "Can I get a refund for wilted roses? Answer in two sentences."
    expect_contains: ["refund", "photo"]
  - id: card-message
    prompt: "Write a 10-word birthday card message."
    max_tokens: 64
```

Real calls need the matching key in the environment: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GEMINI_API_KEY` (or `GOOGLE_API_KEY`). The provider is picked from the model ID prefix, or set with `--provider`. Optional `OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL` and `GEMINI_BASE_URL` must be https.

```bash
model-pin-scanner regress golden.yaml --old gpt-4o-2024-08-06 --new gpt-6-luna
model-pin-scanner regress golden.yaml --old claude-sonnet-4-5-20250929 --new claude-sonnet-5-5 --fail-on regressed
model-pin-scanner regress golden.yaml --old a --new b --provider mock --mock-responses responses.yaml
```

Statuses: `identical` (same text after collapsing whitespace), `minor` (similarity at or above `--threshold`, default 0.9), `changed`, `regressed` (an `expect_contains` phrase the old model produced is missing from the new output), `error` (a provider call failed). `--fail-on never|regressed|changed` sets the exit code; errors count as regressions. Model output is not deterministic, so treat `minor` and `changed` as prompts to read, not verdicts.

To add a provider, write a class with a `name` and a `complete(request: CompletionRequest) -> str` method (see `src/model_pin_scanner/providers.py`).

## Example run

Against the fixture repo in this project:

```bash
model-pin-scanner scan tests/fixtures/sample_repo --today 2026-11-21 --fail-within 30
```

```text
# Model pin scan

Scanned 6 files on 2026-11-21. Found 15 references to models with a known shutdown date.
11 fail the 30-day threshold (shut down or within 30 days).
Deprecation data last reviewed 2026-11-22.

| Status | Model | Days left | Shutdown | Replacement | Location | Verified |
| --- | --- | ---: | --- | --- | --- | --- |
| SHUT DOWN | `claude-3-7-sonnet-20250219-v1:0` (= `claude-3-7-sonnet-20250219`) | -275 | 2026-02-19 | claude-sonnet-5-5 | `tests/fixtures/sample_repo/config/models.yaml:5` | [yes](...) |
| SHUT DOWN | `gemini-2.0-flash` | -173 | 2026-06-01 | gemini-3.6-flash | `tests/fixtures/sample_repo/.env.example:2` | [yes](...) |
| CRITICAL | `gpt-5-2025-08-07` | 20 | 2026-12-11 | gpt-6.1-sol | `tests/fixtures/sample_repo/app/llm.py:7` | [yes](...) |
| WARNING | `gpt-4o-mini-2024-07-18` | 54 | 2027-01-14 | gpt-6-luna | `tests/fixtures/sample_repo/Dockerfile:2` | [yes](...) |
...

## Other model IDs found (no known shutdown)

| Model | Kind | Count | First location |
| --- | --- | ---: | --- |
| `gpt-4o` | alias | 1 | `tests/fixtures/sample_repo/app/llm.py:8` |
...
```

Exit code 1. A regress run with canned responses:

```bash
cd tests/fixtures
model-pin-scanner regress golden.yaml --old gpt-4o-2024-08-06 --new gpt-6-luna --provider mock --mock-responses mock_responses.yaml
```

```text
# Regression: `gpt-4o-2024-08-06` -> `gpt-6-luna`

4 prompts. 1 identical, 1 minor, 1 changed, 1 regressed, 0 error. Similarity threshold 0.9.

| Prompt | Status | Similarity | Lost expectations |
| --- | --- | ---: | --- |
| `refund-policy` | regressed | 0.36 | refund, photo |
| `hours` | identical | 1.00 | - |
| `card-message` | minor | 0.94 | - |
| `delivery-zip` | changed | 0.73 | - |
```

followed by a unified diff per changed prompt.

## GitHub Action

```yaml
name: Model pins
on:
  pull_request:
  schedule:
    - cron: "17 6 * * 1"
jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pikalink82/model-pin-scanner@main
        with:
          fail-within-days: "30"
          exclude: |
            tests/*
```

Inputs: `path` (default `.`), `fail-within-days` (default `30`), `warn-within-days` (`90`), `data-file`, `exclude` (one glob per line), `all-files` (`false`), `python-version` (`3.12`, used only inside the action). Outputs: `at-risk`, `failing`, `report-json`. The Markdown report goes to the job summary, and each at-risk line gets a file annotation. A weekly schedule matters: a pin that was fine last month can cross the threshold without any code change.

## The data file

`src/model_pin_scanner/data/deprecations.yaml` ships with the package. Each entry has `id`, `provider`, `shutdown_date`, `replacement` (or `null`), `source_url`, `verified`, and optional `verified_by`, `aliases` and `notes`. `model-pin-scanner data` validates it and prints the table. Pass `--data` to use your own file, for example to add internal or Azure-specific dates.

## Verified vs. unverified

Verified by the automated tests (150 tests, run on Python 3.11 and 3.13):

- Detection and false-positive handling for every spelling listed under "What gets matched", including Bedrock, Vertex, OpenRouter-style prefixes and fine-tune IDs.
- Day counting, statuses, `--fail-within` exit codes, Markdown, JSON and annotation output against the fixture repo.
- Data file validation and that every seeded entry cites its provider's official page.
- `regress` end to end with mock responses; each HTTP provider's request shape, response parsing, retries and error handling against a fake transport.
- The action's scan step, run locally with bash the way a runner would (inputs, outputs, summary, annotations, exit code). The wheel builds and installs with its data file.

Not verified:

- **The data was rebuilt from the official pages on 2026-11-22**: OpenAI's deprecations page, Anthropic's model deprecations page and Google's Gemini deprecations page, read directly that day. 140 of 145 entries are verified against them. The five Gemini 1.5 entries are not, because Google's page no longer lists models older than Gemini 2.0; they come from training knowledge and are long past retirement either way. Google's dates are its published earliest possible shutdown dates. Providers change these pages, so re-check before relying on a date months out.
- Run on real repos (2026-11-22, shallow clones of openai-python, anthropic-sdk-python, openai-agents-python and python-genai): no crashes, and the pins found matched what a person reading the code would call pins. SDK repos list every model ID in their type definitions, so they produce many findings; exclude those paths with `--exclude` if you scan an SDK.
- No real API call was made. The OpenAI, Anthropic and Gemini request formats follow the public APIs as known at build time but were tested only against mocks.
- Windows runners are untested. The CI workflow runs on GitHub (ubuntu).

## License

MIT, see LICENSE.
