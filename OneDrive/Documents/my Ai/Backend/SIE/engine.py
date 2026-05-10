"""Society Intelligence Engine — retrieval and commands; never touches Chatbot memory."""

from __future__ import annotations

from pathlib import Path

from Backend.SIE import ingest, store, trigger
from Backend.SIE.paths import SIE_DB_PATH


def _help_text() -> str:
    return "\n".join(
        [
            "Society Intelligence Engine (SIE) - isolated from personal chat memory.",
            "Commands:",
            "  sie help",
            "  sie stats",
            "  sie import json <path-to.json>   - rows with society/society_name + flat fields",
            "  sie import excel <path.xlsx>     - structured import (legacy; uses first sheet)",
            "  sie scan <folder>                - recursive scan; indexes txt/md/json/csv/xlsx(doc all sheets)/docx/pdf/images(ocr)",
            "                                     - if <folder> contains multiple society folders, each top folder becomes a society bucket",
            "  sie seed sample                  - load demo Crown / Pices data (if empty)",
            "",
            "Natural language (only when SIE triggers): ask about pending maintenance, flats, owners, payments.",
        ]
    )


def _cmd_stats() -> str:
    store.ensure_db()
    with store.get_connection() as conn:
        line = store.stats_line(conn)
        dups = store.duplicate_payments_by_utr(conn)
    extra = f" Duplicate UTR rows: {len(dups)}." if dups else ""
    return f"SIE database ({SIE_DB_PATH}): {line}.{extra}"


def _cmd_import_json(path_str: str) -> str:
    p = Path(path_str.strip().strip('"'))
    if not p.is_file():
        return f"File not found: {p}"
    recs = ingest.load_json_records(p)
    if not recs:
        return "No records in JSON."
    store.ensure_db()
    with store.get_connection() as conn:
        f, pay = store.import_record_bundle(conn, recs)
        store.audit(conn, "import_json", str(p))
    return f"Imported: {len(recs)} rows -> {f} flats touched, {pay} new payments."


def _cmd_import_excel(path_str: str) -> str:
    p = Path(path_str.strip().strip('"'))
    if not p.is_file():
        return f"File not found: {p}"
    if p.suffix.lower() not in {".xlsx", ".xlsm"}:
        return "Excel import expects .xlsx or .xlsm (legacy .xls is not supported)."
    try:
        recs = ingest.load_xlsx_records(p)
    except RuntimeError as e:
        return str(e)
    if not recs:
        return "No rows found in the spreadsheet."
    store.ensure_db()
    is_society_batch = all(
        isinstance(r, dict) and ("society" in r or "society_name" in r) for r in recs
    )
    if not is_society_batch:
        return (
            "Each row must include a 'society' or 'society_name' column for structured import. "
            "Use sie scan <folder> to index generic spreadsheets as searchable text."
        )
    with store.get_connection() as conn:
        f, pay = store.import_record_bundle(conn, recs)
        store.audit(conn, "import_excel", str(p))
    return f"Imported: {len(recs)} rows -> {f} flats touched, {pay} new payments."


def _cmd_scan(path_str: str) -> str:
    p = Path(path_str.strip().strip('"'))
    store.ensure_db()
    return ingest.scan_folder(p, society_id=None, import_rows=True)


def _cmd_seed_sample() -> str:
    store.ensure_db()
    sample = Path(__file__).resolve().parent.parent.parent / "Data" / "SIE" / "sample_societies.json"
    if not sample.is_file():
        return f"Sample file missing: {sample}"
    with store.get_connection() as conn:
        n_soc = conn.execute("SELECT COUNT(*) FROM societies").fetchone()[0]
        if int(n_soc) > 0:
            return "Societies already exist; skip seed. Use sie import json with your data."
    return _cmd_import_json(str(sample))


def _handle_command(arg: str) -> str:
    low = arg.lower().strip()
    if not low or low == "help":
        return _help_text()
    if low == "stats":
        return _cmd_stats()
    if low == "seed sample" or low == "seed":
        return _cmd_seed_sample()
    if low.startswith("import json "):
        return _cmd_import_json(arg[12:].strip())
    if low.startswith("import excel "):
        return _cmd_import_excel(arg[13:].strip())
    if low.startswith("scan "):
        return _cmd_scan(arg[5:].strip())
    return _help_text()


def _resolve_scope(conn, query: str) -> tuple[list[int] | None, str | None, str | None]:
    """Returns (society_ids filter or None for all), normalized flat label, wing code."""
    low = query.lower()
    society_ids = store.find_society_ids_by_name(conn, low)
    sid_list = society_ids if society_ids else None
    flat = trigger.extract_flat_hint(query)
    norm = store.normalize_flat_label(flat) if flat else None
    wing = trigger.extract_wing_hint(query)
    if wing and norm is None:
        pass
    return sid_list, norm, wing


