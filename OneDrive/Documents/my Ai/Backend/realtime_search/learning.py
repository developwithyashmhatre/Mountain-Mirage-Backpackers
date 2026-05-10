from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def bump_topic_stats(path: Path, topics: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        doc = {"version": 1, "counts": {}, "last_updated": None}
    counts: dict[str, int] = doc.get("counts", {})
    for t in topics:
        counts[t] = int(counts.get(t, 0)) + 1
    doc["counts"] = counts
    doc["last_updated"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
