import { useCallback, useEffect, useRef, useState } from "react";
import { API, authHeaders } from "../utils/auth";

// Patterns v1 (founder-gated) — components 1-3 of
// docs/designs/graph-v2-patterns.md. Witness, not manager: every block is a
// question the user asks about themselves; no targets, streaks, scores, or
// action suggestions. Renders inside the Journal Patterns section only when
// the gate (utils/patternsGate.js) passes; the backend 404s otherwise.
//
// COPY: all user-facing strings in this file are placeholders pending founder
// review — witness register throughout.

// Fixed category -> hue mapping, bottom-to-top stack order. Never cycled, and
// color follows the category regardless of which weeks have data. Hues are the
// dataviz reference categorical theme validated against the app surface
// #f2ece1 (adjacent-pair CVD separation passes in this exact order); "other"
// folds to the neutral tan per the ≤8-hues rule. The legend's text labels are
// the required relief for the low-contrast slots.
const CATEGORY_COLORS = {
  work: "#2a78d6",
  personal: "#1baf7a",
  health: "#eda100",
  finance: "#008300",
  family: "#4a3aa7",
  hobby: "#e34948",
  travel: "#e87ba4",
  education: "#eb6834",
  other: "#8b7b69",
};
const STACK_ORDER = Object.keys(CATEGORY_COLORS);

const MIN_TAGGED_ENTRIES = 5;

const CHART_W = 640;
const CHART_H = 170;
const CHART_PAD_BOTTOM = 22;

const pct = (share) => `${Math.round((share || 0) * 100)}%`;

const weekLabel = (isoDate) => {
  const d = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return isoDate;
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
};

// Trend framing is data, never good/bad (no colored deltas, no arrows).
function gravityTrend(entity) {
  const cur = entity.share || 0;
  const prior = entity.prior_share || 0;
  if (prior === 0 && cur > 0) return "new in this window";
  if (Math.abs(cur - prior) < 0.03) return `about the same as before (${pct(prior)})`;
  return cur > prior ? `up from ${pct(prior)}` : `down from ${pct(prior)}`;
}

function AttentionMixChart({ mix }) {
  const [hover, setHover] = useState(null);
  const svgWrapRef = useRef(null);

  const weeks = mix.weeks || [];
  if (weeks.length === 0) return null;

  const totals = weeks.map((w) =>
    STACK_ORDER.reduce((sum, cat) => sum + (w.counts[cat] || 0), 0)
  );
  const maxTotal = Math.max(1, ...totals);
  const plotH = CHART_H - CHART_PAD_BOTTOM;
  const xAt = (i) => (weeks.length === 1 ? CHART_W / 2 : (i * CHART_W) / (weeks.length - 1));
  const yAt = (v) => plotH - (v / maxTotal) * (plotH - 6);

  // Stacked areas bottom-up in fixed order; each band is the polygon between
  // the running cumulative sum with and without this category.
  const cumulative = weeks.map(() => 0);
  const bands = STACK_ORDER.map((cat) => {
    const lower = [...cumulative];
    weeks.forEach((w, i) => {
      cumulative[i] += w.counts[cat] || 0;
    });
    const upper = [...cumulative];
    if (upper.every((v, i) => v === lower[i])) return null;
    const top = upper.map((v, i) => `${xAt(i)},${yAt(v)}`);
    const bottom = lower.map((v, i) => `${xAt(i)},${yAt(v)}`).reverse();
    return { cat, points: [...top, ...bottom].join(" ") };
  }).filter(Boolean);

  const activeCategories = STACK_ORDER.filter((cat) =>
    weeks.some((w) => (w.counts[cat] || 0) > 0)
  );

  const handleMove = (event) => {
    const rect = svgWrapRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return;
    const frac = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    const index = Math.round(frac * (weeks.length - 1));
    setHover({ index, leftPct: (xAt(index) / CHART_W) * 100 });
  };

  const hoverWeek = hover ? weeks[hover.index] : null;

  return (
    <div className="pat-chart-wrap">
      <div
        ref={svgWrapRef}
        className="pat-chart"
        onMouseMove={handleMove}
        onMouseLeave={() => setHover(null)}
      >
        <svg
          viewBox={`0 0 ${CHART_W} ${CHART_H}`}
          preserveAspectRatio="none"
          role="img"
          aria-label="Weekly stacked area chart of entry categories"
        >
          {bands.map((band) => (
            <polygon
              key={band.cat}
              points={band.points}
              fill={CATEGORY_COLORS[band.cat]}
              stroke="#f2ece1"
              strokeWidth="1.5"
            />
          ))}
          {hover && (
            <line
              x1={xAt(hover.index)}
              x2={xAt(hover.index)}
              y1="0"
              y2={plotH}
              stroke="#6b5f4e"
              strokeWidth="1"
              strokeDasharray="3 3"
            />
          )}
          <line x1="0" x2={CHART_W} y1={plotH} y2={plotH} stroke="rgba(26, 22, 18, 0.14)" />
        </svg>
        <div className="pat-chart-xlabels" aria-hidden="true">
          <span>{weekLabel(weeks[0].week_start)}</span>
          <span>{weekLabel(weeks[weeks.length - 1].week_start)}</span>
        </div>
        {hoverWeek && (
          <div
            className="pat-tooltip"
            style={{ left: `${hover.leftPct}%` }}
            role="status"
          >
            <div className="pat-tooltip-week">week of {weekLabel(hoverWeek.week_start)}</div>
            {STACK_ORDER.filter((cat) => (hoverWeek.counts[cat] || 0) > 0).map(
              (cat) => (
                <div key={cat} className="pat-tooltip-row">
                  <span
                    className="pat-swatch"
                    style={{ background: CATEGORY_COLORS[cat] }}
                  />
                  {cat} · {hoverWeek.counts[cat]}
                </div>
              )
            )}
            {totals[hover.index] === 0 && (
              <div className="pat-tooltip-row">nothing written</div>
            )}
          </div>
        )}
      </div>
      <div className="pat-legend">
        {activeCategories.map((cat) => (
          <span key={cat} className="pat-legend-item">
            <span className="pat-swatch" style={{ background: CATEGORY_COLORS[cat] }} />
            {cat}
          </span>
        ))}
      </div>
    </div>
  );
}

