import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { API, authHeaders } from "../utils/auth";
import "../styles/dispatch.css";

const STATUS_PHRASES = [
  "reading what you wrote",
  "wait, this rings a bell...",
  "looking through your past",
  "noticing some things",
  "putting it together",
  "almost there",
  "there.",
];

const CHAR_BASE_MS = 18;
const DISCOVERY_GAP_MS = 1100;

function jitter(base, char) {
  if (char === " ") return base * 0.5;
  if (".,;:!?".includes(char)) return base * 5;
  return base * (0.5 + Math.random());
}

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
export default function DispatchReveal({ dispatch, entryId, phase }) {
  const [statusIdx, setStatusIdx] = useState(0);
  const [subjectTyped, setSubjectTyped] = useState("");
  const [subjectDone, setSubjectDone] = useState(false);
  const [discoveryLines, setDiscoveryLines] = useState([]);
  const [sigVisible, setSigVisible] = useState(false);
  const [stamps, setStamps] = useState([]);
  const [stampsVisible, setStampsVisible] = useState([]);
  const [hintVisible, setHintVisible] = useState(false);

  // Cycle status phrases while processing
  useEffect(() => {
    if (phase !== "processing") return;
    const id = setInterval(() => {
      setStatusIdx((i) => Math.min(i + 1, STATUS_PHRASES.length - 1));
    }, 950);
    return () => clearInterval(id);
  }, [phase]);

  // Type the subject line when revealing starts
  useEffect(() => {
    if (phase !== "revealing" || !dispatch) return;
    const subject = `RE: ${dispatch.subject || "untitled"}`;
    let i = 0;
    let timeout;
    function typeNext() {
      if (i >= subject.length) { setSubjectDone(true); return; }
      const ch = subject[i];
      setSubjectTyped(subject.slice(0, i + 1));
      i++;
      timeout = setTimeout(typeNext, jitter(CHAR_BASE_MS, ch));
    }
    timeout = setTimeout(typeNext, 200);
    return () => clearTimeout(timeout);
  }, [phase, dispatch]);

  // Type discoveries sequentially after subject is done
  useEffect(() => {
    if (!subjectDone || !dispatch) return;
    const lines = dispatch.discoveries || [];
    if (!lines.length) { setSigVisible(true); return; }

    let lineIdx = 0;
    let charIdx = 0;
    let buffer = "";
    let timeout;

    function typeDiscovery() {
      if (lineIdx >= lines.length) { setSigVisible(true); return; }
      const phrase = lines[lineIdx].phrase || "";

      if (charIdx < phrase.length) {
        const ch = phrase[charIdx];
        buffer += ch;
        setDiscoveryLines((prev) => {
          const next = [...prev];
          next[lineIdx] = buffer;
          return next;
        });
        charIdx++;
        timeout = setTimeout(typeDiscovery, jitter(CHAR_BASE_MS, ch));
      } else {
        lineIdx++;
        charIdx = 0;
        buffer = "";
        timeout = setTimeout(typeDiscovery, DISCOVERY_GAP_MS);
      }
    }

    timeout = setTimeout(typeDiscovery, 400);
    return () => clearTimeout(timeout);
  }, [subjectDone, dispatch]);

  // Stagger stamps in after signature
  useEffect(() => {
    if (!sigVisible || !dispatch) return;
    const s = dispatch.stamps || [];
    setStamps(s);
    s.forEach((_, i) => {
      setTimeout(() => {
        setStampsVisible((prev) => [...prev, i]);
      }, 400 + i * 180);
    });
    const total = 400 + s.length * 180 + 600;
    const hintTimer = setTimeout(() => setHintVisible(true), total + 1500);
    return () => clearTimeout(hintTimer);
  }, [sigVisible, dispatch]);

  const handleStampSaved = useCallback((kind, oldVal, newVal) => {
    setStamps((prev) =>
      prev.map((s) =>
        s.kind === kind && s.value === oldVal ? { ...s, value: newVal } : s
      )
    );
  }, []);

  if (phase === "idle") return null;

  return (
    <div className="dispatch-wrap" style={{ marginBottom: 32 }}>
      {/* Wire status indicator */}
      <div className="dispatch-wire-wrap">
        <div className="dispatch-blob-box">
          <svg
            className="dispatch-blob"
            width="48"
            height="36"
            viewBox="0 0 48 36"
          >
            <path
              d="M 24 8 C 30 8, 34 12, 34 18 C 34 24, 30 28, 24 28 C 18 28, 14 24, 14 18 C 14 12, 18 8, 24 8 Z"
              fill="#3a2f1c"
              fillOpacity="0.85"
            />
          </svg>
        </div>
        <div className="dispatch-status-text">
          {STATUS_PHRASES[statusIdx]}
        </div>
      </div>

      {/* Telegram envelope - drops in when pipeline returns */}
      <AnimatePresence>
        {phase === "revealing" && dispatch && (
          <motion.div
            className="dispatch-telegram"
            initial={{ y: 28, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{
              type: "spring",
              stiffness: 260,
              damping: 18,
              mass: 0.8,
            }}
          >
            <span className="dispatch-postmark">
              RAWTXT &middot; ENTRY {String(entryId || "").slice(-6).toUpperCase()}
            </span>

            <div className="dispatch-header">
              <span className="dispatch-header-from">FROM YOUR JOURNAL &middot; TO YOU</span>
              <span className="dispatch-header-time">{fmtTime(new Date())}</span>
            </div>

            {/* Subject typing */}
            <div className="dispatch-subject">
              {subjectTyped}
              {!subjectDone && <span className="dispatch-cursor" />}
            </div>

            {/* Discoveries body */}
            <div className="dispatch-body">
              {discoveryLines.map((line, i) => (
                <span
                  key={i}
                  className="dispatch-discovery-line"
                  dangerouslySetInnerHTML={{ __html: numberize(line) }}
                />
              ))}
              {discoveryLines.length > 0 && discoveryLines.length < (dispatch.discoveries || []).length && (
                <span className="dispatch-cursor" />
              )}
            </div>

            {/* Closing signature */}
            <AnimatePresence>
              {sigVisible && (
                <motion.span
                  className="dispatch-signature"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.7 }}
                >
                  -- your journal
                </motion.span>
              )}
            </AnimatePresence>

            {/* Stamps row */}
            {stamps.length > 0 && (
              <div className="dispatch-stamps-row" style={{ marginTop: 20 }}>
                {stamps.map((stamp, i) => (
                  <AnimatePresence key={`${stamp.kind}-${stamp.value}-${i}`}>
                    {stampsVisible.includes(i) && (
                      <motion.div
                        initial={{ scale: 0, rotate: -25 }}
                        animate={[
                          { scale: 1.3, rotate: -3, transition: { duration: 0.2 } },
                          { scale: 1, rotate: -2, transition: { duration: 0.25 } },
                        ]}
                        style={{ display: "inline-block" }}
                      >
                        <Stamp
                          stamp={stamp}
                          entryId={entryId}
                          onSaved={handleStampSaved}
                        />
                      </motion.div>
                    )}
                  </AnimatePresence>
                ))}
              </div>
            )}

            {/* Footer hint */}
            <div className={`dispatch-footer-hint ${hintVisible ? "visible" : ""}`}>
              tap any stamp to correct it &middot; we learn from every mark you make
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
