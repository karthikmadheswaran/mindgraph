import { useState, useEffect, useRef, useCallback } from "react";
import { API, authHeaders } from "../utils/auth";
import { supabase } from "../supabaseClient";
import { trackEvent } from "../posthog";
import AnimatedView from "./AnimatedView";
import Toast from "./Toast";
import DispatchReveal from "./DispatchReveal";
import { PoCard, ReflectionGift, buildIntentionCards } from "./InsightCards";
import "../styles/input.css";

const POLL_INTERVAL_MS = 2500;
const MAX_POLLS = 80; // 200s ceiling — non-dedup pipeline runs 5+ Gemini calls and can take 60-90s
const RECENT_COUNT = 3;

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function fmtDate(d) {
  return d.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

function fmtTime(d) {
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

function fmtRecentDate(str) {
  const d = new Date(str);
  return isNaN(d)
    ? ""
    : d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

const MicIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </svg>
);

const AttachIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M21 12l-8.5 8.5a5 5 0 0 1-7-7L14 5a3.5 3.5 0 0 1 5 5l-9 9a2 2 0 0 1-3-3l7-7" />
  </svg>
);

function Home({ isActive, onNavigate }) {
  const [text, setText] = useState("");
  const [recording, setRecording] = useState(false);
  const [toast, setToast] = useState(null);
  const [firstName, setFirstName] = useState("there");
  const [now, setNow] = useState(new Date());
  const taRef = useRef(null);

  // Dispatch reveal state
  const [dispatchPhase, setDispatchPhase] = useState("idle"); // "idle"|"processing"|"revealing"
  const [dispatchPayload, setDispatchPayload] = useState(null);
  const [dispatchEntryId, setDispatchEntryId] = useState(null);
  const pollRef = useRef(null);
  const pollCountRef = useRef(0);

  // Witness surfaces (Noticed) + the 3 most recent entries
  const [recentEntries, setRecentEntries] = useState(null);
  const [driftCards, setDriftCards] = useState([]);
  const [reflection, setReflection] = useState(null);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      const user = session?.user;
      if (!user) return;
      const full = user.user_metadata?.full_name;
      const raw = full ? full.split(" ")[0] : user.email?.split("@")[0] || "there";
      setFirstName(raw.charAt(0).toUpperCase() + raw.slice(1));
    });
  }, []);

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (isActive && taRef.current) taRef.current.focus();
  }, [isActive]);

  // Bounded card composer: the textarea auto-grows with the text instead of
  // occupying a fixed 50vh ruled page.
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${ta.scrollHeight}px`;
  }, [text]);

  const fetchRecent = useCallback(async () => {
    try {
      const headers = await authHeaders();
      const res = await fetch(
        `${API}/entries?page=1&page_size=${RECENT_COUNT}`,
        { headers }
      );
      if (!res.ok) throw new Error("fetch failed");
      const data = await res.json();
      setRecentEntries(data.entries || []);
    } catch {
      setRecentEntries((prev) => prev || []);
    }
  }, []);

  // Drift pick v1: the backend chooses THE one card (scored, 48h-sticky, 14d
  // cooldown, self-judgment guard) and logs drift_card_served per pick.
  const refetchDrift = useCallback(async () => {
    try {
      const headers = await authHeaders();
      const res = await fetch(`${API}/intentions/drift?pick=true`, { headers });
      if (!res.ok) return;
      const data = await res.json();
      setDriftCards(data?.pick ? buildIntentionCards({ intentions: [data.pick] }) : []);
    } catch {
      /* keep last-known card on a transient fetch error */
    }
  }, []);

  // Resolve ("Did this") / dismiss a drifting intention — same optimistic
  // remove + server re-sync as the Today view, so behavior (and any analytics
  // fired server-side) is identical from Home.
  const handleDriftAction = useCallback(
    async (id, action) => {
      if (!id || (action !== "resolve" && action !== "dismiss")) return;
      setDriftCards((cards) => cards.filter((c) => c.id !== id));
      try {
        const headers = await authHeaders();
        const res = await fetch(`${API}/intentions/${id}/${action}`, { method: "POST", headers });
        if (!res.ok) throw new Error(`${action} failed: ${res.status}`);
        await refetchDrift();
      } catch (err) {
        console.error("drift action failed", err);
        await refetchDrift();
      }
    },
    [refetchDrift]
  );

  // Persist that the reflection was seen (fired once, when the first card is opened).
  const handleReflectionReveal = useCallback(async () => {
    try {
      const headers = await authHeaders();
      await fetch(`${API}/insights/synthesis/open`, { method: "POST", headers });
    } catch (err) {
      console.error("reflection open failed", err);
    }
  }, []);

  useEffect(() => {
    if (!isActive) return;
    fetchRecent();
    refetchDrift();
    const fetchSynthesis = async () => {
      try {
        const headers = await authHeaders();
        const res = await fetch(`${API}/insights/synthesis`, { headers });
        const synthesisData = res.ok ? await res.json() : null;
        setReflection(synthesisData?.data || null);
      } catch {
        // keep current state — the section simply doesn't render on empties
      }
    };
    fetchSynthesis();
  }, [isActive, fetchRecent, refetchDrift]);

  // Poll entry status until complete
  const startPolling = useCallback((entryId) => {
    // Defensive: kill any prior poller before starting a new one — without this,
    // back-to-back submissions leak intervals and produce duplicate poll-N logs.
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    pollCountRef.current = 0;
    pollRef.current = setInterval(async () => {
      pollCountRef.current++;
      if (pollCountRef.current > MAX_POLLS) {
        clearInterval(pollRef.current);
        setDispatchPhase("idle");
        setToast({ message: "Processing is taking a while. Check back soon.", type: "success" });
        return;
      }

      try {
        const headers = await authHeaders();
        const res = await fetch(`${API}/entries/${entryId}/status`, { headers });
        if (!res.ok) {
          console.warn(`[dispatch poll] status fetch ${res.status} for entry ${entryId}`);
          return;
        }
        const data = await res.json();
        console.log(
          `[dispatch poll #${pollCountRef.current}] status=${data?.status} stage=${data?.pipeline_stage} dp=${
            data?.dispatch_payload == null
              ? "null"
              : typeof data.dispatch_payload === "string"
              ? `string(${data.dispatch_payload.length}c)`
              : `object(${Object.keys(data.dispatch_payload).length}k)`
          }`,
        );

        // Defensive: dispatch_payload may come back as a JSON string if the
        // column is TEXT or supabase-py double-stringified during write.
        let dp = data.dispatch_payload;
        if (typeof dp === "string") {
          try { dp = JSON.parse(dp); } catch { dp = null; }
        }
        const hasDispatch = dp && typeof dp === "object";

        if (data.status === "error") {
          // Pipeline crashed — stop polling and surface a toast.
          clearInterval(pollRef.current);
          console.warn("[dispatch poll] status=error — returning to idle");
          setDispatchPhase("idle");
          setToast({ message: "Processing failed. Please try again.", type: "error" });
          fetchRecent();
        } else if (data.status === "completed" && hasDispatch) {
          // Both signals present — reveal the telegram.
          clearInterval(pollRef.current);
          console.log("[dispatch poll] revealing with payload:", dp);
          setDispatchPayload(dp);
          setDispatchPhase("revealing");
          fetchRecent();
        } else if (data.status === "completed" && !hasDispatch) {
          // Status flipped but dispatch_payload hasn't arrived in the read yet
          // — read-after-write inconsistency. Keep polling instead of giving up;
          // the next 1-2 polls should catch the payload.
          console.log("[dispatch poll] status=completed but dp not yet visible — continuing to poll");
        }
        // else: status=processing — keep polling normally
      } catch (err) {
        console.warn("[dispatch poll] exception:", err);
        /* keep polling */
      }
    }, POLL_INTERVAL_MS);
  }, [fetchRecent]);

  useEffect(() => {
    return () => clearInterval(pollRef.current);
  }, []);

  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;

  const handleSubmit = async () => {
    if (!text.trim()) return;
    const submittedText = text;

    setDispatchPhase("processing");
    setDispatchPayload(null);
    setText("");

    try {
      const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
      const headers = await authHeaders();
      const response = await fetch(`${API}/entries/async`, {
        method: "POST",
        headers,
        body: JSON.stringify({ raw_text: submittedText, user_timezone: userTimezone }),
      });
      if (response.status === 401) {
        setDispatchPhase("idle");
        setToast({ message: "Session expired. Please log in again.", type: "error" });
        return;
      }
      if (!response.ok) throw new Error("submission failed");

      const data = await response.json();
      const entryId = data.entry_id;
      setDispatchEntryId(entryId);
      trackEvent("entry_submitted", { input_type: "text", char_count: submittedText.length });

      startPolling(entryId);
    } catch {
      setDispatchPhase("idle");
      setToast({ message: "Failed to submit entry. Please try again.", type: "error" });
    }
  };

  // Noticed section content: at most 2 cards — the backend-picked drift card
  // (drift pick v1) + the reflection gift. The gift renders whenever a
  // synthesis exists: unopened arrives wrapped, previously-opened renders
  // revealed (Home is now the only surface for past reflections since Today
  // was retired). Neither -> the whole section (header included) stays out of
  // the DOM.
  const noticedDriftCard = driftCards.length > 0 ? driftCards[0] : null;
  const hasGift = Boolean(reflection?.synthesis_text);
  const showNoticed = Boolean(noticedDriftCard) || hasGift;

  return (
    <AnimatedView viewKey="home" isActive={isActive}>
      <div className="write-view">
        <div className="write-wrap minimal">
          <div className="write-mini-head">
            <div className="write-date">{fmtDate(now)}</div>
            <div className="write-weather">
              {fmtTime(now)}
            </div>
          </div>

          <h1 className="write-greeting">
            {getGreeting()}, <em>{firstName}</em>.
          </h1>

          <p className="write-nudge">
            What&apos;s been on your mind that you haven&apos;t said out loud?
          </p>

          {/* Composer — bounded card, grows with the text */}
          <div className="composer">
            <textarea
              ref={taRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="What's on your mind? Messy is fine."
              rows={3}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSubmit();
              }}
            />

            <div className="composer-rail">
              <span className="count">
                <b>{wordCount}</b> words
              </span>
              <span className="rail-dot" />
              {recording ? (
                <>
                  <button className="rail-btn recording" onClick={() => setRecording(false)}>
                    <MicIcon />
                  </button>
                  <span className="voice-wave rec">
                    {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => <span key={i} className="bar" />)}
                  </span>
                </>
              ) : (
                <>
                  <button className="rail-btn" title="Voice" onClick={() => setRecording(true)}>
                    <MicIcon />
                  </button>
                  <button className="rail-btn" title="Attach">
                    <AttachIcon />
                  </button>
                </>
              )}
              <button
                className="send-btn"
                disabled={dispatchPhase === "processing" || !text.trim()}
                onClick={handleSubmit}
              >
                {dispatchPhase === "processing" ? (
                  <span className="spinner small" />
                ) : (
                  <>Send <span className="kbd">⌘↵</span></>
                )}
              </button>
            </div>
          </div>

          {/* Dispatch reveal -- shows after submit */}
          {dispatchPhase !== "idle" && (
            <DispatchReveal
              dispatch={dispatchPayload}
              entryId={dispatchEntryId}
              phase={dispatchPhase}
              firstName={firstName}
            />
          )}

          {/* Noticed — witness surfaces, max 2 cards, section hidden when empty */}
          {showNoticed && (
            <div className="noticed-section">
              <div className="entries-section-head">
                <span className="entries-section-label">Noticed</span>
              </div>
              <div className="noticed-cards">
                {noticedDriftCard && (
                  <PoCard card={noticedDriftCard} onDriftAction={handleDriftAction} />
                )}
                {hasGift && (
                  <ReflectionGift
                    bare
                    reflection={reflection}
                    onReveal={handleReflectionReveal}
                  />
                )}
              </div>
            </div>
          )}

          {/* Recent — the 3 most recent entries, one line each */}
          <div className="recent-entries-section">
            <div className="entries-section-head">
              <span className="entries-section-label">Recent</span>
              <button
                type="button"
                className="recent-all-link"
                onClick={() => onNavigate && onNavigate("journal")}
              >
                All entries →
              </button>
            </div>
            {recentEntries === null ? (
              <div>
                {[0, 1, 2].map((i) => (
                  <div key={i} className="recent-entry-skeleton">
                    <div className="skeleton-line" style={{ width: "65%" }} />
                    <div className="skeleton-line short" />
                  </div>
                ))}
              </div>
            ) : recentEntries.length === 0 ? (
              <p className="recent-empty">Nothing yet. Start writing.</p>
            ) : (
              recentEntries.slice(0, RECENT_COUNT).map((entry) => {
                const title =
                  entry.auto_title ||
                  (entry.raw_text
                    ? entry.raw_text.slice(0, 80) + (entry.raw_text.length > 80 ? "…" : "")
                    : "Untitled");
                return (
                  <div
                    key={entry.id || entry.created_at}
                    className="recent-entry-row recent-entry-row--line"
                  >
                    <span className="recent-entry-date">{fmtRecentDate(entry.created_at)}</span>
                    <span className="recent-entry-title">{title}</span>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <Toast
          message={toast?.message}
          type={toast?.type || "success"}
          visible={!!toast}
          onDismiss={() => setToast(null)}
        />
      </div>
    </AnimatedView>
  );
}

export default Home;
