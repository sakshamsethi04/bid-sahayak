"""Optional LLM layer. Used only to phrase the recommendation from the rule engine's
structured findings. If no key is configured, or the call fails, the deterministic
text is used, so the demo never depends on an external API."""
import json
import urllib.request

from ..config import LLM_API_KEY, LLM_MODEL, LLM_PROVIDER, llm_enabled

PROMPT = ("You are assisting an Indian government procurement officer evaluating a GeM bid. Rewrite the findings below as a "
          "concise 3-sentence recommendation. Do not approve or reject; the officer decides. Keep every fact and number.\n\n")


def _call(text: str) -> str:
    if LLM_PROVIDER == "anthropic":
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", method="POST",
                                     headers={"x-api-key": LLM_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                                     data=json.dumps({"model": LLM_MODEL or "claude-sonnet-4-5", "max_tokens": 300,
                                                      "messages": [{"role": "user", "content": PROMPT + text}]}).encode())
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.load(r)["content"][0]["text"].strip()
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", method="POST",
                                 headers={"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"},
                                 data=json.dumps({"model": LLM_MODEL or "gpt-4o-mini",
                                                  "messages": [{"role": "user", "content": PROMPT + text}]}).encode())
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.load(r)["choices"][0]["message"]["content"].strip()


def phrase_recommendation(deterministic: str):
    """Returns (text, source_label)."""
    if not llm_enabled():
        return deterministic, "Rule engine (deterministic mode, no LLM key configured)"
    try:
        return _call(deterministic), f"LLM ({LLM_PROVIDER}) over rule-engine findings"
    except Exception as e:  # network, quota, bad key...
        return deterministic, f"Rule engine (LLM unavailable: {type(e).__name__})"
