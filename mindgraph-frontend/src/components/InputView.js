import { useState, useEffect, useRef, useCallback } from "react";
import { API, authHeaders } from "../utils/auth";
import { supabase } from "../supabaseClient";
import { trackEvent } from "../posthog";
import AnimatedView from "./AnimatedView";
import Toast from "./Toast";
import "../styles/input.css";

const STREAK_COUNT = 47;

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

function fmtEntryDate(dateStr) {
  const d = new Date(dateStr);
  const date = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
  return `${date} · ${time}`;
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

function EntrySkeleton() {
  return (
    <div className="recent-entry-skeleton">
      <div className="skeleton-line" style={{ width: "68%" }} />
      <div className="skeleton-line short" />
    </div>
  );
}

function InputView({ isActive, onEntrySubmitted }) {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null);
  const [firstName, setFirstName] = useState("there");
  const [now, setNow] = useState(new Date());
  const [recording, setRecording] = useState(false);
  const [entries, setEntries] = useState(null); // null = not yet fetched
  const [entriesLoading, setEntriesLoading] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const taRef = useRef(null);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      const user = session?.user;
      if (!user) return;
      const full = user.user_metadata?.full_name;
      const raw = full
        ? full.split(" ")[0]
        : user.email?.split("@")[0] || "there";
      // Fix 3: always capitalize first letter
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

  const fetchEntries = useCallback(async () => {
    setEntriesLoading(true);
    try {
      const headers = await authHeaders();
      const res = await fetch(`${API}/entries`, { headers });
      if (!res.ok) throw new Error("fetch failed");
      const data = await res.json();
      setEntries((data.entries || []).slice(0, 5));
    } catch {
      setEntries([]);
    } finally {
      setEntriesLoading(false);
    }
  }, []);

  // Fetch when the view becomes active
  useEffect(() => {
    if (isActive) fetchEntries();
  }, [isActive, fetchEntries]);

  const handleSubmit = async () => {
    if (!text.trim()) return;
    setLoading(true);
    try {
      const userTimezone =
        Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
      const headers = await authHeaders();
      const response = await fetch(`${API}/entries/async`, {
        method: "POST",
        headers,
        body: JSON.stringify({ raw_text: text, user_timezone: userTimezone }),
      });
      if (response.status === 401) {
        setToast({ message: "Session expired. Please log in again.", type: "error" });
        return;
      }
      if (!response.ok) throw new Error("Entry submission failed");
      await response.json();
      setToast({ message: "Entry submitted! Processing...", type: "success" });
      trackEvent("entry_submitted", { input_type: "text", char_count: text.length });
      setText("");
      if (onEntrySubmitted) onEntrySubmitted();
      fetchEntries(); // refresh list after submit
    } catch {
      setToast({ message: "Failed to submit entry. Please try again.", type: "error" });
    } finally {
      setLoading(false);
    }
  };

  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;

  const toggleExpand = (id) =>
    setExpandedId((prev) => (prev === id ? null : id));

  return (
    <AnimatedView viewKey="write" isActive={isActive}>
      <div className="write-view">
        <div className="write-wrap minimal">
          <div className="write-mini-head">
            <div className="write-date">{fmtDate(now)}</div>
            <div className="write-weather">
              {fmtTime(now)} · Day {STREAK_COUNT}
            </div>
          </div>

          <h1 className="write-greeting">
            {getGreeting()}, <em>{firstName}</em>.
          </h1>

          <p className="write-nudge">
            What&apos;s been on your mind that you haven&apos;t said out loud?
          </p>

          <div className="composer tall">
            <textarea
              ref={taRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Start anywhere…"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey))
                  handleSubmit();
              }}
            />

            <div className="composer-rail">
              <span className="count">
                <b>{wordCount}</b> words
              </span>
              <span className="rail-dot" />
              {recording ? (
                <>
                  <button
                    className="rail-btn recording"
                    onClick={() => setRecording(false)}
                  >
                    <MicIcon />
                  </button>
                  <span className="voice-wave rec">
                    {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
                      <span key={i} className="bar" />
                    ))}
                  </span>
                </>
              ) : (
                <>
                  <button
                    className="rail-btn"
                    title="Voice"
                    onClick={() => setRecording(true)}
                  >
                    <MicIcon />
                  </button>
                  <button className="rail-btn" title="Attach">
                    <AttachIcon />
                  </button>
                </>
              )}
              <button
                className="send-btn"
                disabled={loading || !text.trim()}
                onClick={handleSubmit}
              >
                {loading ? (
                  <span className="spinner small" />
                ) : (
                  <>
                    Send <span className="kbd">⌘↵</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Fix 2: Recent entries */}
          <div className="recent-entries-section">
            <div className="recent-entries-head">
              <span>Recent entries</span>
            </div>
            <hr className="recent-entries-rule" />

            {entriesLoading || entries === null ? (
              <div className="recent-entries-list">
                <EntrySkeleton />
                <EntrySkeleton />
                <EntrySkeleton />
              </div>
            ) : entries.length === 0 ? (
              <p className="recent-empty">Nothing yet. Start writing.</p>
            ) : (
              <div className="recent-entries-list">
                {entries.map((entry) => {
                  const id = entry.id || entry.created_at;
                  const title =
                    entry.auto_title ||
                    (entry.raw_text
                      ? entry.raw_text.slice(0, 60) +
                        (entry.raw_text.length > 60 ? "…" : "")
                      : "Untitled");
                  const isOpen = expandedId === id;
                  return (
                    <div
                      key={id}
                      className="recent-entry-row"
                      onClick={() => toggleExpand(id)}
                    >
                      <div className="recent-entry-title">{title}</div>
                      <div className="recent-entry-date">
                        {fmtEntryDate(entry.created_at)}
                      </div>
                      {isOpen && entry.raw_text && (
                        <p className="recent-entry-body">
                          {entry.raw_text}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
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

export default InputView;
