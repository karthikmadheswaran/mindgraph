import { useCallback, useRef, useState } from "react";
import { API, authHeaders } from "../utils/auth";
import "../styles/entries.css";

function fmtEntryDate(str) {
  const d = new Date(str);
  const date = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
  return `${date} · ${time}`;
}

// Chip with inline edit (same edit flow as stamps in DispatchReveal)
function EntryChip({ stamp, entryId, onSaved }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(stamp.value || "");
  const [saved, setSaved] = useState(false);
  const inputRef = useRef(null);

  const isFirst = stamp.is_first_mention;
  let kindClass = `entry-chip--${stamp.kind}`;
  if (isFirst) kindClass = "entry-chip--firstmention";

  const handleSave = useCallback(async () => {
    if (val === stamp.value) { setEditing(false); return; }
    try {
      const headers = await authHeaders();
      await fetch(`${API}/entries/${entryId}/edits`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          stamp_kind: stamp.kind,
          field_path: `stamps[kind=${stamp.kind}].value`,
          original_value: stamp.value,
          edited_value: val,
          edit_type: "correction",
        }),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 600);
      if (onSaved) onSaved(stamp.kind, stamp.value, val);
    } catch {
      /* silent */
    }
    setEditing(false);
  }, [val, stamp, entryId, onSaved]);

  const handleKey = useCallback((e) => {
    if (e.key === "Enter") handleSave();
    if (e.key === "Escape") { setVal(stamp.value); setEditing(false); }
  }, [handleSave, stamp.value]);

  return (
    <span
      className={`entry-chip ${kindClass} ${saved ? "dispatch-stamp--saved" : ""}`}
      onClick={() => !editing && setEditing(true)}
      title="Click to correct"
      style={{ cursor: "pointer" }}
    >
      {stamp.label}:&nbsp;
      {editing ? (
        <input
          ref={inputRef}
          className="entry-chip-input"
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={handleKey}
          onBlur={handleSave}
          autoFocus
          style={{ width: Math.max(30, val.length * 7) + "px" }}
        />
      ) : (
        <span>{val}{isFirst ? " ★" : ""}</span>
      )}
    </span>
  );
}

function EntrySkeleton() {
  return (
    <div className="entries-skeleton">
      <div className="entries-skeleton-line" style={{ width: "65%" }} />
      <div className="entries-skeleton-line short" />
    </div>
  );
}

// Chevron icon
function Chevron({ open }) {
  return (
    <svg
      className={`entry-card-chevron${open ? " open" : ""}`}
      viewBox="0 0 14 14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    >
      <path d="M 2 4.5 L 7 9.5 L 12 4.5" />
    </svg>
  );
}

function EntryCard({ entry }) {
  const [open, setOpen] = useState(false);
  const [stamps, setStamps] = useState(entry.dispatch_payload?.stamps || []);

  const title =
    entry.auto_title ||
    (entry.raw_text
      ? entry.raw_text.slice(0, 60) + (entry.raw_text.length > 60 ? "…" : "")
      : "Untitled");

  const handleStampSaved = useCallback((kind, oldVal, newVal) => {
    setStamps((prev) =>
      prev.map((s) => (s.kind === kind && s.value === oldVal ? { ...s, value: newVal } : s))
    );
  }, []);

  return (
    <div className="entry-card" onClick={() => setOpen((v) => !v)}>
      <div className="entry-card-head">
        <span className="entry-card-title">{title}</span>
        <span className="entry-card-date">{fmtEntryDate(entry.created_at)}</span>
        <Chevron open={open} />
      </div>

      <div
        className={`entry-card-body${open ? " expanded" : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        {entry.raw_text && (
          <div className="entry-card-text">{entry.raw_text}</div>
        )}
        {stamps.length > 0 && (
          <div className="entry-chips-row">
            {stamps.map((stamp, i) => (
              <EntryChip
                key={`${stamp.kind}-${stamp.value}-${i}`}
                stamp={stamp}
                entryId={entry.id}
                onSaved={handleStampSaved}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function EntriesList({ entries, loading, appended }) {
  if (loading && !appended) {
    return (
      <div className="entries-list">
        {[0, 1, 2, 3].map((i) => <EntrySkeleton key={i} />)}
      </div>
    );
  }

  if (!loading && (!entries || entries.length === 0)) {
    return <p className="entries-empty">Nothing yet. Start writing.</p>;
  }

  return (
    <div className="entries-list">
      {entries.map((entry) => (
        <EntryCard key={entry.id || entry.created_at} entry={entry} />
      ))}
      {loading && appended && <EntrySkeleton />}
    </div>
  );
}
