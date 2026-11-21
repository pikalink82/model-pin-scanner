# Human to-do

Things that need your login, money or judgement. In priority order.

## 1. Verify the deprecation data (most important)

Every entry in `src/model_pin_scanner/data/deprecations.yaml` is `verified: false`: the official pages could not be opened from the build sandbox. Open each page, compare it with the table in DECISIONS.md, fix any date or replacement that differs, and flip `verified` to `true` for each entry you confirm.

- https://platform.openai.com/docs/deprecations
- https://platform.claude.com/docs/en/about-claude/model-deprecations
- https://ai.google.dev/gemini-api/docs/deprecations

Then check the list and the tests:

```bash
.venv/bin/model-pin-scanner data
.venv/bin/pytest
```

Also decide whether to add `claude-haiku-4-5-20251001` and `gpt-4.1-nano-2025-04-14` once their status is clear (left out because sources conflicted).

## 2. Create the GitHub repo and push (done)

Done 2026-11-21: pushed to https://github.com/pikalink82/model-pin-scanner (public). Still open: check the first CI run on the Actions tab; the workflow and the action's self-test have never run on GitHub.

## 3. Tag a release so others can use the action

```bash
git tag -a v0.1.0 -m "v0.1.0"
git push origin v0.1.0
```

The repo is created public (Pikalink approved this) so other people's workflows can use `uses: <you>/model-pin-scanner@v0.1.0`. Replace `<you>` in README.md with your GitHub username.

## 4. Pin the setup-python action by commit SHA

`action.yml` and `.github/workflows/ci.yml` use `actions/setup-python@v5` and `actions/checkout@v4` by tag. Look up the current commit SHAs on GitHub and pin them, or let Dependabot or Renovate do it.

## 5. Try one real regress run (optional, costs a few cents)

Only if you want to confirm the live API formats. Set one key in your shell, not in a file:

```bash
export OPENAI_API_KEY=...
model-pin-scanner regress tests/fixtures/golden.yaml --old gpt-4o-2024-08-06 --new gpt-4.1-2025-04-14
```

## 6. Publish to PyPI (optional)

Needs a PyPI account and a trusted-publisher setup for the repo. Until then, install with `pipx install git+https://github.com/<you>/model-pin-scanner.git`.
