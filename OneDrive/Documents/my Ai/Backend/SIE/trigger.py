"""
Strict SIE activation: only when society anchors are present.
Does not call LLMs — avoids leaking society context into normal chat routing.
"""

from __future__ import annotations

import json
import re
import sqlite3

from Backend.SIE.store import (
    ensure_db,
    get_connection,
    list_societies,
    person_ids_mentioned_in_query,
)

# Strong domain signals (must pair with an anchor unless `sie ` command)
SOCIETY_DOMAIN_TERMS = frozenset(
    """
    maintenance sinking fund corpus chs housing society apartment complex
    wing flat owner tenant unpaid pending overdue mcm society committee
    utr cheque payment dues bill invoice notice penalty parking meter water
    repair amenity clubhouse agm minutes resolution
    """.split()
)

# Flat-like patterns (housing societies): A-101, D 102, B wing 303
FLAT_PATTERNS = [
    re.compile(r"\b([a-z])[-\s]?wing[-\s]?(\d{2,4})\b", re.I),
    re.compile(r"\b([A-Z])[-\s](\d{2,4})\b"),
    re.compile(r"\bflat\s*([A-Z])[-\s]?(\d{2,4})\b", re.I),
]


def extract_flat_hint(text: str) -> str | None:
    for pat in FLAT_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        if len(m.groups()) == 2:
            a, b = m.group(1).upper(), m.group(2)
            if len(a) == 1 and a.isalpha():
                return f"{a}-{b}"
    return None


def extract_wing_hint(text: str) -> str | None:
    m = re.search(r"\b([A-Z])\s*wing\b", text, re.I)
    if m:
        return m.group(1).upper()
    return None


def _tokens_lower(text: str) -> set[str]:
    return {t.strip(".,?!\"'()[]") for t in text.lower().split() if t}


def mentions_domain_term(text_lower: str) -> bool:
    toks = _tokens_lower(text_lower)
    for term in SOCIETY_DOMAIN_TERMS:
        if term in text_lower or term in toks:
            return True
    return False


def should_activate_sie(query: str, conn: sqlite3.Connection | None) -> bool:
    """
    Activate only if:
    - explicit `sie ...` command, OR
    - registered society / alias appears in query, OR
    - known person (from DB) full name appears, OR
    - (flat pattern AND domain term), OR
    - (flat pattern AND society name in same query from registry)
    """
    raw = query.strip()
    if not raw:
        return False
    low = raw.lower()
    if low.startswith("sie "):
        return True

    if conn is None:
        ensure_db()
        with get_connection() as c:
            return should_activate_sie(query, c)

    flat_hint = extract_flat_hint(raw)
    wing_hint = extract_wing_hint(raw)

    soc_ids = []
    for row in list_societies(conn):
        name = (row["name"] or "").strip().lower()
        if name and len(name) >= 3 and name in low:
            soc_ids.append(int(row["id"]))
            continue
        try:
            aliases = json.loads(row["aliases_json"] or "[]")
        except Exception:
            aliases = []
        for a in aliases:
            al = str(a).strip().lower()
            if al and len(al) >= 2 and al in low:
                soc_ids.append(int(row["id"]))
                break

    person_hits = person_ids_mentioned_in_query(conn, low)
    if person_hits:
        return True

    if soc_ids:
        return True

    if flat_hint and mentions_domain_term(low):
        return True

    # Wing + number style already covered by flat_hint often; wing + domain
    if wing_hint and mentions_domain_term(low):
        return True

    return False
