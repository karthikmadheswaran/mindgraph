import { useState, useEffect, useCallback, useRef, Fragment } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { API, authHeaders } from "../utils/auth";
import { deadlineLabel, deadlineSortValue } from "../utils/dateHelpers";
import {
  getCachedDashboardSnapshot,
  loadDashboardSnapshot,
  subscribeDashboardSnapshot,
  updateDashboardSnapshot,
} from "../utils/dashboardSnapshot";
import AnimatedView from "./AnimatedView";
import DateTimePicker from "./DateTimePicker";
import Toast from "./Toast";
import "../styles/dashboard.css";

const normalizeDeadline = (deadline) => ({
  ...deadline,
  status: deadline.status || "pending",
});

const normalizeProject = (project) => ({
  ...project,
  status: project.status || "active",
});

const normalizeDeadlines = (items = []) => items.map(normalizeDeadline);
const normalizeProjects = (items = []) => items.map(normalizeProject);

const formatSyncTime = (timestamp = Date.now()) =>
  new Date(timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

const sortDeadlines = (items) =>
  [...items].sort(
    (left, right) =>
      deadlineSortValue(left.due_date).localeCompare(deadlineSortValue(right.due_date))
  );

const sortProjects = (items) =>
  [...items].sort(
    (left, right) => (right?.mention_count || 0) - (left?.mention_count || 0)
  );

const sortProgressDeadlines = (items) =>
  [...items].sort(
    (left, right) =>
      new Date(right?.status_changed_at || 0).getTime() -
      new Date(left?.status_changed_at || 0).getTime()
  );

const sortProgressProjects = (items) =>
  [...items].sort(
    (left, right) =>
      new Date(right?.status_changed_at || 0).getTime() -
      new Date(left?.status_changed_at || 0).getTime()
  );

const upsertById = (items, item, sorter = (nextItems) => nextItems) =>
  sorter([...items.filter((existingItem) => existingItem.id !== item.id), item]);

// ——— Dashboard design constants ———

const PROGRESS_WIDTHS = [72, 18, 40, 55, 62];

const DAILY_THREADS = [
  {
    q: "You've mentioned the dentist 4 times since January. What's the actual plan?",
    tag: "AVOIDANCE · OPEN SINCE JAN",
  },
  {
    q: "Rafael's tone shifted this week. Want to write about why?",
    tag: "PATTERN · 14 DAYS",
  },
  {
    q: "The Pune trip hasn't moved in 11 days. Book it, or let it go?",
    tag: "STALLED PROJECT",
  },
];

const MOOD_WEATHER = [
  { text: "Mostly reflective this week. Chance of avoidance by Thursday.", dot: "" },
  { text: "High energy Mon–Wed. Things quieted down after that.", dot: "warm" },
  { text: "Lots of planning, less feeling. Due for a heart-forward entry.", dot: "cool" },
];

const MONTH_ABBR = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];

const formatEntryDate = (dateStr) => {
  const d = new Date(dateStr);
  const month = d.toLocaleString("en", { month: "short" });
  const day = d.getDate();
  const time = d.toLocaleString("en", { hour: "numeric", minute: "2-digit", hour12: true });
  return `${month} ${day} · ${time}`;
};
const DAY_FULL = ["SUNDAY","MONDAY","TUESDAY","WEDNESDAY","THURSDAY","FRIDAY","SATURDAY"];

function getProjectMeta(project) {
  if (!project.status_changed_at) {
    return { state: "warm", meta: "No recent activity" };
  }
  const days = Math.floor(
    (Date.now() - new Date(project.status_changed_at).getTime()) / 86400000
  );
  if (days === 0) return { state: "active", meta: "Active · moved today" };
  if (days === 1) return { state: "active", meta: "Active · moved yesterday" };
  if (days <= 3) return { state: "active", meta: `Active · ${days} days ago` };
  if (days <= 7) return { state: "warm", meta: "Slow · once a week" };
  return { state: "warm", meta: `Stalled · ${days} days quiet` };
}

const PO_TYPES = {
  loop:       { label: "Loop detected",     bg: "#faeee4", text: "#b84a2d", accent: "#b84a2d", tintBg: "#fdf6f2" },
  language:   { label: "Language signal",   bg: "#e8f0fa", text: "#7a9ab5", accent: "#7a9ab5", tintBg: "#f5f8fd" },
  avoidance:  { label: "Avoidance signal",  bg: "#e8f2eb", text: "#6b8a6b", accent: "#6b8a6b", tintBg: "#f5faf5" },
  identity:   { label: "Identity gap",      bg: "#f0e8f5", text: "#9a7ab5", accent: "#9a7ab5", tintBg: "#f8f5fd" },
  behavioral: { label: "Behavioral rhythm", bg: "#faeee4", text: "#b84a2d", accent: "#b84a2d", tintBg: "#fdf6f2" },
};

