from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional
from urllib import error, parse, request
from zoneinfo import ZoneInfo

import streamlit as st

IST = ZoneInfo("Asia/Kolkata")
TABLE = "screener_state"
TIMEOUT_SECONDS = 12


def today_iso() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def watchlist_key(date_text: Optional[str] = None) -> str:
    return f"watchlist:{date_text or today_iso()}"


def execution_key(date_text: Optional[str] = None) -> str:
    return f"execution:{date_text or today_iso()}"


def _credentials() -> tuple[Optional[str], Optional[str]]:
    try:
        url = str(st.secrets.get("SUPABASE_URL", "")).strip().rstrip("/")
        key = str(st.secrets.get("SUPABASE_KEY", "")).strip()
    except Exception:
        return None, None
    return (url or None, key or None)


def is_configured() -> bool:
    url, key = _credentials()
    return bool(url and key)


def _headers(key: str, prefer: Optional[str] = None) -> dict[str, str]:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def load_payload(state_key: str) -> tuple[bool, Optional[Any], Optional[str]]:
    """Return (storage_reachable, payload, error_message)."""
    base_url, api_key = _credentials()
    if not base_url or not api_key:
        return False, None, "Supabase secrets are missing."

    query = parse.urlencode({"key": f"eq.{state_key}", "select": "payload"})
    endpoint = f"{base_url}/rest/v1/{TABLE}?{query}"
    req = request.Request(endpoint, headers=_headers(api_key), method="GET")

    try:
        with request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            rows = json.loads(response.read().decode("utf-8"))
        if not rows:
            return True, None, None
        return True, rows[0].get("payload"), None
    except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        return False, None, f"Supabase read failed: {exc}"


def save_payload(state_key: str, payload: Any) -> tuple[bool, Optional[str]]:
    base_url, api_key = _credentials()
    if not base_url or not api_key:
        return False, "Supabase secrets are missing."

    endpoint = f"{base_url}/rest/v1/{TABLE}?on_conflict=key"
    body = json.dumps({"key": state_key, "payload": payload}, default=str).encode("utf-8")
    req = request.Request(
        endpoint,
        data=body,
        headers=_headers(api_key, "resolution=merge-duplicates,return=minimal"),
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=TIMEOUT_SECONDS):
            pass
        return True, None
    except (error.URLError, error.HTTPError, TimeoutError) as exc:
        return False, f"Supabase write failed: {exc}"


def connection_status() -> tuple[bool, str]:
    if not is_configured():
        return False, "Supabase secrets missing"
    reachable, _, message = load_payload("__connection_test__")
    return (True, "Supabase connected") if reachable else (False, message or "Supabase unavailable")
