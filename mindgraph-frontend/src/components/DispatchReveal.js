import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { API, authHeaders } from "../utils/auth";
import "../styles/dispatch.css";

const PHRASES_GENERIC = [
  "reading what you wrote",
  "noticing some things",
  "putting it together",
  "thinking it through",
  "looking for the thread",
  "wait, this rings a bell",
];

const PHRASES_CREATIVE = [
  "untangling your morning",
  "matching today's words to last month's promises",
  "scrolling through an earlier you",
  "tracing a thread back",
  "looking for echoes",
  "rummaging through your notes",
  "humming and squinting at the page",
  "comparing this week to last",
];

const PHRASES_SARCASTIC = [
  "pretending to read carefully",
  "putting on reading glasses",
  "looking up what 'soon' means again",
  "asking your past self what they meant",
  "filing this under 'feelings'",
  "checking if 'busy' is a personality",
];

const PHRASES_USER = [
  "checking what {name} usually circles back to",
  "remembering what {name} said last time",
  "comparing this {name} to yesterday's {name}",
  "looking at {name}'s last few weeks",
];

function buildPhrasePool(firstName) {
  const safeName = (firstName || "you").trim() || "you";
  const userPool = PHRASES_USER.map((p) => p.replace(/\{name\}/g, safeName));
  const all = [
    ...PHRASES_GENERIC,
    ...PHRASES_CREATIVE,
    ...PHRASES_SARCASTIC,
    ...userPool,
  ];
  for (let i = all.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [all[i], all[j]] = [all[j], all[i]];
  }
  return [...all, "almost there."];
}

const PHRASE_CYCLE_MS = 2800; // synced with 3s pulse-orb breath

function fmtTime(d) {
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

function numberize(text) {
  return text.replace(/\b(\d+(?:st|nd|rd|th)?)\b/g, (m) => (
    `<span class="dispatch-number">${m}</span>`
  ));
}

// Stamp component with inline edit affordance
function Stamp({ stamp, entryId, onSaved, style }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(stamp.value || "");
  const [saved, setSaved] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    if (editing && inputRef.current) inputRef.current.focus();
  }, [editing]);

  const isFirst = stamp.is_first_mention;
  let kindClass = `dispatch-stamp--${stamp.kind}`;
  if (isFirst) kindClass = "dispatch-stamp--firstmention";

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
      setTimeout(() => setSaved(false), 800);
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
      className={`dispatch-stamp ${kindClass} ${saved ? "dispatch-stamp--saved" : ""}`}
      style={style}
      onClick={() => !editing && setEditing(true)}
      title="Click to correct"
    >
      {stamp.label}:&nbsp;
      {editing ? (
        <input
          ref={inputRef}
          className="dispatch-stamp-input"
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={handleKey}
          onBlur={handleSave}
          style={{ width: Math.max(40, val.length * 7) + "px" }}
        />
      ) : (
        <span>{val}{isFirst ? " ★" : ""}</span>
      )}
    </span>
  );
}

// Phase: "processing" | "revealing" | "done"
export default function DispatchReveal({ dispatch, entryId, phase, firstName }) {
  const [statusIdx, setStatusIdx] = useState(0);
  const [stamps, setStamps] = useState([]);

  // Build a fresh shuffled phrase pool each time we enter processing
  const phrasePool = useMemo(
    () => (phase === "processing" ? buildPhrasePool(firstName) : []),
    [phase, firstName]
  );

  // Reset cycle position when a new processing run starts
  useEffect(() => {
    if (phase === "processing") {
      setStatusIdx(0);
      setStamps([]);
    }
  }, [phase]);

  // Phrases breathe with the pulse-orb: one phrase per 2.8s cycle
  useEffect(() => {
    if (phase !== "processing" || phrasePool.length === 0) return;
    const id = setInterval(() => {
      setStatusIdx((i) => Math.min(i + 1, phrasePool.length - 1));
    }, PHRASE_CYCLE_MS);
    return () => clearInterval(id);
  }, [phase, phrasePool]);

  // Snapshot stamps from dispatch when we enter the revealing phase
  useEffect(() => {
    if (phase === "revealing" && dispatch) {
      setStamps(dispatch.stamps || []);
    }
  }, [phase, dispatch]);

  const handleStampSaved = useCallback((kind, oldVal, newVal) => {
    setStamps((prev) =>
      prev.map((s) =>
        s.kind === kind && s.value === oldVal ? { ...s, value: newVal } : s
      )
    );
  }, []);

  if (phase === "idle") return null;

  const discoveries = (dispatch?.discoveries) || [];

  return (
    <div className="dispatch-wrap" style={{ marginBottom: 32 }}>
      {/* Pulse-orb thinking indicator: warm glow that breathes */}
      <div className="dispatch-wire-wrap">
        <div className="dispatch-pulse">
          <span className="dispatch-pulse-ring  dispatch-pulse-ring--1" />
          <span className="dispatch-pulse-ring  dispatch-pulse-ring--2" />
          <span className="dispatch-pulse-glow" />
          <span className="dispatch-pulse-core" />
        </div>
        <div className="dispatch-status-text-wrap">
          <AnimatePresence mode="wait">
            <motion.div
              key={statusIdx}
              className="dispatch-status-text"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.55, ease: [0.4, 0, 0.2, 1] }}
            >
              {phrasePool[statusIdx] || ""}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>

      {/* Telegram envelope - drops in when pipeline returns */}
      <AnimatePresence>
        {phase === "revealing" && dispatch && (
          <motion.div
            className="dispatch-telegram"
            initial={{ y: 24, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5, ease: [0.2, 0.85, 0.3, 1] }}
          >
            <span className="dispatch-postmark">
              <span className="dispatch-postmark-line">
                RAWTXT &middot; ENTRY {String(entryId || "").slice(-6).toUpperCase()}
              </span>
              <span className="dispatch-postmark-line">{fmtTime(new Date())}</span>
            </span>

            <div className="dispatch-header">
              <span className="dispatch-header-from">FROM YOUR JOURNAL &middot; TO YOU</span>
            </div>

            {/* All content reveals together in a single coordinated fade-up */}
            <div className="dispatch-content">
              <div className="dispatch-subject">
                RE: {dispatch.subject || "untitled"}
              </div>

              {discoveries.length > 0 && (
                <div className="dispatch-body">
                  {discoveries.map((d, i) => (
                    <span
                      key={i}
                      className="dispatch-discovery-line"
                      dangerouslySetInnerHTML={{ __html: numberize(d.phrase || "") }}
                    />
                  ))}
                </div>
              )}

              <span className="dispatch-signature">
                -- your journal
              </span>

              {stamps.length > 0 && (
                <div className="dispatch-stamps-row" style={{ marginTop: 20 }}>
                  {stamps.map((stamp, i) => (
                    <Stamp
                      key={`${stamp.kind}-${stamp.value}-${i}`}
                      stamp={stamp}
                      entryId={entryId}
                      onSaved={handleStampSaved}
                    />
                  ))}
                </div>
              )}

              <div className="dispatch-footer-hint visible">
                tap any stamp to correct it &middot; we learn from every mark you make
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