const PATTERN_CARDS_DATA = [
  {
    type: "loop",
    statN: "14×",
    statU: "entries",
    title: "You have a guilt cycle. You're in it more than you think.",
    body: "Loneliness → reach out → smoke → guilt → repeat. The whole cycle is just loneliness with nowhere to go. It surfaces as sudden topic changes and self-criticism spikes — often at night, always on unstructured evenings.",
    cycle: [
      { l: "Lonely", on: false },
      { l: "Reach out", on: false },
      { l: "Smoke", on: false },
      { l: "Restless", on: true },
      { l: "Guilt", on: true },
      { l: "Repeat", on: true },
    ],
    footL: "Detected across 14 entries",
    footR: "Explore this →",
  },
  {
    type: "language",
    statN: "7×",
    statU: "this week",
    title: "You use 'but' to talk yourself out of things you actually want.",
    body: "7 of your last 11 entries contain 'but I don't know if…' or 'but maybe I'm just…' — always immediately after stating something you genuinely want. You're shrinking yourself before anyone else can.",
    quote: "I want to get freelance clients… but maybe I'm not senior enough yet.",
    quoteSrc: "April 14 · Ask Journal",
    footL: "7 instances detected",
    footR: "Show me all →",
  },
  {
    type: "avoidance",
    statN: "3×",
    statU: "since you named it",
    title: "You discovered your uncertainty escape pattern. You're still doing it.",
    body: "When a task requires uncertain thinking, your brain reads it as threat. Phone, Discord, cigarette become exits. You named this on 30 March. You've written about it 3 times since.",
    quote: "Uncertain task → discomfort → phone/Discord/cigarette → relief → guilt → back to task → repeat",
    quoteSrc: "Your own words · 30 March",
    footL: "Still appearing in recent entries",
    footR: "Track progress →",
  },
  {
    type: "identity",
    statN: "9×",
    statU: "entries",
    title: "You describe the version of yourself you want to be as if he's someone else. He's already here.",
    body: "In 9 entries you describe 'Karthik who finishes things, works out, feels proud' as a future person. But in those same entries you shipped MindGraph, fixed real bugs, made real decisions. That version is already showing up.",
    footL: "Across 9 entries",
    footR: "See the evidence →",
  },
  {
    type: "behavioral",
    statN: "2×",
    statU: "on sundays",
    title: "You write most when structure collapses. Sundays are your sharpest.",
    body: "Journal entries cluster on Sundays and late-week evenings — when the week's expectations lift. Your clearest thinking happens when you're not trying.",
    barchart: true,
    footL: "Pattern across 7 weeks",
    footR: "See full chart →",
  },
];

const PO_BAR_HEIGHTS = [5, 14, 6, 8, 9, 7, 18];

function PatternsObservatory() {
  return (
    <div className="patterns-observatory">
      <div className="po-sep" />
      <div className="po-head">
        <span className="po-eyebrow">What your mind is doing</span>
        <span className="po-noticed">Noticed from your entries</span>
      </div>
      <div className="po-sub">Things you wouldn't see without someone reading all of it.</div>
      <motion.div
        className="po-cards"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4 }}
      >
        {PATTERN_CARDS_DATA.map((c, i) => {
          const t = PO_TYPES[c.type];
          return (
            <motion.div
              key={i}
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
                <button type="button" className="po-foot-btn" style={{ color: t.accent }}>
                  {c.footR}
                </button>
              </div>
            </motion.div>
          );
        })}
      </motion.div>
    </div>
  );
}

// ——— Shuffle icon ———
const ShuffleIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polyline points="16 3 21 3 21 8" />
    <line x1="4" y1="20" x2="21" y2="3" />
    <polyline points="21 16 21 21 16 21" />
    <line x1="15" y1="15" x2="21" y2="21" />
  </svg>
);

