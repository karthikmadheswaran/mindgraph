"""One-time migration (ADR-0001 Phase 2): parse the frozen Notion changelog page
into structured rows for the MindGraph Changelog DB.

The old changelog page (3449402f2bd281a6afbdfb0397d8f10b) stored history as
nested toggles: day toggle `DD/MM/YYYY` -> item toggles `[Category] title` with
Category / What / Impact body lines. This script parses a Notion-flavored-
markdown export of that page (as returned by the Notion MCP `fetch` tool, JSON
or raw text) and emits one JSON row per item, shaped for the Changelog DB
schema (Title, date:Date:start, Category, What, Impact, Commit, Eval delta).

Run on 2026-06-10 against the 95-entry export; rows were then written to the DB
(data source 829daeda-7303-4f7d-b269-75b23adb53ff) via the Notion MCP in
batches. Kept in the repo as the migration's provenance. Idempotence: the
script only parses; re-running it never writes anywhere.

Usage: python scripts/backfill_changelog_to_notion_db.py <export.json|export.txt> <rows_out.json>
"""

import json
import re
import sys

REPO_COMMIT_URL = "https://github.com/karthikmadheswaran/mindgraph/commit/"

# Normalize historical category spellings to the DB's select options.
CATEGORY_MAP = {
    "Testing": "Tests",
    "Bug open": "Bug",
    "Bug (open)": "Bug",
}
VALID = {"Launch", "Feature", "Pipeline", "Eval", "Infra", "Backend", "Frontend",
         "Tests", "Docs", "Strategy", "Bug", "Bug Fix", "Decision"}

FIELD_RE = re.compile(r"^(Category|What|Impact):\s*(.*)$")
DAY_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
# `commit abc1234` / `commits abc1234, def5678` / (commit `abc1234`)
COMMIT_RE = re.compile(r"commits?\s+`?([0-9a-f]{7,40})\b", re.IGNORECASE)
EVAL_DELTA_RE = re.compile(r"((?:F1|MRR|pass rate|hit rate)[^.;]{0,30}?[\d.]+\s*(?:→|->)\s*[\d.]+)")


def _trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def unescape(s: str) -> str:
    return s.replace("\\[", "[").replace("\\]", "]").replace("\\~", "~").replace("\\*", "*")


def parse(text: str):
    rows, day = [], None
    item = None  # dict being accumulated
    field = None  # current continuation target: 'What' | 'Impact' | None

    def flush():
        nonlocal item, field
        if item and item.get("Title"):
            rows.append(item)
        item, field = None, None

    for raw in text.split("\n"):
        line = raw.strip("\t ").rstrip()
        m = re.match(r"^<summary>(.*)</summary>$", line)
        if m:
            inner = unescape(m.group(1)).strip()
            d = DAY_RE.match(inner)
            if d:  # day toggle
                flush()
                day = f"{d.group(3)}-{d.group(2)}-{d.group(1)}"
            else:  # item toggle
                flush()
                cat = None
                cm = re.match(r"^\[([^\]]+)\]\s*(.*)$", inner)
                title = inner
                if cm:
                    cat = cm.group(1).strip()
                item = {"Title": title[:1900], "Date": day, "Category": cat,
                        "What": "", "Impact": "", "_text": inner}
            continue
        if item is None or not line or line.startswith(("<", ">")):
            continue
        item["_text"] += "\n" + line
        f = FIELD_RE.match(line)
        if f:
            name, val = f.group(1), unescape(f.group(2)).strip()
            if name == "Category":
                item["Category"] = val or item["Category"]
                field = None
            else:
                item[name] = val
                field = name
        elif field:  # continuation of a multi-line What/Impact
            item[field] += " " + unescape(line)
    flush()

    out = []
    for r in rows:
        cat = CATEGORY_MAP.get(r["Category"] or "", r["Category"])
        if cat not in VALID:
            cat = "Feature"  # conservative default; flagged in stderr
            print(f"WARN unmapped category {r['Category']!r}: {r['Title'][:60]}", file=sys.stderr)
        sha = COMMIT_RE.search(r["_text"])
        delta = EVAL_DELTA_RE.search(r["_text"])
        out.append({
            "Title": r["Title"],
            "date:Date:start": r["Date"],
            "Category": cat,
            # Index-level truncation: the frozen source page keeps full prose;
            # DB rows are for scanning/filtering, not archival.
            "What": _trunc(unescape(r["What"]), 600),
            "Impact": _trunc(unescape(r["Impact"]), 400),
            "Commit": REPO_COMMIT_URL + sha.group(1) if sha else None,
            "Eval delta": delta.group(1) if delta else None,
        })
    return out


def main():
    src, dst = sys.argv[1], sys.argv[2]
    text = open(src, encoding="utf-8").read()
    # MCP tool results nest JSON up to twice: [{"text": "{\"text\": \"<page...>\"}"}]
    for _ in range(3):
        stripped = text.lstrip()
        if not stripped.startswith(("[", "{")):
            break
        try:
            d = json.loads(stripped)
        except json.JSONDecodeError:
            break
        if isinstance(d, list):
            d = d[0]
        text = d["text"] if isinstance(d, dict) and "text" in d else json.dumps(d)
    rows = parse(text)
    json.dump(rows, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"parsed {len(rows)} rows -> {dst}")


if __name__ == "__main__":
    main()
