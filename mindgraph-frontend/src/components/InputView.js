import { useState, useEffect, useRef, useCallback } from "react";
import { API, authHeaders } from "../utils/auth";
import { supabase } from "../supabaseClient";
import { trackEvent } from "../posthog";
import AnimatedView from "./AnimatedView";
import Toast from "./Toast";
import DispatchReveal from "./DispatchReveal";
import EntriesList from "./EntriesList";
import EntriesControls from "./EntriesControls";
import "../styles/input.css";

const STREAK_COUNT = 47;
const POLL_INTERVAL_MS = 2500;
const MAX_POLLS = 80; // 200s ceiling — non-dedup pipeline runs 5+ Gemini calls and can take 60-90s

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

function buildFilterOptions(entries) {
  const moods = new Set();
  const persons = new Set();
  const categories = new Set();
  for (const e of entries) {
    const stamps = e.dispatch_payload?.stamps || [];
    for (const s of stamps) {
      if (s.kind === "mood" && s.value) moods.add(s.value);
      if (s.kind === "person" && s.value) persons.add(s.value);
      if (s.kind === "pattern" && s.value) categories.add(s.value);
    }
  }
  return {
    mood: Array.from(moods),
    person: Array.from(persons),
    category: Array.from(categories),
  };
}

function InputView({ isActive, onEntrySubmitted }) {
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

  // Entries list state
  const [entries, setEntries] = useState(null);
  const [totalCount, setTotalCount] = useState(0);
  const [entriesLoading, setEntriesLoading] = useState(false);
  const [appendingMore, setAppendingMore] = useState(false);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({});
  const [filterOptions, setFilterOptions] = useState({ mood: [], person: [], category: [] });
  const PAGE_SIZE = 10;

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

  const fetchEntries = useCallback(async (pg = 1, activeFilters = {}, append = false) => {
    if (append) {
      setAppendingMore(true);
    } else {
      setEntriesLoading(true);
    }

    try {
      const params = new URLSearchParams({
        page: String(pg),
        page_size: String(PAGE_SIZE),
      });
      if (activeFilters.mood) params.set("mood", activeFilters.mood);
      if (activeFilters.person) params.set("person", activeFilters.person);
      if (activeFilters.category) params.set("category", activeFilters.category);
      if (activeFilters.date_from) params.set("date_from", activeFilters.date_from);
      if (activeFilters.date_to) params.set("date_to", activeFilters.date_to);
      if (activeFilters.search) params.set("search", activeFilters.search);

      const headers = await authHeaders();
      const res = await fetch(`${API}/entries?${params}`, { headers });
      if (!res.ok) throw new Error("fetch failed");
      const data = await res.json();
      const fetched = data.entries || [];

      if (append) {
        setEntries((prev) => [...(prev || []), ...fetched]);
      } else {
        setEntries(fetched);
        if (pg === 1 && !Object.values(activeFilters).some(Boolean) && fetched.length > 0) {
          setFilterOptions((prev) => {
            const hasOptions = prev.mood.length > 0 || prev.person.length > 0 || prev.category.length > 0;
            return hasOptions ? prev : buildFilterOptions(fetched);
          });
        }
      }
      setTotalCount(data.total_count || 0);
    } catch {
      if (!append) setEntries([]);
    } finally {
      setEntriesLoading(false);
      setAppendingMore(false);
    }
  }, []);

  const fetchFilterOptions = useCallback(async () => {
    try {
      const headers = await authHeaders();
      const res = await fetch(`${API}/entries/filter-options`, { headers });
      if (!res.ok) {
        console.warn(`filter-options: ${res.status} — filter dropdowns will use client-side fallback`);
        setFilterOptions({ mood: [], person: [], category: [] });
        return;
      }
      const data = await res.json();
      if (data && Array.isArray(data.mood) && Array.isArray(data.person) && Array.isArray(data.category)) {
        setFilterOptions(data);
      }
    } catch (err) {
      console.warn("filter-options fetch failed:", err);
      setFilterOptions({ mood: [], person: [], category: [] });
    }
  }, []);

  useEffect(() => {
    if (isActive) {
      setPage(1);
      fetchEntries(1, filters);
      fetchFilterOptions();
    }
  }, [isActive]); // eslint-disable-line react-hooks/exhaustive-deps

  // Re-fetch when filters change
  const handleFiltersChange = useCallback((newFilters) => {
    setFilters(newFilters);
    setPage(1);
    fetchEntries(1, newFilters);
  }, [fetchEntries]);

  const handlePageChange = useCallback((pg) => {
    setPage(pg);
    fetchEntries(pg, filters);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [fetchEntries, filters]);

  const handleLoadMore = useCallback(() => {
    const nextPage = page + 1;
    setPage(nextPage);
    fetchEntries(nextPage, filters, true);
  }, [fetchEntries, filters, page]);

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

        if (data.status === "completed" || data.status === "error") {
          clearInterval(pollRef.current);
          // Defensive: dispatch_payload may come back as a JSON string if the
          // column is TEXT or supabase-py double-stringified during write.
          let dp = data.dispatch_payload;
          if (typeof dp === "string") {
            try { dp = JSON.parse(dp); } catch { dp = null; }
          }
          if (data.status === "completed" && dp && typeof dp === "object") {
            console.log("[dispatch poll] revealing with payload:", dp);
            setDispatchPayload(dp);
            setDispatchPhase("revealing");
          } else {
            console.warn(
              `[dispatch poll] no payload to reveal (status=${data.status}, dp_type=${typeof dp}) — returning to idle`,
            );
            setDispatchPhase("idle");
          }
          // Refresh entries list and filter options
          fetchEntries(1, {});
          fetchFilterOptions();
          setPage(1);
          setFilters({});
        }
      } catch (err) {
        console.warn("[dispatch poll] exception:", err);
        /* keep polling */
      }
    }, POLL_INTERVAL_MS);
  }, [fetchEntries, fetchFilterOptions]);

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

      if (onEntrySubmitted) onEntrySubmitted();
      startPolling(entryId);
    } catch {
      setDispatchPhase("idle");
      setToast({ message: "Failed to submit entry. Please try again.", type: "error" });
    }
  };

  return (
    <AnimatedView viewKey="write" isActive={isActive}>
      <div className="write-view">
        <div className="write-wrap minimal">
          <div className="write-mini-head">
            <div className="write-date">{fmtDate(now)}</div>
            <div className="write-weather">
              {fmtTime(now)} &middot; Day {STREAK_COUNT}
            </div>
          </div>

          <h1 className="write-greeting">
            {getGreeting()}, <em>{firstName}</em>.
          </h1>

          <p className="write-nudge">
            What&apos;s been on your mind that you haven&apos;t said out loud?
          </p>

          {/* Composer - always visible */}
          <div className="composer tall">
            <textarea
              ref={taRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Start anywhere..."
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

          {/* Entries list section */}
          <div className="recent-entries-section">
            <div className="entries-section-head">
              <span className="entries-section-label">Your entries</span>
              {totalCount > 0 && (
                <span className="entries-section-count">{totalCount} total</span>
              )}
            </div>

            <EntriesControls
              filters={filters}
              onFiltersChange={handleFiltersChange}
              filterOptions={filterOptions}
              page={page}
              totalCount={totalCount}
              pageSize={PAGE_SIZE}
              onPageChange={handlePageChange}
              onLoadMore={handleLoadMore}
              loadingMore={appendingMore}
            />

            <EntriesList
              entries={entries}
              loading={entriesLoading}
              appended={appendingMore}
            />
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