function Dashboard({ isActive, userId }) {
  const cachedSnapshot = getCachedDashboardSnapshot({ userId });

  const [entries, setEntries] = useState(cachedSnapshot?.entries || []);
  const [allDeadlines, setAllDeadlines] = useState(
    normalizeDeadlines(cachedSnapshot?.deadlines || [])
  );
  const [allProjects, setAllProjects] = useState(
    normalizeProjects(cachedSnapshot?.projects || [])
  );
  const [entities, setEntities] = useState(cachedSnapshot?.entities || []);
  const [relations, setRelations] = useState(cachedSnapshot?.relations || []);
  const [loadingData, setLoadingData] = useState(!cachedSnapshot);
  const [refreshing, setRefreshing] = useState(false);
  const [lastSynced, setLastSynced] = useState(
    cachedSnapshot?.fetchedAt ? formatSyncTime(cachedSnapshot.fetchedAt) : ""
  );
  const [hasActivated, setHasActivated] = useState(isActive);
  const [snapshotReady, setSnapshotReady] = useState(Boolean(cachedSnapshot));
  const [showHidden, setShowHidden] = useState(false);
  const [showSnoozed, setShowSnoozed] = useState(false);
  const [projectActionState, setProjectActionState] = useState({});
  const [deadlineActionState, setDeadlineActionState] = useState({});
  const [editingDeadlineId, setEditingDeadlineId] = useState(null);
  const [pendingDeletion, setPendingDeletion] = useState(null);
  const [toast, setToast] = useState(null);
  const [shuffleKey, setShuffleKey] = useState(0);
  const [shuffling, setShuffling] = useState(false);
  const [noticedInsight, setNoticedInsight] = useState(null);

  const hasLoadedRef = useRef(Boolean(cachedSnapshot));
  const refreshTimeoutRef = useRef(null);
  const retryTimeoutRef = useRef(null);
  const deadlineBadgeRefs = useRef({});
  const pendingDeletionRef = useRef(null);
  const pendingDeletionTimerRef = useRef(null);

  const applySnapshot = useCallback((snapshot) => {
    const activePendingDeletion = pendingDeletionRef.current;
    const nextDeadlines = normalizeDeadlines(snapshot.deadlines || []).filter(
      (deadline) =>
        !(
          activePendingDeletion?.kind === "deadline" &&
          activePendingDeletion.item.id === deadline.id
        )
    );
    const nextProjects = normalizeProjects(snapshot.projects || []).filter(
      (project) =>
        !(
          activePendingDeletion?.kind === "project" &&
          activePendingDeletion.item.id === project.id
        )
    );

    const nextEntries = (snapshot.entries || []).filter(
      (entry) =>
        !(
          activePendingDeletion?.kind === "entry" &&
          activePendingDeletion.item.id === entry.id
        )
    );
    setEntries(nextEntries);
    setAllDeadlines(nextDeadlines);
    setAllProjects(nextProjects);
    setEntities(snapshot.entities || []);
    setRelations(snapshot.relations || []);
    setLoadingData(false);
    setRefreshing(false);
    setSnapshotReady(true);
    setLastSynced(formatSyncTime(snapshot.fetchedAt));
  }, []);

  useEffect(() => {
    pendingDeletionRef.current = pendingDeletion;
  }, [pendingDeletion]);

  const fetchEntries = useCallback(async () => {
    const headers = await authHeaders();
    return fetch(`${API}/entries`, { headers }).then((r) => r.json());
  }, []);

  const runSilentRefresh = useCallback(async () => {
    if (!userId) {
      return;
    }

    try {
      await loadDashboardSnapshot({ force: true, userId });
      hasLoadedRef.current = true;
    } catch {
      setRefreshing(false);
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = setTimeout(() => {
        runSilentRefresh();
      }, 1500);
    }
  }, [userId]);

  const scheduleSilentRefresh = useCallback(
    (delay = 500) => {
      clearTimeout(refreshTimeoutRef.current);
      refreshTimeoutRef.current = setTimeout(() => {
        runSilentRefresh();
      }, delay);
    },
    [runSilentRefresh]
  );

  useEffect(() => {
    if (!userId) {
      return undefined;
    }

    return subscribeDashboardSnapshot((snapshot) => {
      if (!snapshot) {
        return;
      }

      hasLoadedRef.current = true;
      applySnapshot(snapshot);
    });
  }, [applySnapshot, userId]);

  useEffect(() => {
    if (!userId || hasLoadedRef.current) {
      return undefined;
    }

    let cancelled = false;
    setLoadingData(true);

    loadDashboardSnapshot({ userId })
      .then((snapshot) => {
        if (cancelled || hasLoadedRef.current || !snapshot) {
          return;
        }

        hasLoadedRef.current = true;
        applySnapshot(snapshot);
      })
      .catch(() => {
        if (!cancelled) {
          setRefreshing(false);
          setLoadingData(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [applySnapshot, userId]);

  useEffect(() => {
    if (isActive && !hasActivated) {
      setHasActivated(true);
    }
  }, [isActive, hasActivated]);

  useEffect(() => {
    if (!snapshotReady) return;

    const interval = setInterval(() => {
      scheduleSilentRefresh(0);
    }, 45000);

    return () => clearInterval(interval);
  }, [scheduleSilentRefresh, snapshotReady]);

  useEffect(() => {
    if (!entries.some((entry) => entry.status === "processing")) return;

    const interval = setInterval(async () => {
      try {
        const data = await fetchEntries();
        const nextEntries = data.entries || [];

        setEntries(nextEntries);
        updateDashboardSnapshot(
          (snapshot) =>
            snapshot
              ? {
                  ...snapshot,
                  entries: nextEntries,
                }
              : snapshot,
          { userId }
        );

        if (!nextEntries.some((entry) => entry.status === "processing")) {
          clearInterval(interval);
          scheduleSilentRefresh(0);
        }
      } catch {
        // silently fail
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [entries, fetchEntries, scheduleSilentRefresh, userId]);

  useEffect(() => {
    return () => {
      clearTimeout(refreshTimeoutRef.current);
      clearTimeout(retryTimeoutRef.current);
      clearTimeout(pendingDeletionTimerRef.current);
    };
  }, []);

  const updateDeadlineStatus = useCallback(async (deadlineId, newStatus) => {
    const headers = await authHeaders();
    const response = await fetch(`${API}/deadlines/${deadlineId}/status`, {
      method: "PATCH",
      headers,
      body: JSON.stringify({ status: newStatus }),
    });

    if (response.status === 401) {
      throw new Error("Session expired. Please log in again.");
    }

    if (!response.ok) {
      throw new Error("Failed to update deadline. Please try again.");
    }

    return response.json();
  }, []);

  const updateDeadlineDate = useCallback(async (deadlineId, dueDate) => {
    const headers = await authHeaders();
    const response = await fetch(`${API}/deadlines/${deadlineId}/date`, {
      method: "PATCH",
      headers,
      body: JSON.stringify({ due_date: dueDate }),
    });

    if (response.status === 401) {
      throw new Error("Session expired. Please log in again.");
    }

    if (!response.ok) {
      throw new Error("Failed to update deadline date. Please try again.");
    }

    return response.json();
  }, []);

  const updateProjectStatus = useCallback(async (projectId, newStatus) => {
    const headers = await authHeaders();
    const response = await fetch(`${API}/projects/${projectId}/status`, {
      method: "PATCH",
      headers,
      body: JSON.stringify({ status: newStatus }),
    });

    if (response.status === 401) {
      throw new Error("Session expired. Please log in again.");
    }

    if (!response.ok) {
      throw new Error("Failed to update project. Please try again.");
    }

    return response.json();
  }, []);

  const deleteEntry = useCallback(async (entryId) => {
    const headers = await authHeaders();
    const response = await fetch(`${API}/entries/${entryId}`, {
      method: "DELETE",
      headers,
    });

    if (response.status === 401) {
      throw new Error("Session expired. Please log in again.");
    }

    if (!response.ok) {
      throw new Error("Failed to delete entry. Please try again.");
    }

    return response.json();
  }, []);

  const deleteDeadline = useCallback(async (deadlineId) => {
    const headers = await authHeaders();
    const response = await fetch(`${API}/deadlines/${deadlineId}`, {
      method: "DELETE",
      headers,
    });

    if (response.status === 401) {
      throw new Error("Session expired. Please log in again.");
    }

    if (!response.ok) {
      throw new Error("Failed to delete deadline. Please try again.");
    }

    return response.json();
  }, []);

  const deleteProject = useCallback(async (projectId) => {
    const headers = await authHeaders();
    const response = await fetch(`${API}/projects/${projectId}`, {
      method: "DELETE",
      headers,
    });

    if (response.status === 401) {
      throw new Error("Session expired. Please log in again.");
    }

    if (!response.ok) {
      throw new Error("Failed to delete project. Please try again.");
    }

    return response.json();
  }, []);

  const setProjectsState = useCallback(
    (updater) => {
      setAllProjects((current) => {
        const nextProjects =
          typeof updater === "function" ? updater(current) : updater;

        updateDashboardSnapshot(
          (snapshot) =>
            snapshot
              ? {
                  ...snapshot,
                  projects: nextProjects,
                }
              : snapshot,
          { userId }
        );

        return nextProjects;
      });
    },
    [userId]
  );

  const setEntriesState = useCallback(
    (updater) => {
      setEntries((current) => {
        const nextEntries =
          typeof updater === "function" ? updater(current) : updater;

        updateDashboardSnapshot(
          (snapshot) =>
            snapshot
              ? {
                  ...snapshot,
                  entries: nextEntries,
                }
              : snapshot,
          { userId }
        );

        return nextEntries;
      });
    },
    [userId]
  );

  const setDeadlinesState = useCallback(
    (updater) => {
      setAllDeadlines((current) => {
        const nextDeadlines =
          typeof updater === "function" ? updater(current) : updater;

        updateDashboardSnapshot(
          (snapshot) =>
            snapshot
              ? {
                  ...snapshot,
                  deadlines: nextDeadlines,
                }
              : snapshot,
          { userId }
        );

        return nextDeadlines;
      });
    },
    [userId]
  );

  const setProgressState = useCallback(
    (updater) => {
      updateDashboardSnapshot(
        (snapshot) => {
          if (!snapshot) {
            return snapshot;
          }

          const nextProgress =
            typeof updater === "function" ? updater(snapshot.progress) : updater;

          if (!nextProgress) {
            return snapshot;
          }

          return {
            ...snapshot,
            progress: nextProgress,
          };
        },
        { userId }
      );
    },
    [userId]
  );

  const restoreDeletedItem = useCallback(
    (deletion) => {
      if (!deletion?.item) {
        return;
      }

      if (deletion.kind === "entry") {
        setEntriesState((current) => {
          if (current.some((item) => item.id === deletion.item.id)) {
            return current;
          }

          return [...current, deletion.item].sort(
            (a, b) => new Date(b.created_at) - new Date(a.created_at)
          );
        });
        return;
      }

      if (deletion.kind === "deadline") {
        setDeadlinesState((current) => {
          if (current.some((item) => item.id === deletion.item.id)) {
            return current;
          }

          return sortDeadlines([...current, deletion.item]);
        });
        return;
      }

      setProjectsState((current) => {
        if (current.some((item) => item.id === deletion.item.id)) {
          return current;
        }

        return sortProjects([...current, deletion.item]);
      });
    },
    [setDeadlinesState, setEntriesState, setProjectsState]
  );

  const clearPendingDeleteTimer = useCallback(() => {
    if (pendingDeletionTimerRef.current) {
      clearTimeout(pendingDeletionTimerRef.current);
      pendingDeletionTimerRef.current = null;
    }
  }, []);

  const finalizePendingDeletion = useCallback(
    async (deletion) => {
      if (!deletion?.item) {
        return;
      }

      clearPendingDeleteTimer();
      pendingDeletionRef.current = null;
      setPendingDeletion(null);
      setToast(null);

      try {
        if (deletion.kind === "entry") {
          await deleteEntry(deletion.item.id);
        } else if (deletion.kind === "deadline") {
          await deleteDeadline(deletion.item.id);
        } else {
          await deleteProject(deletion.item.id);
        }
      } catch (error) {
        restoreDeletedItem(deletion);
        setToast({
          message:
            error.message ||
            `Failed to delete ${deletion.kind}. Please try again.`,
          type: "error",
        });
      }
    },
    [
      clearPendingDeleteTimer,
      deleteDeadline,
      deleteEntry,
      deleteProject,
      restoreDeletedItem,
    ]
  );

  const undoPendingDeletion = useCallback(() => {
    const deletion = pendingDeletionRef.current;
    if (!deletion?.item) {
      return;
    }

    clearPendingDeleteTimer();
    pendingDeletionRef.current = null;
    restoreDeletedItem(deletion);
    setPendingDeletion(null);
    setToast(null);
  }, [clearPendingDeleteTimer, restoreDeletedItem]);

  const scheduleDelete = useCallback(
    (kind, item) => {
      if (!item || pendingDeletionRef.current) {
        return;
      }

      if (kind === "deadline" && editingDeadlineId === item.id) {
        setEditingDeadlineId(null);
      }

      let normalizedItem;
      if (kind === "entry") {
        normalizedItem = item;
      } else if (kind === "deadline") {
        normalizedItem = normalizeDeadline(item);
      } else {
        normalizedItem = normalizeProject(item);
      }

      const deletion = { kind, item: normalizedItem };

      pendingDeletionRef.current = deletion;

      if (kind === "entry") {
        setEntriesState((current) =>
          current.filter((entry) => entry.id !== item.id)
        );
      } else if (kind === "deadline") {
        setDeadlinesState((current) =>
          current.filter((deadline) => deadline.id !== item.id)
        );
      } else {
        setProjectsState((current) =>
          current.filter((project) => project.id !== item.id)
        );
      }

      let message;
      let actionAriaLabel;
      if (kind === "entry") {
        message = "Entry deleted.";
        actionAriaLabel = `Undo entry delete for ${
          item.auto_title || "journal entry"
        }`;
      } else if (kind === "deadline") {
        message = "Deadline deleted.";
        actionAriaLabel = `Undo deadline delete for ${item.description}`;
      } else {
        message = "Project deleted.";
        actionAriaLabel = `Undo project delete for ${item.name}`;
      }

      setPendingDeletion(deletion);
      setToast({
        message,
        type: "success",
        actionLabel: "Undo",
        actionAriaLabel,
        onAction: undoPendingDeletion,
        duration: 5000,
      });

      pendingDeletionTimerRef.current = setTimeout(() => {
        finalizePendingDeletion(deletion);
      }, 5000);
    },
    [
      editingDeadlineId,
      finalizePendingDeletion,
      setDeadlinesState,
      setEntriesState,
      setProjectsState,
      undoPendingDeletion,
    ]
  );

  const handleProjectStatusChange = useCallback(
    async (project, nextStatus) => {
      const isTerminalStatus = nextStatus === "completed";
      const normalizedProject = normalizeProject(project);
      const optimisticProject = isTerminalStatus
        ? normalizeProject({
            ...normalizedProject,
            status: nextStatus,
            status_changed_at: new Date().toISOString(),
          })
        : null;

      setProjectActionState((current) => ({
        ...current,
        [project.id]: true,
      }));

      if (isTerminalStatus) {
        setProjectsState((current) =>
          current.filter((item) => item.id !== project.id)
        );
        setProgressState((current) => ({
          ...current,
          projects: upsertById(
            current.projects,
            optimisticProject,
            sortProgressProjects
          ),
        }));
      } else {
        setProjectsState((current) =>
          current.map((item) =>
            item.id === project.id ? { ...item, status: nextStatus } : item
          )
        );
      }

      try {
        const updatedProject = normalizeProject(
          await updateProjectStatus(project.id, nextStatus)
        );

        if (isTerminalStatus) {
          setProgressState((current) => ({
            ...current,
            projects: upsertById(
              current.projects,
              updatedProject,
              sortProgressProjects
            ),
          }));
        } else {
          setProjectsState((current) =>
            current.map((item) =>
              item.id === project.id ? updatedProject : item
            )
          );
        }
      } catch (error) {
        if (isTerminalStatus) {
          setProjectsState((current) => {
            if (current.some((item) => item.id === project.id)) {
              return current;
            }

            return sortProjects([...current, normalizedProject]);
          });
          setProgressState((current) => ({
            ...current,
            projects: current.projects.filter((item) => item.id !== project.id),
          }));
        } else {
          setProjectsState((current) =>
            current.map((item) =>
              item.id === project.id ? normalizedProject : item
            )
          );
        }

        setToast({
          message: error.message || "Failed to update project. Please try again.",
          type: "error",
        });
      } finally {
        setProjectActionState((current) => {
          const next = { ...current };
          delete next[project.id];
          return next;
        });
      }
    },
    [setProgressState, setProjectsState, updateProjectStatus]
  );

  const handleDeadlineStatusChange = useCallback(
    async (deadline, nextStatus) => {
      const isTerminalStatus = nextStatus === "done";
      const normalizedDeadline = normalizeDeadline(deadline);
      const optimisticDeadline = isTerminalStatus
        ? normalizeDeadline({
            ...normalizedDeadline,
            status: nextStatus,
            status_changed_at: new Date().toISOString(),
          })
        : null;

      if (editingDeadlineId === deadline.id) {
        setEditingDeadlineId(null);
      }

      setDeadlineActionState((current) => ({
        ...current,
        [deadline.id]: true,
      }));

      if (isTerminalStatus) {
        setDeadlinesState((current) =>
          current.filter((item) => item.id !== deadline.id)
        );
        setProgressState((current) => ({
          ...current,
          deadlines: upsertById(
            current.deadlines,
            optimisticDeadline,
            sortProgressDeadlines
          ),
        }));
      } else {
        setDeadlinesState((current) =>
          current.map((item) =>
            item.id === deadline.id ? { ...item, status: nextStatus } : item
          )
        );
      }

      try {
        const updatedDeadline = normalizeDeadline(
          await updateDeadlineStatus(deadline.id, nextStatus)
        );

        if (isTerminalStatus) {
          setProgressState((current) => ({
            ...current,
            deadlines: upsertById(
              current.deadlines,
              updatedDeadline,
              sortProgressDeadlines
            ),
          }));
        } else {
          setDeadlinesState((current) =>
            current.map((item) =>
              item.id === deadline.id ? updatedDeadline : item
            )
          );
        }
      } catch (error) {
        if (isTerminalStatus) {
          setDeadlinesState((current) => {
            if (current.some((item) => item.id === deadline.id)) {
              return current;
            }

            return sortDeadlines([...current, normalizedDeadline]);
          });
          setProgressState((current) => ({
            ...current,
            deadlines: current.deadlines.filter(
              (item) => item.id !== deadline.id
            ),
          }));
        } else {
          setDeadlinesState((current) =>
            current.map((item) =>
              item.id === deadline.id ? normalizedDeadline : item
            )
          );
        }

        setToast({
          message: error.message || "Failed to update deadline. Please try again.",
          type: "error",
        });
      } finally {
        setDeadlineActionState((current) => {
          const next = { ...current };
          delete next[deadline.id];
          return next;
        });
      }
    },
    [editingDeadlineId, setDeadlinesState, setProgressState, updateDeadlineStatus]
  );

  const closeDeadlinePicker = useCallback((deadlineId = null) => {
    setEditingDeadlineId((current) =>
      deadlineId === null || current === deadlineId ? null : current
    );
  }, []);

  const toggleDeadlinePicker = useCallback((deadlineId) => {
    setEditingDeadlineId((current) =>
      current === deadlineId ? null : deadlineId
    );
  }, []);

  const handleDeadlineDateSave = useCallback(
    async (deadline, nextDueDate) => {
      const normalizedDeadline = normalizeDeadline(deadline);

      setDeadlineActionState((current) => ({
        ...current,
        [deadline.id]: true,
      }));

      closeDeadlinePicker(deadline.id);

      setDeadlinesState((current) =>
        sortDeadlines(
          current.map((item) =>
            item.id === deadline.id ? { ...item, due_date: nextDueDate } : item
          )
        )
      );

      try {
        const updatedDeadline = normalizeDeadline(
          await updateDeadlineDate(deadline.id, nextDueDate)
        );

        setDeadlinesState((current) =>
          sortDeadlines(
            current.map((item) =>
              item.id === deadline.id ? updatedDeadline : item
            )
          )
        );
      } catch (error) {
        setDeadlinesState((current) =>
          sortDeadlines(
            current.map((item) =>
              item.id === deadline.id ? normalizedDeadline : item
            )
          )
        );
        setToast({
          message:
            error.message || "Failed to update deadline date. Please try again.",
          type: "error",
        });
      } finally {
        setDeadlineActionState((current) => {
          const next = { ...current };
          delete next[deadline.id];
          return next;
        });
      }
    },
    [closeDeadlinePicker, setDeadlinesState, updateDeadlineDate]
  );

  // Fetch insights for Noticed card when view becomes active
  useEffect(() => {
    if (!isActive) return;
    const fetchInsights = async () => {
      try {
        const headers = await authHeaders();
        const [insightsRes, patternsRes] = await Promise.all([
          fetch(`${API}/insights`, { headers }),
          fetch(`${API}/insights/patterns`, { headers }),
        ]);
        const insightsData = insightsRes.ok ? await insightsRes.json() : null;
        const patternsData = patternsRes.ok ? await patternsRes.json() : null;

        console.log("RAW insights response:", JSON.stringify(insightsData, null, 2));
        console.log("RAW patterns response:", JSON.stringify(patternsData, null, 2));

        const TYPE_LABELS = {
          tool:    "FORGOTTEN TOOL",
          person:  "QUIET CONNECTION",
          project: "STALLED PROJECT",
          task:    "OPEN TASK",
        };

        // Actual shape (confirmed from console):
        // /insights/patterns → { status, data: { repeated_themes, shiny_objects, ... } } — no stale data
        // /insights          → { insights: [{ insight_type: "forgotten_projects", content: JSON_STRING, ... }] }
        //   insight.content is a JSON string: { stale: [...], active: [...], stale_count, active_count }
        //   Must JSON.parse(insight.content) to get the stale array.

        const forgottenInsight = insightsData?.insights?.find(
          (i) => i.insight_type === "forgotten_projects"
        );
        let parsedContent = null;
        try { parsedContent = forgottenInsight ? JSON.parse(forgottenInsight.content) : null; } catch { /* malformed */ }

        const stale = Array.isArray(parsedContent?.stale) ? parsedContent.stale : [];
        const item = [...stale].sort(
          (a, b) => (b.mention_count || 0) - (a.mention_count || 0)
        )[0] || null;

        if (item) {
          const typeLabel = TYPE_LABELS[item.type] || "PATTERN";
          const dateTag = `QUIET FOR ${item.days_since_mention} DAYS`;
          const cardText = `${item.name} hasn't come up in ${item.days_since_mention} days. ${item.context || ""}`.trim();
          setNoticedInsight({
            category: typeLabel,
            dateTag,
            content: cardText,
            hasActions: true,
          });
        } else {
          setNoticedInsight({
            category: "PATTERN",
            content: "No patterns detected yet. Keep journaling.",
            hasActions: false,
          });
        }
      } catch {
        // keep null — fallback shown in JSX
      }
    };
    fetchInsights();
  }, [isActive]);

  const deadlines = showSnoozed
    ? allDeadlines
    : allDeadlines.filter((deadline) => deadline.status === "pending");
  const projects = showHidden
    ? allProjects
    : allProjects.filter((project) => project.status === "active");

  const activePickerDeadline =
    deadlines.find((deadline) => deadline.id === editingDeadlineId) || null;

  useEffect(() => {
    if (editingDeadlineId && !activePickerDeadline) {
      setEditingDeadlineId(null);
    }
  }, [activePickerDeadline, editingDeadlineId]);

  // ——— Computed display values ———
  const now = new Date();
  const formattedDate = `${DAY_FULL[now.getDay()]}, ${MONTH_ABBR[now.getMonth()]} ${now.getDate()}`;
  const weekStart = new Date(now);
  weekStart.setDate(weekStart.getDate() - weekStart.getDay());
  weekStart.setHours(0, 0, 0, 0);
  const entriesThisWeek = entries.filter((e) => new Date(e.created_at) >= weekStart).length;
  const currentThread = DAILY_THREADS[shuffleKey % DAILY_THREADS.length];
  const currentWeather = MOOD_WEATHER[shuffleKey % MOOD_WEATHER.length];
  const handleShuffle = () => {
    setShuffling(true);
    setTimeout(() => { setShuffleKey((k) => k + 1); setShuffling(false); }, 400);
  };

  return (
    <AnimatedView viewKey="dashboard" isActive={isActive}>
      {loadingData ? (
        <div
          style={{
            textAlign: "center",
            padding: 40,
            color: "var(--text-muted)",
          }}
        >
          <span className="spinner" />
          <p style={{ marginTop: 12 }}>Loading your journal...</p>
        </div>
      ) : (
        <>
        <div className="spread">

          {/* ——— LEFT COLUMN ——— */}
          <div key={"l" + shuffleKey} className={`spread-col${shuffling ? " shuffling" : ""}`}>

            {/* Masthead */}
            <div className="spread-masthead">
              <h1>The <em>Daily</em> Mind</h1>
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <div className="issue">VOL. {loadingData ? "—" : entries.length} · {formattedDate}</div>
                <button
                  type="button"
                  className={`shuffle-btn${shuffling ? " spinning" : ""}`}
                  onClick={handleShuffle}
                >
                  <ShuffleIcon /> Shuffle
                </button>
              </div>
            </div>

            {/* Mood weather */}
            <p className="weather-line" style={{ marginTop: "-10px", marginBottom: "6px" }}>
              {currentWeather.text}
            </p>

            {/* Stats ticker */}
            <div className="ticker">
              <div className="tick">
                <div className="tick-n">{entriesThisWeek}</div>
                <div className="tick-l">entries this week</div>
              </div>
              <div className="tick">
                <div className="tick-n">
                  {projects.length}<em>+2</em>
                </div>
                <div className="tick-l">active projects</div>
              </div>
              <div className="tick">
                <div className="tick-n">{entities.length}</div>
                <div className="tick-l">entities tracked</div>
              </div>
            </div>

            {/*
              // GET /insights returned: checked in console.log above
              // GET /insights/patterns returned: checked in console.log above
              // noticedInsight uses: .type/.category (tag), .content/.description (body), .created_at (month), .title
            */}
            {/* MindGraph Noticed / Daily Thread */}
            <div className="dthread">
              {noticedInsight ? (
                <>
                  <div className="dthread-kicker">
                    <span className="pulse-sm" />
                    MINDGRAPH NOTICED ·{" "}
                    {(noticedInsight.category || noticedInsight.type || "PATTERN").toUpperCase()}
                    {noticedInsight.dateTag
                      ? ` · ${noticedInsight.dateTag}`
                      : noticedInsight.created_at
                      ? ` · OPEN SINCE ${new Date(noticedInsight.created_at).toLocaleString("en", { month: "short" }).toUpperCase()}`
                      : ""}
                  </div>
                  {noticedInsight.title && (
                    <div className="dthread-q">{noticedInsight.title}</div>
                  )}
                  <div className="dthread-q" style={noticedInsight.title ? { fontSize: "16px", marginTop: "-6px" } : undefined}>
                    {noticedInsight.content || noticedInsight.description}
                  </div>
                  {noticedInsight.hasActions !== false && (
                    <div className="dthread-actions">
                      <button type="button" className="dthread-btn primary">Answer now</button>
                      <button type="button" className="dthread-btn">Snooze</button>
                      <button type="button" className="dthread-btn">Not now</button>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <div className="dthread-kicker">
                    <span className="pulse-sm" />
                    MINDGRAPH NOTICED · {currentThread.tag}
                  </div>
                  <div className="dthread-q">{currentThread.q}</div>
                  <div className="dthread-actions">
                    <button type="button" className="dthread-btn primary">Answer now</button>
                    <button type="button" className="dthread-btn">Snooze</button>
                    <button type="button" className="dthread-btn">Not now</button>
                  </div>
                </>
              )}
            </div>

          </div>

          {/* ——— RIGHT COLUMN ——— */}
          <div key={"r" + shuffleKey} className={`spread-col${shuffling ? " shuffling" : ""}`}>

            {/* Active Projects */}
            <div>
              <h2>
                Active Projects
                <span className="count">{projects.length} TRACKED</span>
              </h2>
              <div className="proj-list">
                {projects.length === 0 ? (
                  <p className="spread-empty">
                    No active projects. Write about something you're working on.
                  </p>
                ) : (
                  projects.slice(0, 5).map((project, idx) => {
                    const pm = getProjectMeta(project);
                    return (
                      <div key={project.id} className="proj">
                        <div>
                          <div className="proj-title">{project.name}</div>
                          <div className="proj-meta">
                            <span className={`pulse${pm.state === "warm" ? " warm" : ""}`} />
                            {pm.meta}
                          </div>
                        </div>
                        <div className="proj-bar">
                          <span
                            style={{
                              width: `${PROGRESS_WIDTHS[idx % PROGRESS_WIDTHS.length]}%`,
                            }}
                          />
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            <hr style={{ border: "none", borderTop: "1px solid rgba(26,22,18,0.06)", margin: "0" }} />

            {/* Upcoming Deadlines */}
            <div>
              <h2>
                Upcoming Deadlines
                <span className="count">{formattedDate}</span>
              </h2>
              {deadlines.length === 0 ? (
                <p className="spread-empty">
                  No upcoming deadlines. Mention a due date in your next entry.
                </p>
              ) : (
                <div className="deadlines">
                  {deadlines.slice(0, 4).map((deadline) => {
                    const dDate = deadline.due_date ? new Date(deadline.due_date) : null;
                    const isUrgent =
                      dDate && dDate - now < 2 * 24 * 60 * 60 * 1000 && dDate > now;
                    const day = dDate
                      ? String(dDate.getDate()).padStart(2, "0")
                      : "?";
                    const mon = dDate
                      ? dDate.toLocaleString("en-US", { month: "short" }).toUpperCase()
                      : "";
                    const when = deadlineLabel(deadline.due_date);
                    const isUpdating = Boolean(deadlineActionState[deadline.id]);

                    return (
                      <div key={deadline.id} className={`dl${isUrgent ? " urgent" : ""}`}>
                        <div className="dl-date">
                          <span className="day">{day}</span>
                          <span className="mon">{mon}</span>
                        </div>
                        <div>
                          <div className="dl-title">{deadline.description}</div>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <div className="dl-when">{when}</div>
                          <button
                            type="button"
                            className="dl-done-btn"
                            aria-label={`Mark done: ${deadline.description}`}
                            disabled={isUpdating}
                            onClick={() => handleDeadlineStatusChange(deadline, "done")}
                          >
                            ✓
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>


          </div>
        </div>

        {/* ——— Patterns Observatory — full width below both columns ——— */}
        <div className="spread-full" style={{ marginTop: "2rem" }}>
          <PatternsObservatory />
        </div>

        </>
      )}

      <AnimatePresence>
        {activePickerDeadline && (
          <DateTimePicker
            currentDate={activePickerDeadline.due_date}
            anchorRef={{
              current: deadlineBadgeRefs.current[activePickerDeadline.id] || null,
            }}
            onCancel={() => closeDeadlinePicker(activePickerDeadline.id)}
            onSave={(nextDueDate) =>
              handleDeadlineDateSave(activePickerDeadline, nextDueDate)
            }
          />
        )}
      </AnimatePresence>

      <Toast
        message={toast?.message}
        type={toast?.type || "success"}
        actionLabel={toast?.actionLabel}
        actionAriaLabel={toast?.actionAriaLabel}
        onAction={toast?.onAction}
        duration={toast?.duration}
        visible={!!toast}
        onDismiss={() => setToast(null)}
      />
    </AnimatedView>
  );
}

export default Dashboard;
