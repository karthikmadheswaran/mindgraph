import { useState, useEffect, useRef, Fragment } from "react";
import { motion, AnimatePresence } from "framer-motion";
import "../styles/dashboard.css";

// Shared witness-surface cards (drift + reflection gift), extracted from the
// retired Today view so Home (Noticed) and Journal (Intentions) render the same
// components. WITNESS, NOT MANAGER (locked product philosophy) — no streaks,
// no urgency, no guilt copy.

export const PO_TYPES = {
  loop:       { label: "Loop detected",     bg: "#faeee4", text: "#b84a2d", accent: "#b84a2d", tintBg: "#fdf6f2" },
  language:   { label: "Language signal",   bg: "#e8f0fa", text: "#7a9ab5", accent: "#7a9ab5", tintBg: "#f5f8fd" },
  avoidance:  { label: "Avoidance signal",  bg: "#e8f2eb", text: "#6b8a6b", accent: "#6b8a6b", tintBg: "#f5faf5" },
  identity:   { label: "Identity gap",      bg: "#f0e8f5", text: "#9a7ab5", accent: "#9a7ab5", tintBg: "#f8f5fd" },
  behavioral: { label: "Behavioral rhythm", bg: "#faeee4", text: "#b84a2d", accent: "#b84a2d", tintBg: "#fdf6f2" },
  // Drift (P5): a stated intention gone quiet. Calm muted blue-grey — witness,
  // not alarm. NEVER red/warning styling; guilt framing violates the product.
  drift:      { label: "Drifting",          bg: "#eceef2", text: "#7c8597", accent: "#8a93a6", tintBg: "#f6f7f9" },
};

const PO_BAR_HEIGHTS = [5, 14, 6, 8, 9, 7, 18];

// Parse the self-synthesis markdown doc into { title, body } insight blocks.
// The doc is "**Title**\n body\n\n**Title**\n body ..." (see app/synthesis_engine).
function parseSynthesis(text) {
  if (!text || typeof text !== "string") return [];
  const blocks = [];
  const re = /\*\*(.+?)\*\*\s*\n?([\s\S]*?)(?=\n\s*\*\*|$)/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const title = (m[1] || "").trim();
    const body = (m[2] || "").replace(/\s+/g, " ").trim();
    if (title) blocks.push({ title, body });
  }
  // Fallback: unparseable doc -> show it whole rather than nothing.
  if (blocks.length === 0 && text.trim()) blocks.push({ title: "", body: text.trim() });
  return blocks;
}

// The Reflection "gift": an evolving self-understanding doc that reveals non-obvious
// behavioural patterns (distinct from drift). Arrives WRAPPED (opened_at null) and
// reveals on open. Replaces the old shallow pattern cards. Reuses the po-* card look
// for the revealed state; a calm violet accent sets it apart from drift's grey.
const REFLECTION_ACCENT = "#8a7bb5";

