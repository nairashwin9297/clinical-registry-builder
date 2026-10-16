"""Minimal Ollama client for live mode (standard library only, no extra dependency)."""

import json
import urllib.error
import urllib.request

from django.conf import settings

from . import extraction_core as core

TIMEOUT_SECONDS = 600  # a long note on a laptop CPU can take minutes


def _post(path, payload):
    req = urllib.request.Request(f"{settings.OLLAMA_URL}{path}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read())


def generate(messages):
    """Same contract as the notebook's generate(): chat messages in, reply text out."""
    payload = {
        "model": settings.OLLAMA_MODEL,
        # Our messages use Gemma's list-of-parts content; Ollama wants plain strings.
        "messages": [{"role": m["role"], "content": "".join(p["text"] for p in m["content"])} for m in messages],
        "stream": False,
        # Match the notebook: greedy decoding and the same output limit. Ollama's default context
        # window is too small for the longest notes plus the prompt, so raise it.
        "options": {"temperature": 0, "num_predict": core.MAX_NEW_TOKENS, "num_ctx": 8192},
    }
    return _post("/api/chat", payload)["message"]["content"]


def status():
    """Is Ollama reachable, and is the configured model pulled?"""
    try:
        with urllib.request.urlopen(f"{settings.OLLAMA_URL}/api/tags", timeout=5) as resp:
            models = [m["name"] for m in json.loads(resp.read()).get("models", [])]
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"reachable": False, "model_available": False, "error": str(e),
                "url": settings.OLLAMA_URL, "model": settings.OLLAMA_MODEL}
    wanted = settings.OLLAMA_MODEL
    available = any(m == wanted or m == f"{wanted}:latest" for m in models)
    return {"reachable": True, "model_available": available, "error": "",
            "url": settings.OLLAMA_URL, "model": wanted}