function PatternsSection({ isActive, intentions, onIntentionAction }) {
  const [mix, setMix] = useState(null);
  const [gravity, setGravity] = useState(null);
  const [hidden, setHidden] = useState(false);
  const loadedRef = useRef(false);

  const fetchPatterns = useCallback(async () => {
    try {
      const headers = await authHeaders();
      const [mixRes, gravityRes] = await Promise.all([
        fetch(`${API}/patterns/attention-mix`, { headers }),
        fetch(`${API}/patterns/gravity`, { headers }),
      ]);
      // Backend gate says no (or routes not deployed yet): stay invisible.
      if (mixRes.status === 404 || gravityRes.status === 404) {
        setHidden(true);
        return;
      }
      if (mixRes.ok) setMix(await mixRes.json());
      if (gravityRes.ok) setGravity(await gravityRes.json());
    } catch {
      /* transient failure — quiet section, retry on next activation */
      loadedRef.current = false;
    }
  }, []);

  useEffect(() => {
    if (!isActive || loadedRef.current) return;
    loadedRef.current = true;
    fetchPatterns();
  }, [isActive, fetchPatterns]);

  if (hidden) return null;

  const sparseMix = !mix || (mix.tagged_entries || 0) < MIN_TAGGED_ENTRIES;
  const gravityEntities = gravity?.entities || [];
  const ledger = intentions || [];

  return (
    <div className="pat-section">
      {/* ——— 1. Attention Mix ——— */}
      <h3 className="pat-question">Where has my attention been going?</h3>
      {sparseMix ? (
        <p className="pat-quiet">
          Too few entries to see a shape yet — this fills in as you write.
        </p>
      ) : (
        <>
          <p className="pat-subtext">Where your words have been going, week by week.</p>
          <AttentionMixChart mix={mix} />
        </>
      )}

      {/* ——— 2. Gravity ——— */}
      <h3 className="pat-question">What&apos;s taking up the most space?</h3>
      {gravityEntities.length === 0 ? (
        <p className="pat-quiet">
          No people or projects have taken up space in the last{" "}
          {gravity?.window_days || 30} days.
        </p>
      ) : (
        <div className="pat-gravity">
          {gravityEntities.map((entity) => (
            <div key={entity.entity_id} className="pat-gravity-row">
              <span className="pat-gravity-name">{entity.name}</span>
              <span className="pat-gravity-meta">
                in {pct(entity.share)} of your entries · {gravityTrend(entity)}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* ——— 3. Drift ledger — reuses the Journal's drift read path + the
             existing resolve/dismiss handlers (endpoints + events unchanged) ——— */}
      <h3 className="pat-question">What did I say I wanted that&apos;s gone quiet?</h3>
      {ledger.length === 0 ? (
        <p className="pat-quiet">Nothing pending — the ledger is quiet.</p>
      ) : (
        <div className="intent-list">
          {ledger.map((card) => (
            <div key={card.id} className="intent-row">
              <span className="intent-text">{card.title}</span>
              <span className="intent-meta">
                {card.statN !== "" ? `${card.statN} days quiet` : "quiet time unknown"}
              </span>
              <span className="intent-actions">
                <button
                  type="button"
                  className="po-foot-btn"
                  onClick={() => onIntentionAction(card.id, "resolve")}
                >
                  Did this
                </button>
                <button
                  type="button"
                  className="po-foot-btn intent-dismiss"
                  onClick={() => onIntentionAction(card.id, "dismiss")}
                >
                  Dismiss
                </button>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default PatternsSection;