def _answer_natural(conn, query: str) -> str:
    low = query.lower()
    society_ids, flat_norm, wing_code = _resolve_scope(conn, query)

    lines: list[str] = []

    if any(k in low for k in ("duplicate", "duplicates", "double payment")):
        dups = store.duplicate_payments_by_utr(conn)
        if not dups:
            lines.append("No duplicate UTR payments detected.")
        else:
            lines.append("Possible duplicate payments (same UTR):")
            for r in dups[:10]:
                lines.append(f"  UTR {r['utr']}: count={r['c']}, payment_ids={r['ids']}")

    person_ids = store.person_ids_mentioned_in_query(conn, low)
    if person_ids and not flat_norm:
        for pid in person_ids[:5]:
            flats = store.flats_for_person(conn, pid)
            pname = conn.execute("SELECT display_name FROM persons WHERE id = ?", (pid,)).fetchone()
            label = pname["display_name"] if pname else f"id {pid}"
            if not flats:
                lines.append(f"{label}: no linked flats in SIE.")
            else:
                lines.append(f"{label}:")
                for f in flats:
                    lines.append(
                        f"  - {f['unit_label']} ({f['normalized_label']}) @ {f['society_name']} wing {f['wing_code'] or '-'}"
                    )

    flat_rows: list = []
    if flat_norm:
        flat_rows = store.search_flats(conn, society_ids, flat_norm, wing_code)
    elif society_ids and wing_code:
        flat_rows = store.search_flats(conn, society_ids, None, wing_code)

    if flat_rows and ("owner" in low or "tenant" in low or "who" in low):
        for f in flat_rows[:8]:
            people = store.persons_for_flat(conn, int(f["id"]))
            lines.append(
                f"{f['society_name']} {f['unit_label']}: "
                + (
                    ", ".join(f"{p['display_name']} ({p['role']})" for p in people)
                    if people
                    else "no owner/tenant on file"
                )
            )

    if any(k in low for k in ("pending", "unpaid", "due", "overdue", "maintenance")):
        flat_ids = [int(f["id"]) for f in flat_rows] if flat_rows else None
        pend = store.pending_maintenance(conn, society_ids, flat_ids)
        if pend:
            lines.append("Maintenance (pending / underpaid):")
            for r in pend[:25]:
                due = r["amount_due"] or 0
                paid = r["amount_paid"] or 0
                lines.append(
                    f"  {r['society_name']} {r['unit_label']} {r['bill_month']}: due={due}, paid={paid}, status={r['status']}"
                )
        elif not lines:
            lines.append("No pending maintenance rows matched your filters.")

    if any(k in low for k in ("payment", "paid", "utr", "cheque", "check")):
        flat_ids = [int(f["id"]) for f in flat_rows] if flat_rows else None
        pays = store.recent_payments(conn, society_ids, flat_ids, limit=15)
        if pays:
            lines.append("Recent payments:")
            for r in pays:
                lines.append(
                    f"  {r['society_name']} {r['unit_label']}: {r['amount']} on {r['paid_at']} "
                    f"via {r['method']} UTR={r['utr'] or '-'} Chq={r['cheque_no'] or '-'}"
                )

    if flat_rows and not any(
        k in low for k in ("pending", "unpaid", "owner", "tenant", "payment", "paid", "duplicate")
    ):
        lines.append("Matching flats:")
        for f in flat_rows[:15]:
            lines.append(
                f"  {f['society_name']} wing {f['wing_code'] or '-'} {f['unit_label']} ({f['normalized_label']})"
            )

    if not lines:
        needle = query.strip()
        if len(needle) > 80:
            needle = needle[:80]
        docs = store.search_documents(conn, society_ids, needle)
        if docs:
            lines.append("Document snippets (keyword match):")
            for d in docs[:8]:
                snippet = (d["snippet"] or "").replace("\n", " ")
                lines.append(f"  [{d['doc_type']}] {d['title']}: {snippet[:200]}...")
        else:
            lines.append(
                "No structured matches. Try: name a society from your data, a flat like A-101, "
                "or run `sie import json` / `sie scan` to load records."
            )

    return "\n".join(lines)


def try_society_intelligence(query: str) -> str | None:
    """
    If SIE activates, return a response string (caller prints it).
    If SIE should stay off, return None so normal routing runs.
    """
    q = query.strip()
    if not q:
        return None

    store.ensure_db()
    with store.get_connection() as conn:
        if not trigger.should_activate_sie(q, conn):
            return None
        low = q.lower()
        if low.startswith("sie "):
            arg = q.split(" ", 1)[1].strip() if " " in q else ""
            return _handle_command(arg)
        store.audit(conn, "sie_query", q[:500])
        return _answer_natural(conn, q)
