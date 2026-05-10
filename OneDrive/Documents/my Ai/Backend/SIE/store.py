"""SQLite relational store for SIE (separate from personal chat memory)."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from Backend.SIE.paths import SIE_DATA_DIR, SIE_DB_PATH


def _connect() -> sqlite3.Connection:
    SIE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SIE_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS societies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            aliases_json TEXT DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS wings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            society_id INTEGER NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
            code TEXT NOT NULL,
            display_name TEXT,
            UNIQUE(society_id, code)
        );

        CREATE TABLE IF NOT EXISTS flats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            society_id INTEGER NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
            wing_id INTEGER REFERENCES wings(id) ON DELETE SET NULL,
            unit_label TEXT NOT NULL,
            normalized_label TEXT NOT NULL,
            notes TEXT,
            UNIQUE(society_id, normalized_label)
        );

        CREATE TABLE IF NOT EXISTS persons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            display_name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS flat_person (
            flat_id INTEGER NOT NULL REFERENCES flats(id) ON DELETE CASCADE,
            person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            valid_from TEXT,
            valid_to TEXT,
            PRIMARY KEY (flat_id, person_id, role)
        );

        CREATE TABLE IF NOT EXISTS maintenance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flat_id INTEGER NOT NULL REFERENCES flats(id) ON DELETE CASCADE,
            bill_month TEXT NOT NULL,
            amount_due REAL,
            amount_paid REAL DEFAULT 0,
            status TEXT,
            due_date TEXT,
            notes TEXT,
            UNIQUE(flat_id, bill_month)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            society_id INTEGER NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
            flat_id INTEGER REFERENCES flats(id) ON DELETE SET NULL,
            amount REAL NOT NULL,
            paid_at TEXT,
            method TEXT,
            utr TEXT,
            cheque_no TEXT,
            bank_ref TEXT,
            notes TEXT,
            dedupe_key TEXT UNIQUE,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            society_id INTEGER REFERENCES societies(id) ON DELETE SET NULL,
            source_path TEXT,
            title TEXT,
            doc_type TEXT,
            body_text TEXT,
            ingested_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT NOT NULL DEFAULT 'local_user',
            action TEXT NOT NULL,
            detail TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_flats_society ON flats(society_id);
        CREATE INDEX IF NOT EXISTS idx_payments_flat ON payments(flat_id);
        CREATE INDEX IF NOT EXISTS idx_payments_utr ON payments(utr);
        CREATE INDEX IF NOT EXISTS idx_docs_society ON documents(society_id);
        """
    )


def ensure_db() -> None:
    with get_connection() as conn:
        init_schema(conn)


def normalize_flat_label(unit: str) -> str:
    s = unit.strip().upper()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"^([A-Z])[- ]?(\d+)$", r"\1-\2", s)
    return s


@dataclass
class SearchContext:
    society_ids: list[int]
    society_names: list[str]
    flat_label: str | None
    wing_hint: str | None


def list_societies(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT id, name, aliases_json FROM societies ORDER BY name"))


def find_society_ids_by_name(conn: sqlite3.Connection, text: str) -> list[int]:
    t = text.strip().lower()
    if not t:
        return []
    rows = list_societies(conn)
    out: list[int] = []
    for r in rows:
        name = (r["name"] or "").lower()
        if len(name) >= 3 and name in t:
            out.append(int(r["id"]))
            continue
        try:
            aliases = json.loads(r["aliases_json"] or "[]")
        except json.JSONDecodeError:
            aliases = []
        for a in aliases:
            al = str(a).lower()
            if len(al) >= 2 and al in t:
                out.append(int(r["id"]))
                break
    return list(dict.fromkeys(out))


def person_ids_mentioned_in_query(conn: sqlite3.Connection, query_lower: str) -> list[int]:
    rows = conn.execute("SELECT id, display_name FROM persons").fetchall()
    found: list[int] = []
    for r in rows:
        name = (r["display_name"] or "").strip().lower()
        if len(name) < 3:
            continue
        if name in query_lower:
            found.append(int(r["id"]))
    return found


def persons_for_flat(conn: sqlite3.Connection, flat_id: int) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT p.display_name, fp.role, p.phone
            FROM flat_person fp
            JOIN persons p ON p.id = fp.person_id
            WHERE fp.flat_id = ?
            ORDER BY fp.role, p.display_name
            """,
            (flat_id,),
        )
    )


def flats_for_person(conn: sqlite3.Connection, person_id: int) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT f.id, f.unit_label, f.normalized_label, s.name AS society_name, w.code AS wing_code
            FROM flat_person fp
            JOIN flats f ON f.id = fp.flat_id
            JOIN societies s ON s.id = f.society_id
            LEFT JOIN wings w ON w.id = f.wing_id
            WHERE fp.person_id = ?
            """,
            (person_id,),
        )
    )