// `bare` renders just the gift cards without the section chrome (separator,
// eyebrow, sub) — used inside Home's "Noticed" section, which carries its own
// header. `maxCards` caps how many insights render (Home shows a curated
// subset — the doc's leading "strongest" blocks; the full set is Journal's
// job). Default (unset) renders everything.
export function ReflectionGift({ reflection, onReveal, bare = false, maxCards }) {
  const allInsights = reflection?.synthesis_text ? parseSynthesis(reflection.synthesis_text) : [];
  const insights = maxCards ? allInsights.slice(0, maxCards) : allInsights;
  const alreadyOpened = Boolean(reflection?.opened);
  // Each insight is its OWN gift, opened separately. openedSet tracks which are
  // revealed this session; revealPosted guards the single "seen" POST.
  const [openedSet, setOpenedSet] = useState(() => new Set());
  const revealPosted = useRef(false);

  // Fresh gift => everything wrapped; a previously-seen gift => all revealed.
  // Re-run whenever the reflection payload changes (new gift after a regen).
  useEffect(() => {
    revealPosted.current = false;
    setOpenedSet(alreadyOpened ? new Set(insights.map((_, i) => i)) : new Set());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reflection]);

  if (!reflection || !reflection.synthesis_text) return null;

  const openCard = (i) => {
    setOpenedSet((prev) => {
      const next = new Set(prev);
      next.add(i);
      return next;
    });
    // Persist "seen" once, on the first card the user opens.
    if (!alreadyOpened && !revealPosted.current) {
      revealPosted.current = true;
      if (onReveal) onReveal();
    }
  };

  return (
    <div className="patterns-observatory reflection-revealed">
      {!bare && (
        <>
          <div className="po-sep" />
          <div className="po-head">
            <span className="po-eyebrow">What your journal reveals</span>
            <span className="po-noticed">Noticed reading all of it</span>
          </div>
          <div className="po-sub">
            Open each one when you're ready — patterns in how you think and move, not a summary.
          </div>
        </>
      )}
      <motion.div
        className="po-cards"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.45 }}
      >
        {insights.map((c, i) => (
          <div key={i} className="reflection-slot">
            <AnimatePresence mode="wait">
              {openedSet.has(i) ? (
                // Insight UNFOLDS up into place (as if lifted out of the box), with
                // a one-shot sparkle. Spring gives it a little life.
                <motion.div
                  key="open"
                  className="po-card reflection-opened-card"
                  style={{ borderLeft: `4px solid ${REFLECTION_ACCENT}`, transformOrigin: "bottom center" }}
                  initial={{ rotateX: 78, opacity: 0, y: 10 }}
                  animate={{ rotateX: 0, opacity: 1, y: 0 }}
                  transition={{ type: "spring", stiffness: 260, damping: 20, delay: 0.05 }}
                >
                  <motion.span
                    className="reflection-burst"
                    initial={{ opacity: 0.9, scale: 0.2, rotate: 0 }}
                    animate={{ opacity: 0, scale: 1.9, rotate: 40 }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                  >
                    ✦
                  </motion.span>
                  {c.title && <div className="po-title">{c.title}</div>}
                  <div className="po-body">{c.body}</div>
                </motion.div>
              ) : (
                // Wrapped gift. On open, the "lid" flips up and off (rotateX around
                // the top edge) before the insight unfolds in.
                <motion.div
                  key="wrap"
                  className="reflection-card-wrapped"
                  role="button"
                  tabIndex={0}
                  onClick={() => openCard(i)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      openCard(i);
                    }
                  }}
                  style={{ transformOrigin: "top center" }}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ rotateX: -95, opacity: 0, transition: { duration: 0.3, ease: [0.4, 0, 0.2, 1] } }}
                  transition={{ duration: 0.3, delay: i * 0.05 }}
                  whileHover={{ y: -3, scale: 1.02 }}
                  whileTap={{ scale: 0.95 }}
                >
                  <motion.div
                    className="reflection-mark"
                    animate={{ rotate: [0, 10, -10, 0], scale: [1, 1.08, 1] }}
                    transition={{ repeat: Infinity, duration: 3.5, ease: "easeInOut" }}
                  >
                    ✶
                  </motion.div>
                  <div className="reflection-card-hint">A reflection · tap to open</div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ))}
      </motion.div>
    </div>
  );
}

