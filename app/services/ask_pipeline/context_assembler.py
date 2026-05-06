from app.services.ask_pipeline.state import AskState


async def context_assembler(state: AskState) -> dict:
    parts: list[str] = []

    today = state.get("today_str") or ""
    if today:
        parts.append(f"Today is {today}.")

    recent = state.get("recent_summaries") or []
    if recent:
        parts.append("\n# Recent journal activity")
        for s in recent:
            title = (s.get("title") or "Untitled").strip()
            summary = (s.get("summary") or "").strip()
            parts.append(f"- {s['date']}: \"{title}\" — {summary}")

    temporal = state.get("temporal_entries") or []
    if temporal:
        parts.append("\n# Journal entries from the requested time period")
        for e in temporal:
            title = (e.get("title") or "Untitled").strip()
            text = (e.get("raw_text") or e.get("summary") or "").strip()
            parts.append(f"Entry ({e['date']}, title: {title}):\n{text}\n---")

    rag = state.get("rag_entries") or []
    if rag:
        parts.append("\n# Retrieved journal entries (relevance-tagged)")
        for e in rag:
            relevance = e.get("relevance") or "unknown"
            text = (e.get("raw_text") or "").strip()
            parts.append(f"Entry ({e['date']}, relevance: {relevance}):\n{text}\n---")

    dashboard = state.get("dashboard_context") or {}
    projects = dashboard.get("projects") or []
    deadlines = dashboard.get("deadlines") or []
    if projects or deadlines:
        parts.append("\n# Current dashboard context")
        parts.append(
            f"Active projects: {', '.join(projects) if projects else '(none)'}"
        )
        parts.append(
            f"Upcoming deadlines: {', '.join(deadlines) if deadlines else '(none)'}"
        )

    return {"assembled_context": "\n".join(parts).strip()}