def search_flats(
    conn: sqlite3.Connection,
    society_ids: list[int] | None,
    normalized_label: str | None,
    wing_code: str | None,
) -> list[sqlite3.Row]:
    q = """
        SELECT f.id, f.unit_label, f.normalized_label, s.name AS society_name, w.code AS wing_code
        FROM flats f
        JOIN societies s ON s.id = f.society_id
        LEFT JOIN wings w ON w.id = f.wing_id
        WHERE 1=1
    """
    params: list[Any] = []
    if society_ids:
        q += f" AND f.society_id IN ({','.join('?' * len(society_ids))})"
        params.extend(society_ids)
    if normalized_label:
        q += " AND f.normalized_label = ?"
        params.append(normalized_label)
    if wing_code:
        q += " AND w.code = ?"
        params.append(wing_code.upper())
    q += " ORDER BY s.name, f.normalized_label"
    return list(conn.execute(q, params))


def pending_maintenance(
    conn: sqlite3.Connection,
    society_ids: list[int] | None,
    flat_ids: list[int] | None,
) -> list[sqlite3.Row]:
    q = """
        SELECT m.bill_month, m.amount_due, m.amount_paid, m.status, m.due_date,
               f.unit_label, f.normalized_label, s.name AS society_name
        FROM maintenance_records m
        JOIN flats f ON f.id = m.flat_id
        JOIN societies s ON s.id = f.society_id
        WHERE (
            (m.status IS NULL OR lower(m.status) IN ('pending','unpaid','due','overdue'))
            OR (m.amount_due IS NOT NULL AND m.amount_paid IS NOT NULL AND m.amount_paid < m.amount_due)
        )
    """
    params: list[Any] = []
    if society_ids:
        q += f" AND f.society_id IN ({','.join('?' * len(society_ids))})"
        params.extend(society_ids)
    if flat_ids:
        q += f" AND m.flat_id IN ({','.join('?' * len(flat_ids))})"
        params.extend(flat_ids)
    q += " ORDER BY s.name, f.normalized_label, m.bill_month"
    return list(conn.execute(q, params))


def recent_payments(
    conn: sqlite3.Connection,
    society_ids: list[int] | None,
    flat_ids: list[int] | None,
    limit: int = 20,
) -> list[sqlite3.Row]:
    q = """
        SELECT p.amount, p.paid_at, p.method, p.utr, p.cheque_no, f.unit_label, s.name AS society_name
        FROM payments p
        LEFT JOIN flats f ON f.id = p.flat_id
        JOIN societies s ON s.id = p.society_id
        WHERE 1=1
    """
    params: list[Any] = []
    if society_ids:
        q += f" AND p.society_id IN ({','.join('?' * len(society_ids))})"
        params.extend(society_ids)
    if flat_ids:
        q += f" AND p.flat_id IN ({','.join('?' * len(flat_ids))})"
        params.extend(flat_ids)
    q += " ORDER BY datetime(COALESCE(p.paid_at, p.created_at)) DESC LIMIT ?"
    params.append(limit)
    return list(conn.execute(q, params))