// Short date for footer context ("Apr 3").
function _fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? "" : d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// Map a GET /intentions/drift response into intention cards. WITNESS, NOT
// MANAGER (locked product philosophy): state the intention and how long it's
// been quiet — no streaks, no "falling behind", no nudging, no alarm. The API
// returns ALL pending intentions sorted drift_days descending (days-quiet
// order) — we preserve that order. Used by the Journal Intentions wall with
// the full list, and by Home with the single backend-picked card
// ({ intentions: [pick] }). id is carried through for resolve/dismiss.
export function buildIntentionCards(driftData) {
  const items = driftData?.intentions;
  if (!Array.isArray(items)) return [];
  return items
    .filter((it) => it && it.id)
    .map((it) => {
      const days = it.drift_days;
      const refs = it.reference_count || 1;
      const first = _fmtDate(it.first_stated_at);
      const last = _fmtDate(it.last_referenced_at);
      const title = it.text
        ? it.text.charAt(0).toUpperCase() + it.text.slice(1)
        : "A stated intention";
      // Multi-mention (ref >= 2) renders LIGHT, not heavy — SAME visual weight as
      // a single-mention card: a one-line body (the count is NOT narrated in
      // prose) + a compact one-line footer carrying the span + count
      // ("Apr 3 → May 13 · 2×"), reusing the muted po-foot-l styling — no badge,
      // no accent. Witness tone, same calm card. Guard the same-day re-mention
      // edge (last === first) so the footer never reads "Apr 3 → Apr 3".
      const multi = refs >= 2;
      const distinctLast = multi && last && last !== first;
      let body;
      let footL;
      if (!multi) {
        body = `You wrote this on ${first}. It hasn't come up since.`;
        footL = `First stated ${first}`;
      } else if (distinctLast) {
        body = `You kept coming back to this — last on ${last}. Quiet since.`;
        footL = `${first} → ${last} · ${refs}×`;
      } else {
        body = `You wrote this more than once on ${first}. Quiet since.`;
        footL = `${first} · ${refs}×`;
      }
      return {
        type: "drift",
        id: it.id,
        isDrifting: Boolean(it.is_drifting),
        statN: days != null ? String(days) : "",
        statU: "days quiet",
        title,
        body,
        footL,
        footR: "Still open →",
      };
    });
}


// One observatory card. Extracted from PatternsObservatory's map body unchanged
// so Home can render a single drift card outside the full Observatory section.
export function PoCard({ card: c, index: i = 0, onDriftAction }) {
  const t = PO_TYPES[c.type];
  return (
    <motion.div
      className="po-card"
      style={{ borderLeft: `4px solid ${t.accent}` }}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: i * 0.08, ease: [0.25, 0.1, 0.25, 1] }}
    >
      <div className="po-card-top">
        <span className="po-pill" style={{ background: t.bg, color: t.text }}>
          {t.label}
        </span>
        <div className="po-stat">
          <span className="po-stat-n" style={{ color: t.accent }}>{c.statN}</span>
          <span className="po-stat-u">{c.statU}</span>
        </div>
      </div>
      <div className="po-title">{c.title}</div>
      <div className="po-body">{c.body}</div>
      {c.quote && (
        <div className="po-quote">
          <div className="po-quote-text">"{c.quote}"</div>
          <div className="po-quote-src">{c.quoteSrc}</div>
        </div>
      )}
      {c.cycle && (
        <div className="po-cycle">
          {c.cycle.map((s, j) => (
            <Fragment key={j}>
              <span
                className={`po-chip${s.on ? " on" : ""}`}
                style={s.on ? { background: "#faeee4", color: "#b84a2d", borderColor: "#f0d0b0" } : undefined}
              >
                {s.l}
              </span>
              {j < c.cycle.length - 1 && <span className="po-arrow">→</span>}
            </Fragment>
          ))}
        </div>
      )}
      {c.barchart && (
        <div className="po-barchart">
          {PO_BAR_HEIGHTS.map((h, bi) => {
            const isSunday = bi === 1 || bi === 6;
            return (
              <span
                key={bi}
                className="po-bar"
                style={{
                  height: h,
                  background: isSunday ? "#b84a2d" : "#e8e0d4",
                  opacity: bi === 1 ? 0.35 : bi === 6 ? 0.7 : 1,
                }}
              />
            );
          })}
        </div>
      )}
      <div className="po-foot">
        <span className="po-foot-l">
          <span className="po-dot" style={{ background: t.accent }} />
          {c.footL}
        </span>
        {c.type === "drift" && onDriftAction && c.id ? (
          <span style={{ display: "flex", gap: "14px" }}>
            <button type="button" className="po-foot-btn" style={{ color: t.accent }} onClick={() => onDriftAction(c.id, "resolve")}>
              Did this
            </button>
            <button type="button" className="po-foot-btn" style={{ color: "#8a8780" }} onClick={() => onDriftAction(c.id, "dismiss")}>
              Dismiss
            </button>
          </span>
        ) : c.footR ? (
          <button type="button" className="po-foot-btn" style={{ color: t.accent }}>
            {c.footR}
          </button>
        ) : null}
      </div>
    </motion.div>
  );
}
