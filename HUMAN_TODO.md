# Human to-do

Things that need your login, money or judgement. In priority order.

## 1. Verify the deprecation data (done)

Done 2026-11-22: every entry was rebuilt from the official OpenAI, Anthropic and Google pages, read directly, and 140 of 145 are `verified: true`. Still open: the five Gemini 1.5 entries (not on Google's current page), and a re-check before each release, since providers add rows. The pages are listed in each entry's `source_url`.

## 2. Create the GitHub repo and push (done)

Done 2026-11-21: pushed to https://github.com/pikalink82/model-pin-scanner (public). Still open: check the first CI run on the Actions tab; the workflow and the action's self-test have never run on GitHub.

## 3. Tag a release so others can use the action

```bash
git tag -a v0.1.0 -m "v0.1.0"
git push origin v0.1.0
```

The repo is public (Pikalink approved this), so other people's workflows can already use `uses: pikalink82/model-pin-scanner@main`. Tag once the deprecation data is verified (item 1), then change `@main` to `@v0.1.0` in the README's workflow example.

## 4. Pin the setup-python action by commit SHA (done)

Done 2026-11-22: `action.yml` and the CI workflow pin every action by commit SHA, and `.github/dependabot.yml` opens weekly update PRs for them.

## 5. Try one real regress run (optional, costs a few cents)

Only if you want to confirm the live API formats. Set one key in your shell, not in a file:

```bash
export OPENAI_API_KEY=...
model-pin-scanner regress tests/fixtures/golden.yaml --old gpt-4o-2024-08-06 --new gpt-4.1-2025-04-14
```

## 6. Publish to PyPI (optional)

Needs a PyPI account and a trusted-publisher setup for the repo. Until then, install with `pipx install git+https://github.com/pikalink82/model-pin-scanner.git`.