def duplicate_payments_by_utr(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT utr, COUNT(*) AS c, GROUP_CONCAT(id) AS ids
            FROM payments
            WHERE utr IS NOT NULL AND trim(utr) != ''
            GROUP BY utr
            HAVING c > 1
            """
        )
    )


def search_documents(conn: sqlite3.Connection, society_ids: list[int] | None, needle: str) -> list[sqlite3.Row]:
    like = f"%{needle}%"
    if society_ids:
        q = f"""
            SELECT id, title, doc_type, substr(body_text, 1, 400) AS snippet, society_id
            FROM documents
            WHERE body_text LIKE ? AND (society_id IN ({','.join('?' * len(society_ids))}) OR society_id IS NULL)
            LIMIT 15
        """
        return list(conn.execute(q, (like, *society_ids)))
    return list(
        conn.execute(
            """
            SELECT id, title, doc_type, substr(body_text, 1, 400) AS snippet, society_id
            FROM documents
            WHERE body_text LIKE ?
            LIMIT 15
            """,
            (like,),
        )
    )


def audit(conn: sqlite3.Connection, action: str, detail: str = "") -> None:
    conn.execute(
        "INSERT INTO audit_log (actor, action, detail) VALUES ('local_user', ?, ?)",
        (action, detail[:2000]),
    )


def _to_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _payment_dedupe_key(society_id: int, flat_id: int | None, utr: str | None, cheque: str | None, amount: float, paid_at: str | None) -> str:
    raw = "|".join(
        str(x)
        for x in (society_id, flat_id or "", (utr or "").strip(), (cheque or "").strip(), amount, paid_at or "")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:48]


def import_record_bundle(conn: sqlite3.Connection, records: list[dict[str, Any]]) -> tuple[int, int]:
    """Import list of dicts with keys: society, wing, flat, owner, tenant, phone, maintenance rows, etc."""
    flats_touched: set[int] = set()
    pay_n = 0
    for rec in records:
        soc_name = str(rec.get("society") or rec.get("society_name") or "").strip()
        if not soc_name:
            continue
        existing = conn.execute("SELECT id, aliases_json FROM societies WHERE name = ?", (soc_name,)).fetchone()
        aliases = rec.get("aliases")
        if existing:
            sid = int(existing["id"])
            if aliases is not None:
                conn.execute(
                    "UPDATE societies SET aliases_json = ? WHERE id = ?",
                    (json.dumps(aliases), sid),
                )
        else:
            conn.execute(
                "INSERT INTO societies (name, aliases_json) VALUES (?, ?)",
                (soc_name, json.dumps(aliases or [])),
            )
            sid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

        wing_code = str(rec.get("wing") or rec.get("wing_code") or "").strip().upper() or None
        wing_id = None
        if wing_code:
            conn.execute(
                "INSERT OR IGNORE INTO wings (society_id, code, display_name) VALUES (?, ?, ?)",
                (sid, wing_code, rec.get("wing_name")),
            )
            w = conn.execute(
                "SELECT id FROM wings WHERE society_id = ? AND code = ?",
                (sid, wing_code),
            ).fetchone()
            wing_id = int(w["id"]) if w else None

        unit = str(rec.get("flat") or rec.get("unit") or rec.get("unit_label") or "").strip()
        if not unit:
            continue
        norm = normalize_flat_label(unit)
        conn.execute(
            """
            INSERT OR IGNORE INTO flats (society_id, wing_id, unit_label, normalized_label, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sid, wing_id, unit, norm, rec.get("flat_notes")),
        )
        f = conn.execute(
            "SELECT id FROM flats WHERE society_id = ? AND normalized_label = ?",
            (sid, norm),
        ).fetchone()
        if not f:
            continue
        fid = int(f["id"])
        flats_touched.add(fid)

        def upsert_person(name: str | None, role: str, phone: str | None = None) -> None:
            if not name or not str(name).strip():
                return
            conn.execute(
                "INSERT OR IGNORE INTO persons (display_name, phone) VALUES (?, ?)",
                (str(name).strip(), phone),
            )
            p = conn.execute(
                "SELECT id FROM persons WHERE display_name = ?",
                (str(name).strip(),),
            ).fetchone()
            if not p:
                return
            pid = int(p["id"])
            conn.execute(
                """
                INSERT OR REPLACE INTO flat_person (flat_id, person_id, role, valid_from, valid_to)
                VALUES (?, ?, ?, ?, ?)
                """,
                (fid, pid, role, rec.get("valid_from"), rec.get("valid_to")),
            )

        upsert_person(rec.get("owner"), "owner", rec.get("owner_phone"))
        upsert_person(rec.get("tenant"), "tenant", rec.get("tenant_phone"))

        if rec.get("bill_month"):
            due = _to_float(rec.get("amount_due"))
            paid_m = _to_float(rec.get("amount_paid"))
            conn.execute(
                """
                INSERT OR REPLACE INTO maintenance_records
                (flat_id, bill_month, amount_due, amount_paid, status, due_date, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fid,
                    str(rec["bill_month"]),
                    due,
                    paid_m if paid_m is not None else 0,
                    rec.get("status"),
                    rec.get("due_date"),
                    rec.get("maintenance_notes"),
                ),
            )

        pay_amt = _to_float(rec.get("payment_amount"))
        if pay_amt is not None:
            utr = rec.get("utr") or rec.get("UTR")
            chq = rec.get("cheque_no") or rec.get("cheque")
            amt = pay_amt
            paid_at = rec.get("paid_at") or rec.get("payment_date")
            method = rec.get("payment_method") or rec.get("method")
            dedupe = rec.get("dedupe_key") or _payment_dedupe_key(sid, fid, utr, chq, amt, paid_at)
            try:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO payments
                    (society_id, flat_id, amount, paid_at, method, utr, cheque_no, bank_ref, notes, dedupe_key)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sid,
                        fid,
                        amt,
                        paid_at,
                        method,
                        utr,
                        chq,
                        rec.get("bank_ref"),
                        rec.get("payment_notes"),
                        dedupe,
                    ),
                )
                if cur.rowcount and cur.rowcount > 0:
                    pay_n += 1
            except sqlite3.IntegrityError:
                pass

    return len(flats_touched), pay_n


def insert_document(
    conn: sqlite3.Connection,
    society_id: int | None,
    source_path: str | None,
    title: str | None,
    doc_type: str | None,
    body_text: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO documents (society_id, source_path, title, doc_type, body_text)
        VALUES (?, ?, ?, ?, ?)
        """,
        (society_id, source_path, title, doc_type, body_text),
    )
    return int(cur.lastrowid)


def stats_line(conn: sqlite3.Connection) -> str:
    c1 = conn.execute("SELECT COUNT(*) FROM societies").fetchone()[0]
    c2 = conn.execute("SELECT COUNT(*) FROM flats").fetchone()[0]
    c3 = conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
    c4 = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    return f"societies={c1}, flats={c2}, payments={c3}, documents={c4}"
