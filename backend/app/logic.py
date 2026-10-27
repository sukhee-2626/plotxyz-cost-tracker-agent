"""Original deterministic implementation for Cost Tracker (plotxyz-cost-tracker-agent)."""
from __future__ import annotations

import ast
import csv
import io
import json
import math
import os
import re
import statistics
import time
from collections import Counter, defaultdict, deque


class LogicError(ValueError):
    """Raised when supplied input cannot be processed."""


def _text(payload, key, min_len=1, max_len=20000):
    value = payload.get(key)
    if not isinstance(value, str):
        raise LogicError(f"'{key}' must be a string")
    value = value.strip()
    if len(value) < min_len:
        raise LogicError(f"'{key}' is required")
    if len(value) > max_len:
        raise LogicError(f"'{key}' exceeds {max_len} characters")
    return value


def _num(payload, key, default=None, lo=None, hi=None):
    value = payload.get(key, default)
    if value is None or value == "":
        if default is None:
            raise LogicError(f"'{key}' is required")
        return default
    if isinstance(value, bool):
        raise LogicError(f"'{key}' must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise LogicError(f"'{key}' must be numeric")
    if lo is not None and number < lo:
        raise LogicError(f"'{key}' must be at least {lo}")
    if hi is not None and number > hi:
        raise LogicError(f"'{key}' must be at most {hi}")
    return number


def _json(payload, key, expected=None, max_len=200000):
    raw = payload.get(key)
    if isinstance(raw, (dict, list)):
        data = raw
    elif isinstance(raw, str):
        if len(raw) > max_len:
            raise LogicError(f"'{key}' exceeds {max_len} characters")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LogicError(f"'{key}' is not valid JSON: {exc.msg} at line {exc.lineno}")
    else:
        raise LogicError(f"'{key}' must be JSON")
    if expected is not None and not isinstance(data, expected):
        name = expected.__name__ if hasattr(expected, "__name__") else str(expected)
        raise LogicError(f"'{key}' must be a JSON {name}")
    return data


def _csv(payload, key, max_rows=5000):
    text = _text(payload, key, max_len=2000000)
    try:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise LogicError(f"'{key}' must include a header row")
        columns = [str(c).strip() for c in reader.fieldnames if c and str(c).strip()]
        if not columns:
            raise LogicError(f"'{key}' must include named columns")
        rows = []
        for index, raw in enumerate(reader):
            if index >= max_rows:
                raise LogicError(f"'{key}' exceeds {max_rows} rows")
            rows.append({col: (raw.get(col) or "").strip() for col in columns})
    except csv.Error as exc:
        raise LogicError(f"'{key}' is not valid CSV: {exc}")
    if not rows:
        raise LogicError(f"'{key}' must include at least one data row")
    return columns, rows


STOPWORDS = {'could', 'than', 'your', 'does', 'in', 'have', 'you', 'is', 'they', 'then', 'will', 'it', 'of', 'their', 'are', 'about', 'should', 'into', 'not', 'were', 'would', 'no', 'as', 'from', 'had', 'may', 'a', 'i', 'for', 'he', 'can', 'over', 'under', 'the', 'our', 'to', 'might', 'she', 'be', 'do', 'has', 'an', 'if', 'this', 'at', 'by', 'that', 'we', 'and', 'with', 'its', 'did', 'was', 'or', 'on'}


def _tokens(text):
    return [w for w in re.findall(r"[a-z0-9][a-z0-9_+-]{1,}", text.lower()) if w not in STOPWORDS]


def _sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip(" -•\t") for p in parts if len(p.strip()) > 2]


def provider_status():
    """Report which optional model providers are configured (never exposes secrets)."""
    ollama = bool(os.getenv("OLLAMA_BASE_URL"))
    openai = bool(os.getenv("OPENAI_BASE_URL") and os.getenv("OPENAI_MODEL"))
    return {"ollama_compatible": ollama, "openai_compatible": openai}


def _llm(messages, temperature=0.2):
    """Call an explicitly configured OpenAI-compatible endpoint; return None when unavailable."""
    base = os.getenv("OPENAI_BASE_URL", "").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "")
    if not base or not model:
        ollama = os.getenv("OLLAMA_BASE_URL", "").rstrip("/")
        if not ollama:
            return None
        base = f"{ollama}/v1"
        model = os.getenv("OLLAMA_MODEL", "")
    if not model:
        return None
    try:
        import httpx

        headers = {"Content-Type": "application/json"}
        key = os.getenv("OPENAI_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        with httpx.Client(timeout=20) as client:
            response = client.post(
                f"{base}/chat/completions",
                headers=headers,
                json={"model": model, "messages": messages, "temperature": temperature},
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"]).strip()
    except Exception:
        return None


def _result(summary, result, warnings=None):
    return {"summary": summary, "result": result, "warnings": warnings or []}


def agent_cost_tracker(payload):
    usage = _json(payload, "usage", list)
    budget = _num(payload, "budget_usd", default=None, lo=0)
    if not usage:
        raise LogicError("supply at least one usage record")
    rows, by_provider, by_model, total = [], defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0}), defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0}), 0.0
    for index, record in enumerate(usage[:500]):
        if not isinstance(record, dict):
            raise LogicError(f"usage record {index} must be an object")
        model = str(record.get("model") or "unknown")
        provider = str(record.get("provider") or "default")
        tokens_in = float(record.get("tokens_in", 0) or 0)
        tokens_out = float(record.get("tokens_out", 0) or 0)
        calls = float(record.get("calls", 1) or 1)
        rate = float(record.get("rate_per_1k", 0) or 0)
        tokens = tokens_in + tokens_out
        cost = (tokens / 1000) * rate
        total += cost
        rows.append([index + 1, provider, model, int(calls), int(tokens), round(cost, 6)])
        p = by_provider[provider]
        p["calls"] += calls
        p["tokens"] += tokens
        p["cost"] += cost
        m = by_model[model]
        m["calls"] += calls
        m["tokens"] += tokens
        m["cost"] += cost
    findings = []
    if budget is not None:
        remaining = budget - total
        status = "on track" if remaining >= 0 else "over budget"
        findings.append({"title": f"Budget {status}", "severity": "high" if remaining < 0 else "info", "detail": f"Spent {total:.2f} USD of {budget:.2f} USD; {remaining:.2f} USD remaining."})
        if remaining < 0:
            findings.append({"title": "Budget exceeded", "severity": "high", "detail": f"Spending exceeds the configured budget by {abs(remaining):.2f} USD."})
    provider_rows = [[p, d["calls"], d["tokens"], round(d["cost"], 4)] for p, d in sorted(by_provider.items(), key=lambda kv: -kv[1]["cost"])]
    model_rows = [[m, d["calls"], d["tokens"], round(d["cost"], 4)] for m, d in sorted(by_model.items(), key=lambda kv: -kv[1]["cost"])]
    return _result(
        f"Tracked {len(usage)} usage record(s) across {len(by_provider)} provider(s): {total:.2f} USD total.",
        {
            "metrics": {"records": len(usage), "providers": len(by_provider), "models": len(by_model), "total_usd": round(total, 4)},
            "table": {"columns": ["#", "Provider", "Model", "Calls", "Tokens", "Cost (USD)"], "rows": rows},
            "provider_breakdown": provider_rows,
            "model_breakdown": model_rows,
            "findings": findings,
            "items": ["Cache repeated prompts to reduce token volume.", "Route simple tasks to cheaper models.", "Set per-model rate alerts before the next billing cycle."],
        },
        [],
    )


run = agent_cost_tracker
