import os

from openai import OpenAI

client = OpenAI()

PRIMARY_MODEL = "gpt-5-2025-08-07"
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gpt-4o")
REASONING = {"default": "o3-2025-04-16", "cheap": "o3"}
FINE_TUNED = "ft:gpt-4o-2024-08-06:acme::abc123"

# These are not model pins and must not be reported:
ALGO_TAG = "algo3-2025-04-16"
my_gpt_4o_backup = "my_gpt-4o_backup"
# GPT-4o was nice. The o3 approach is fine.
LEGACY = "gpt-5-2025-08-07-preview"  # model-pin-scanner: ignore


def ask(prompt: str) -> str:
    resp = client.chat.completions.create(model=PRIMARY_MODEL, messages=[{"role": "user", "content": prompt}])
    return resp.choices[0].message.content
