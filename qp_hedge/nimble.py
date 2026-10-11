"""Thin client for the Nimble web-data API (https://docs.nimbleway.com).

Used for the *live* layer: today's forward curve (EIA stopped publishing NYMEX
futures in April 2024) and market-context search. Historical replay never calls it,
so backtests stay reproducible. The API key is read from the NIMBLE_API_KEY env var
or a local .env file; it is never written into code or outputs.
"""
from __future__ import annotations

import json
import os
import urllib.request

BASE = "https://sdk.nimbleway.com/v2"


def api_key() -> str:
    k = os.environ.get("NIMBLE_API_KEY")
    d = os.path.abspath(os.getcwd())
    while not k:  # nearest .env in this or a parent directory (keeps keys out of the repo)
        p = os.path.join(d, ".env")
        if os.path.exists(p):
            for line in open(p):
                if line.startswith("NIMBLE_API_KEY="):
                    k = line.split("=", 1)[1].strip()
        if os.path.dirname(d) == d:
            break
        d = os.path.dirname(d)
    if not k:
        raise RuntimeError("set NIMBLE_API_KEY (env var or .env file)")
    return k


def _post(path: str, body: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {api_key()}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def extract(url: str, formats=("markdown",), **kw) -> dict:
    return _post("/extract", {"url": url, "formats": list(formats), **kw})


def search(query: str, max_results: int = 8, **kw) -> dict:
    return _post("/search", {"query": query, "max_results": max_results, **kw})
