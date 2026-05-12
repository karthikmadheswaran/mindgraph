import { useState, useEffect } from "react";
import { API, authHeaders } from "../utils/auth";
import "../styles/sidebar.css";

const BAR_COUNT = 14;
const BAR_MAX_PX = 14;
const BAR_MIN_PX = 2;

function getUserTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function scaleBars(buckets) {
  const safe = Array.isArray(buckets) && buckets.length === BAR_COUNT
    ? buckets
    : new Array(BAR_COUNT).fill(0);
  const max = Math.max(...safe, 0);
  if (max === 0) return safe.map(() => BAR_MIN_PX);
  return safe.map((v) => {
    if (v <= 0) return BAR_MIN_PX;
    const scaled = Math.round((v / max) * BAR_MAX_PX);
    return Math.max(BAR_MIN_PX, scaled);
  });
}

const icons = {
  write: (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M4 20h4l10-10-4-4L4 16v4z" />
      <path d="M14 6l4 4" />
    </svg>
  ),
  dashboard: (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  ),
  progress: (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M8 21h8" />
      <path d="M12 17v4" />
      <path d="M7 4h10l-1 5a4 4 0 0 1-4 3 4 4 0 0 1-4-3L7 4Z" />
      <path d="M5 4h14" />
    </svg>
  ),
  ask: (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5A8.48 8.48 0 0 1 21 11v.5z" />
      <path d="M8 10h8" />
      <path d="M8 14h5" />
    </svg>
  ),
  graph: (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="6" cy="7" r="3" />
      <circle cx="17" cy="6" r="3" />
      <circle cx="18" cy="17" r="3" />
      <circle cx="7" cy="18" r="3" />
      <path d="m9 7 5-.5" />
      <path d="m16 9 1.4 5" />
      <path d="m15.5 18-5.5.2" />
      <path d="m7 15 .2-5" />
    </svg>
  ),
};

export default function Sidebar({
  currentView,
  onViewChange,
  userEmail,
  onLogout,
  onBrandClick,
}) {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const userTz = encodeURIComponent(getUserTimezone());
    authHeaders().then((headers) =>
      fetch(`${API}/stats/showed-up?user_tz=${userTz}`, { headers })
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((data) => {
          if (cancelled) return;
          setStats({
            count: Number(data?.count) || 0,
            daily_buckets: Array.isArray(data?.daily_buckets) ? data.daily_buckets : [],
          });
        })
        .catch(() => {
          if (!cancelled) setStats(null);
        })
    );
    return () => {
      cancelled = true;
    };
  }, []);

  // Optimistic update: when an entry is submitted, if today's bucket is still 0,
  // bump it to 1 and increment the all-time count. Listens for a window event
  // dispatched from InputView so we don't have to thread a callback through App.
  useEffect(() => {
    function handleSubmitted() {
      setStats((prev) => {
        if (!prev) return prev;
        const buckets = prev.daily_buckets || [];
        const todayIdx = buckets.length - 1;
        if (todayIdx < 0) return prev;
        if ((buckets[todayIdx] || 0) > 0) return prev;
        const nextBuckets = buckets.slice();
        nextBuckets[todayIdx] = 1;
        return { count: prev.count + 1, daily_buckets: nextBuckets };
      });
    }
    window.addEventListener("mindgraph:entry-submitted", handleSubmitted);
    return () => window.removeEventListener("mindgraph:entry-submitted", handleSubmitted);
  }, []);

  const buckets = stats?.daily_buckets || new Array(BAR_COUNT).fill(0);
  const barHeights = scaleBars(buckets);
  const displayCount = stats === null ? "—" : stats.count;

  const navItems = [
    { id: "write", label: "Write", icon: icons.write },
    { id: "ask", label: "Ask", icon: icons.ask },
    { id: "dashboard", label: "Today", icon: icons.dashboard },
    { id: "graph", label: "Graph", icon: icons.graph },
  ];

  return (
    <>
      <aside className="sidebar">
        <div className="sidebar-top">
          <button
            type="button"
            className="sidebar-brand"
            onClick={onBrandClick}
          >
            <span className="brand-mind">mind</span><span className="brand-graph">graph</span>
          </button>
          <nav className="sidebar-nav" aria-label="Primary">
            {navItems.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`sidebar-nav-item ${
                  currentView === item.id ? "active" : ""
                }`}
                onClick={() => onViewChange(item.id)}
              >
                <span className="sidebar-nav-icon">{item.icon}</span>
                <span className="sidebar-nav-label">{item.label}</span>
              </button>
            ))}
          </nav>
        </div>

        <div className="growth-widget">
          <div className="growth-count">{displayCount}</div>
          <div className="growth-label">times you showed up</div>
          <div className="growth-bars">
            {barHeights.map((h, i) => {
              const isLast = i === barHeights.length - 1;
              const hasActivity = (buckets[i] || 0) > 0;
              const color = isLast ? "#1a1612" : "#b84a2d";
              const opacity = isLast
                ? (hasActivity ? 0.85 : 0.25)
                : (hasActivity ? 0.3 + (h / BAR_MAX_PX) * 0.5 : 0.18);
              return (
                <span
                  key={i}
                  className="growth-bar"
                  style={{ height: h, background: color, opacity }}
                />
              );
            })}
          </div>
        </div>

        <div className="sidebar-bottom">
          <div className="sidebar-email" title={userEmail}>
            {userEmail}
          </div>
          <button type="button" className="sidebar-logout" onClick={onLogout}>
            Log out
          </button>
        </div>
      </aside>

      <nav className="mobile-tabs" aria-label="Mobile navigation">
        {navItems.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`mobile-tab ${currentView === item.id ? "active" : ""}`}
            onClick={() => onViewChange(item.id)}
          >
            <span className="mobile-tab-icon">{item.icon}</span>
            <span className="mobile-tab-label">{item.label}</span>
          </button>
        ))}
      </nav>
    </>
  );
}
