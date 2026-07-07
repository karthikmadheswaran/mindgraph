import { useState, useEffect, useCallback, useRef } from "react";
import { AnimatePresence } from "framer-motion";
import { API, authHeaders } from "../utils/auth";
import { daysSinceLastMention, deadlineLabel, deadlineSortValue } from "../utils/dateHelpers";
import {
  getCachedDashboardSnapshot,
  loadDashboardSnapshot,
  subscribeDashboardSnapshot,
  updateDashboardSnapshot,
} from "../utils/dashboardSnapshot";
import AnimatedView from "./AnimatedView";
import DateTimePicker from "./DateTimePicker";
import Toast from "./Toast";
import EntriesControls from "./EntriesControls";
import EntriesList from "./EntriesList";
import { ReflectionGift, buildIntentionCards } from "./InsightCards";
import "../styles/dashboard.css";

// Journal — one scrollable life view (v2, no sub-tabs): On your plate (next
// deadlines + active projects, overflow behind a quiet expander) → Patterns
// (the FULL reflection set; Home shows the capped subset) → Intentions (raw
// rows — the drift card framing stays Home-only) → Entries (reverse-chron
// timeline, infinite scroll only, filters behind one control). Empty sections
// collapse. Witness, not manager: plain dates, no red urgency, no streaks.

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

const PAGE_SIZE = 10;

// "On your plate" shows this many upcoming deadlines; the rest live behind
// the overflow expander together with missed deadlines + hidden projects.
const PLATE_DEADLINES = 3;

function getProjectMeta(project) {
  // "Days quiet" = days since the project was last MENTIONED, via the single
  // canonical accessor (daysSinceLastMention) over last_mentioned_at — which the
  // DB trigger mirrors from entities.last_seen_at.
  const days = daysSinceLastMention(project.last_mentioned_at);
  if (days === null) {
    return { state: "warm", meta: "No recent activity" };
  }
  if (days === 0) return { state: "active", meta: "Active · mentioned today" };
  if (days === 1) return { state: "active", meta: "Active · mentioned yesterday" };
  if (days <= 3) return { state: "active", meta: `Active · ${days} days ago` };
  if (days <= 7) return { state: "warm", meta: "Slow · this week" };
  return { state: "warm", meta: `Stalled · ${days} days quiet` };
}

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

function Journal({ isActive, userId }) {
  const cachedSnapshot = getCachedDashboardSnapshot({ userId });

  // ——— Deadlines + Projects state (relocated from Today, snapshot-backed) ———
  const [allDeadlines, setAllDeadlines] = useState(
    normalizeDeadlines(cachedSnapshot?.deadlines || [])
  );
  const [allProjects, setAllProjects] = useState(
    normalizeProjects(cachedSnapshot?.projects || [])
  );
  const [loadingData, setLoadingData] = useState(!cachedSnapshot);
  const [snapshotReady, setSnapshotReady] = useState(Boolean(cachedSnapshot));
  // One quiet expander for everything beyond the plate: extra upcoming
  // deadlines, the missed group, hidden projects.
  const [overflowOpen, setOverflowOpen] = useState(false);
  const [projectActionState, setProjectActionState] = useState({});
  const [deadlineActionState, setDeadlineActionState] = useState({});
  const [editingDeadlineId, setEditingDeadlineId] = useState(null);
  const [openDeadlineMenuId, setOpenDeadlineMenuId] = useState(null);
  const [openProjectMenuId, setOpenProjectMenuId] = useState(null);
  const [pendingSnooze, setPendingSnooze] = useState(null);
  const [toasts, setToasts] = useState([]);

  // ——— Entries archive state (relocated from the old Write page) ———
  const [entries, setEntries] = useState(null);
  const [totalCount, setTotalCount] = useState(0);
  const [entriesLoading, setEntriesLoading] = useState(false);
  const [appendingMore, setAppendingMore] = useState(false);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({});
  const [filterOptions, setFilterOptions] = useState({ mood: [], person: [], category: [] });

  // ——— Intentions + Patterns state ———
  const [intentionCards, setIntentionCards] = useState(null);
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [reflection, setReflection] = useState(null);

  // ——— Entries timeline state ———
  const [filterOpen, setFilterOpen] = useState(false);

  const hasLoadedRef = useRef(Boolean(cachedSnapshot));
  const refreshTimeoutRef = useRef(null);
  const retryTimeoutRef = useRef(null);
  const deadlineBadgeRefs = useRef({});
  // id -> { deletion, timerId, toastId }. Multiple deletes can be pending at
  // once (per-row undo); single-slot would silently drop a 2nd rapid delete.
  const pendingDeletionsRef = useRef(new Map());
  // intention id -> batch. Same per-id guard for bulk dismiss: a refetch or a
  // rapid second action must never resurrect / double-fire a pending id.
  const pendingIntentionDismissRef = useRef(new Map());
  const toastIdRef = useRef(0);
  const pendingSnoozeRef = useRef(null);
  const pendingSnoozeTimerRef = useRef(null);

  // A row is mid-delete (within its 5s undo window) when its id is in the map.
  // A background snapshot refresh must NOT resurrect any pending row.
  const isPendingDeletion = useCallback((kind, id) => {
    const entry = pendingDeletionsRef.current.get(id);
    return Boolean(entry && entry.deletion.kind === kind);
  }, []);

  const applySnapshot = useCallback(
    (snapshot) => {
      const nextDeadlines = normalizeDeadlines(snapshot.deadlines || []).filter(
        (deadline) => !isPendingDeletion("deadline", deadline.id)
      );
      const nextProjects = normalizeProjects(snapshot.projects || []);
      setAllDeadlines(nextDeadlines);
      setAllProjects(nextProjects);
      setLoadingData(false);
      setSnapshotReady(true);
    },
    [isPendingDeletion]
  );

  // ——— Toast stack: many toasts (delete + snooze + bulk dismiss + errors)
  // coexist, each with its own id so undo/finalize can dismiss exactly one ———
  const dismissToast = useCallback((id) => {
    setToasts((current) => current.filter((item) => item.id !== id));
  }, []);

  const pushToast = useCallback((toast) => {
    toastIdRef.current += 1;
    const id = `toast-${toastIdRef.current}`;
    setToasts((current) => [...current, { ...toast, id }]);
    return id;
  }, []);

  const runSilentRefresh = useCallback(async () => {
    if (!userId) {
      return;
    }

    try {
      await loadDashboardSnapshot({ force: true, userId });
      hasLoadedRef.current = true;
    } catch {
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
          setLoadingData(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [applySnapshot, userId]);

  useEffect(() => {
    if (!snapshotReady) return;

    const interval = setInterval(() => {
      scheduleSilentRefresh(0);
    }, 45000);

    return () => clearInterval(interval);
  }, [scheduleSilentRefresh, snapshotReady]);

  useEffect(() => {
    const pendingDeletions = pendingDeletionsRef.current;
    const pendingDismissals = pendingIntentionDismissRef.current;
    return () => {
      clearTimeout(refreshTimeoutRef.current);
      clearTimeout(retryTimeoutRef.current);
      pendingDeletions.forEach((pending) => clearTimeout(pending.timerId));
      pendingDismissals.forEach((batch) => clearTimeout(batch.timerId));
      clearTimeout(pendingSnoozeTimerRef.current);
    };
  }, []);

  useEffect(() => {
    pendingSnoozeRef.current = pendingSnooze;
  }, [pendingSnooze]);

  // ——— Entries archive (relocated unchanged from the old Write page) ———

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

  const handleFiltersChange = useCallback((newFilters) => {
    setFilters(newFilters);
    setPage(1);
    fetchEntries(1, newFilters);
  }, [fetchEntries]);

  const handleLoadMore = useCallback(() => {
    const nextPage = page + 1;
    setPage(nextPage);
    fetchEntries(nextPage, filters, true);
  }, [fetchEntries, filters, page]);

  // Infinite scroll — the ONLY pagination mechanism. A sentinel below the
  // timeline loads the next page as it approaches the viewport. Callback ref
  // (not an effect) because the sentinel mounts late — after the initial
  // loading gate — and the observer must attach whenever the node appears.
  const entriesRef = useRef({ hasMore: false, busy: false });
  entriesRef.current = {
    hasMore: Boolean(entries) && entries.length < totalCount,
    busy: entriesLoading || appendingMore,
  };
  const loadMoreRef = useRef(handleLoadMore);
  loadMoreRef.current = handleLoadMore;
  const sentinelObserverRef = useRef(null);

  const entriesSentinelRefCb = useCallback((node) => {
    if (sentinelObserverRef.current) {
      sentinelObserverRef.current.disconnect();
      sentinelObserverRef.current = null;
    }
    if (!node || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      (observed) => {
        if (
          observed.some((o) => o.isIntersecting) &&
          entriesRef.current.hasMore &&
          !entriesRef.current.busy
        ) {
          loadMoreRef.current();
        }
      },
      { rootMargin: "400px" }
    );
    io.observe(node);
    sentinelObserverRef.current = io;
  }, []);

  // ——— Deadline + project mutations (relocated unchanged from Today) ———

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

      setDeadlinesState((current) => {
        if (current.some((item) => item.id === deletion.item.id)) {
          return current;
        }

        return sortDeadlines([...current, deletion.item]);
      });
    },
    [setDeadlinesState]
  );

  const finalizePendingDeletion = useCallback(
    async (deletion) => {
      if (!deletion?.item) {
        return;
      }

      const id = deletion.item.id;
      const pending = pendingDeletionsRef.current.get(id);
      if (pending?.timerId) {
        clearTimeout(pending.timerId);
      }
      if (pending?.toastId) {
        dismissToast(pending.toastId);
      }
      pendingDeletionsRef.current.delete(id);

      try {
        await deleteDeadline(id);
      } catch (error) {
        restoreDeletedItem(deletion);
        pushToast({
          message:
            error.message || "Failed to delete deadline. Please try again.",
          type: "error",
        });
      }
    },
    [deleteDeadline, dismissToast, pushToast, restoreDeletedItem]
  );

  const undoPendingDeletion = useCallback(
    (deletion) => {
      if (!deletion?.item) {
        return;
      }

      const id = deletion.item.id;
      const pending = pendingDeletionsRef.current.get(id);
      if (pending?.timerId) {
        clearTimeout(pending.timerId);
      }
      if (pending?.toastId) {
        dismissToast(pending.toastId);
      }
      pendingDeletionsRef.current.delete(id);
      restoreDeletedItem(deletion);
    },
    [dismissToast, restoreDeletedItem]
  );

  const scheduleDelete = useCallback(
    (kind, item) => {
      // Per-id pending state: each rapid delete gets its own optimistic
      // removal, finalize timer, and undo toast. Re-deleting an id already
      // pending is a no-op; a different id is fully independent.
      if (!item || pendingDeletionsRef.current.has(item.id)) {
        return;
      }

      if (kind === "deadline" && editingDeadlineId === item.id) {
        setEditingDeadlineId(null);
      }

      const deletion = { kind, item: normalizeDeadline(item) };

      setDeadlinesState((current) =>
        current.filter((deadline) => deadline.id !== item.id)
      );

      const toastId = pushToast({
        message: "Deadline deleted.",
        type: "success",
        actionLabel: "Undo",
        actionAriaLabel: `Undo deadline delete for ${item.description}`,
        onAction: () => undoPendingDeletion(deletion),
        duration: 5000,
      });

      const timerId = setTimeout(() => {
        finalizePendingDeletion(deletion);
      }, 5000);

      pendingDeletionsRef.current.set(item.id, { deletion, timerId, toastId });
    },
    [
      editingDeadlineId,
      finalizePendingDeletion,
      pushToast,
      setDeadlinesState,
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

        pushToast({
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
    [pushToast, setProgressState, setProjectsState, updateProjectStatus]
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

        pushToast({
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
    [
      editingDeadlineId,
      pushToast,
      setDeadlinesState,
      setProgressState,
      updateDeadlineStatus,
    ]
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
        pushToast({
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
    [closeDeadlinePicker, pushToast, setDeadlinesState, updateDeadlineDate]
  );

  // ——— Snooze (with 5s undo, mirrors scheduleDelete pattern) ———

  const formatDueDateInput = useCallback((date) => {
    const datePart = [
      date.getFullYear(),
      String(date.getMonth() + 1).padStart(2, "0"),
      String(date.getDate()).padStart(2, "0"),
    ].join("-");
    const hh = String(date.getHours()).padStart(2, "0");
    const mm = String(date.getMinutes()).padStart(2, "0");
    return `${datePart}T${hh}:${mm}`;
  }, []);

  const clearPendingSnoozeTimer = useCallback(() => {
    if (pendingSnoozeTimerRef.current) {
      clearTimeout(pendingSnoozeTimerRef.current);
      pendingSnoozeTimerRef.current = null;
    }
  }, []);

  const undoPendingSnooze = useCallback(() => {
    const snooze = pendingSnoozeRef.current;
    if (!snooze) return;
    clearPendingSnoozeTimer();
    pendingSnoozeRef.current = null;
    setDeadlinesState((current) =>
      sortDeadlines(
        current.map((item) =>
          item.id === snooze.deadlineId
            ? { ...item, due_date: snooze.oldDueDate, status: snooze.oldStatus }
            : item
        )
      )
    );
    setPendingSnooze(null);
    if (snooze.toastId) {
      dismissToast(snooze.toastId);
    }
  }, [clearPendingSnoozeTimer, dismissToast, setDeadlinesState]);

  const finalizePendingSnooze = useCallback(
    async (snooze) => {
      if (!snooze) return;
      clearPendingSnoozeTimer();
      pendingSnoozeRef.current = null;
      setPendingSnooze(null);
      if (snooze.toastId) {
        dismissToast(snooze.toastId);
      }
      try {
        const updated = normalizeDeadline(
          await updateDeadlineDate(snooze.deadlineId, snooze.newDueDate)
        );
        setDeadlinesState((current) =>
          sortDeadlines(
            current.map((item) => (item.id === snooze.deadlineId ? updated : item))
          )
        );
      } catch (error) {
        setDeadlinesState((current) =>
          sortDeadlines(
            current.map((item) =>
              item.id === snooze.deadlineId
                ? { ...item, due_date: snooze.oldDueDate, status: snooze.oldStatus }
                : item
            )
          )
        );
        pushToast({
          message: error.message || "Failed to snooze. Please try again.",
          type: "error",
        });
      }
    },
    [
      clearPendingSnoozeTimer,
      dismissToast,
      pushToast,
      setDeadlinesState,
      updateDeadlineDate,
    ]
  );

  const scheduleSnooze = useCallback(
    (deadline, days) => {
      if (pendingSnoozeRef.current) {
        // One snooze at a time — finalize whatever's queued before queueing another.
        finalizePendingSnooze(pendingSnoozeRef.current);
      }
      // Anchor: today for missed, current due_date for upcoming. Otherwise
      // +1d on something 3 weeks overdue stays missed and feels broken.
      const isMissed = deadline.status === "missed";
      const baseDate = isMissed
        ? new Date()
        : (deadline.due_date ? new Date(deadline.due_date) : new Date());
      const target = new Date(baseDate);
      target.setDate(target.getDate() + days);
      const newDueDate = formatDueDateInput(target);

      const snooze = {
        deadlineId: deadline.id,
        oldDueDate: deadline.due_date,
        oldStatus: deadline.status,
        newDueDate,
        days,
      };

      pendingSnoozeRef.current = snooze;
      setPendingSnooze(snooze);
      setOpenDeadlineMenuId(null);

      // Optimistic: update due_date + flip missed -> pending if the new date
      // is in the future (matches backend reconcile behavior).
      setDeadlinesState((current) =>
        sortDeadlines(
          current.map((item) => {
            if (item.id !== deadline.id) return item;
            const nextStatus =
              item.status === "missed" && target > new Date() ? "pending" : item.status;
            return { ...item, due_date: newDueDate, status: nextStatus };
          })
        )
      );

      const label = days === 1 ? "1 day" : days === 7 ? "1 week" : `${days} days`;
      // Snooze stays single-slot logically (pendingSnoozeRef); only its toast
      // joins the shared stack so it coexists with delete/error toasts.
      snooze.toastId = pushToast({
        message: `Snoozed ${label}.`,
        type: "success",
        actionLabel: "Undo",
        actionAriaLabel: `Undo snooze for ${deadline.description}`,
        onAction: undoPendingSnooze,
        duration: 5000,
      });

      pendingSnoozeTimerRef.current = setTimeout(() => {
        finalizePendingSnooze(snooze);
      }, 5000);
    },
    [
      finalizePendingSnooze,
      formatDueDateInput,
      pushToast,
      setDeadlinesState,
      undoPendingSnooze,
    ]
  );

  const toggleDeadlineMenu = useCallback((deadlineId) => {
    setOpenDeadlineMenuId((current) => (current === deadlineId ? null : deadlineId));
  }, []);

  const toggleProjectMenu = useCallback((projectId) => {
    setOpenProjectMenuId((current) => (current === projectId ? null : projectId));
  }, []);

  // ——— Intentions (all pending, days-quiet order — the drift wall as a list) ———

  const isPendingDismiss = useCallback(
    (id) => pendingIntentionDismissRef.current.has(id),
    []
  );

  const refetchIntentions = useCallback(async () => {
    try {
      const headers = await authHeaders();
      const res = await fetch(`${API}/intentions/drift`, { headers });
      if (!res.ok) return;
      const cards = buildIntentionCards(await res.json()).filter(
        // Never resurrect a card that is mid-dismiss (within its undo window).
        (card) => !isPendingDismiss(card.id)
      );
      setIntentionCards(cards);
    } catch {
      /* keep last-known cards on a transient fetch error */
    }
  }, [isPendingDismiss]);

  useEffect(() => {
    if (!isActive) return;
    if (intentionCards === null) {
      refetchIntentions();
    }
    if (reflection === null) {
      const fetchSynthesis = async () => {
        try {
          const headers = await authHeaders();
          const res = await fetch(`${API}/insights/synthesis`, { headers });
          const data = res.ok ? await res.json() : null;
          setReflection(data?.data || null);
        } catch {
          /* Patterns section simply stays collapsed */
        }
      };
      fetchSynthesis();
    }
  }, [isActive, intentionCards, reflection, refetchIntentions]);

  // Persist that the reflection was seen (same contract as Home).
  const handleReflectionReveal = useCallback(async () => {
    try {
      const headers = await authHeaders();
      await fetch(`${API}/insights/synthesis/open`, { method: "POST", headers });
    } catch (err) {
      console.error("reflection open failed", err);
    }
  }, []);

  // Single-card resolve ("Did this") / dismiss — same optimistic remove +
  // re-sync as the Home card.
  const handleIntentionAction = useCallback(
    async (id, action) => {
      if (!id || (action !== "resolve" && action !== "dismiss")) return;
      setIntentionCards((cards) => (cards || []).filter((c) => c.id !== id));
      setSelectedIds((prev) => {
        if (!prev.has(id)) return prev;
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      try {
        const headers = await authHeaders();
        const res = await fetch(`${API}/intentions/${id}/${action}`, { method: "POST", headers });
        if (!res.ok) throw new Error(`${action} failed: ${res.status}`);
        await refetchIntentions();
      } catch (err) {
        console.error("intention action failed", err);
        await refetchIntentions();
      }
    },
    [refetchIntentions]
  );

  const toggleSelected = useCallback((id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const restoreDismissBatch = useCallback((batch) => {
    batch.ids.forEach((id) => pendingIntentionDismissRef.current.delete(id));
    setIntentionCards((cards) => {
      const existing = new Set((cards || []).map((c) => c.id));
      const restored = batch.cards.filter((c) => !existing.has(c.id));
      // Reinsert and restore days-quiet (statN desc) order.
      return [...(cards || []), ...restored].sort(
        (a, b) => Number(b.statN || 0) - Number(a.statN || 0)
      );
    });
  }, []);

  const finalizeDismissBatch = useCallback(
    async (batch) => {
      clearTimeout(batch.timerId);
      dismissToast(batch.toastId);

      const results = await Promise.allSettled(
        batch.ids.map(async (id) => {
          const headers = await authHeaders();
          const res = await fetch(`${API}/intentions/${id}/dismiss`, {
            method: "POST",
            headers,
          });
          if (!res.ok) throw new Error(`dismiss failed: ${res.status}`);
          return id;
        })
      );

      batch.ids.forEach((id) => pendingIntentionDismissRef.current.delete(id));

      const failedIds = batch.ids.filter(
        (_, index) => results[index].status === "rejected"
      );
      if (failedIds.length > 0) {
        const failedCards = batch.cards.filter((c) => failedIds.includes(c.id));
        restoreDismissBatch({ ids: failedIds, cards: failedCards });
        pushToast({
          message: `Failed to dismiss ${failedIds.length} intention${failedIds.length === 1 ? "" : "s"}. Please try again.`,
          type: "error",
        });
      }
    },
    [dismissToast, pushToast, restoreDismissBatch]
  );

  const undoDismissBatch = useCallback(
    (batch) => {
      clearTimeout(batch.timerId);
      dismissToast(batch.toastId);
      restoreDismissBatch(batch);
    },
    [dismissToast, restoreDismissBatch]
  );

  // Bulk dismiss: one batch = one optimistic removal + ONE undo toast + one
  // finalize timer, but every id is tracked in the per-id pending map — so a
  // rapid second batch (or a single-card action) within the 5s window is fully
  // independent and stacks its own toast, mirroring the deadline multi-delete
  // fix. Ids already mid-dismiss are skipped, never double-fired.
  const bulkDismissSelected = useCallback(() => {
    const cards = intentionCards || [];
    const ids = [...selectedIds].filter(
      (id) => !pendingIntentionDismissRef.current.has(id) && cards.some((c) => c.id === id)
    );
    if (ids.length === 0) return;

    const batch = {
      ids,
      cards: cards.filter((c) => ids.includes(c.id)),
    };

    setIntentionCards((current) =>
      (current || []).filter((c) => !ids.includes(c.id))
    );
    setSelectedIds(new Set());
    setSelectMode(false);

    batch.toastId = pushToast({
      message: `Dismissed ${ids.length} intention${ids.length === 1 ? "" : "s"}.`,
      type: "success",
      actionLabel: "Undo",
      actionAriaLabel: `Undo dismissing ${ids.length} intentions`,
      onAction: () => undoDismissBatch(batch),
      duration: 5000,
    });

    batch.timerId = setTimeout(() => {
      finalizeDismissBatch(batch);
    }, 5000);

    ids.forEach((id) => pendingIntentionDismissRef.current.set(id, batch));
  }, [finalizeDismissBatch, intentionCards, pushToast, selectedIds, undoDismissBatch]);

  // ——— Derived collections ———

  const deadlines = allDeadlines.filter((deadline) => deadline.status === "pending");
  const missedDeadlines = allDeadlines
    .filter((deadline) => deadline.status === "missed")
    .sort(
      (left, right) =>
        deadlineSortValue(right.due_date).localeCompare(deadlineSortValue(left.due_date))
    );
  const activeProjects = allProjects.filter((project) => project.status === "active");
  const hiddenProjects = allProjects.filter((project) => project.status === "hidden");

  const activePickerDeadline =
    deadlines.find((deadline) => deadline.id === editingDeadlineId) ||
    missedDeadlines.find((deadline) => deadline.id === editingDeadlineId) ||
    null;

  useEffect(() => {
    if (editingDeadlineId && !activePickerDeadline) {
      setEditingDeadlineId(null);
    }
  }, [activePickerDeadline, editingDeadlineId]);

  // ——— Row renderers (relocated from Today; urgent/red treatment dropped —
  // plain dates only, per the witness-not-manager restructure) ———

  const renderDeadlineRow = (deadline, { missed }) => {
    const dDate = deadline.due_date ? new Date(deadline.due_date) : null;
    const day = dDate ? String(dDate.getDate()).padStart(2, "0") : "?";
    const mon = dDate
      ? dDate.toLocaleString("en-US", { month: "short" }).toUpperCase()
      : "";
    const when = deadlineLabel(deadline.due_date);
    const isUpdating = Boolean(deadlineActionState[deadline.id]);
    const menuOpen = openDeadlineMenuId === deadline.id;
    const rowClass = ["dl", missed ? "dl--missed" : ""].filter(Boolean).join(" ");

    return (
      <div key={deadline.id} className="dl-wrap">
        <div className={rowClass}>
          <div className="dl-date">
            <span className="day">{day}</span>
            <span className="mon">{mon}</span>
          </div>
          <div>
            <div className="dl-title">{deadline.description}</div>
            {missed && <div className="dl-missed-tag">missed</div>}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <div className="dl-when">{when}</div>
            <button
              type="button"
              className={`dl-menu-btn${menuOpen ? " open" : ""}`}
              aria-label={`Actions for ${deadline.description}`}
              aria-expanded={menuOpen}
              ref={(el) => {
                if (el) deadlineBadgeRefs.current[deadline.id] = el;
              }}
              onClick={() => toggleDeadlineMenu(deadline.id)}
            >
              <span aria-hidden="true">⋯</span>
            </button>
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
        {menuOpen && (
          <div className="dl-actions">
            <button
              type="button"
              className="dl-chip"
              onClick={() => scheduleSnooze(deadline, 1)}
            >
              +1 day
            </button>
            <button
              type="button"
              className="dl-chip"
              onClick={() => scheduleSnooze(deadline, 3)}
            >
              +3 days
            </button>
            <button
              type="button"
              className="dl-chip"
              onClick={() => scheduleSnooze(deadline, 7)}
            >
              +1 week
            </button>
            <button
              type="button"
              className="dl-chip dl-chip--ghost"
              onClick={() => {
                setOpenDeadlineMenuId(null);
                toggleDeadlinePicker(deadline.id);
              }}
            >
              Change date
            </button>
            <button
              type="button"
              className="dl-chip dl-chip--danger"
              aria-label={`Delete ${deadline.description}`}
              onClick={() => {
                setOpenDeadlineMenuId(null);
                scheduleDelete("deadline", deadline);
              }}
            >
              Delete
            </button>
          </div>
        )}
      </div>
    );
  };

  const renderProjectRow = (project) => {
    const pm = getProjectMeta(project);
    const menuOpen = openProjectMenuId === project.id;
    const isUpdating = Boolean(projectActionState[project.id]);
    const isHidden = project.status === "hidden";
    const linkedCount = project.mention_count || 0;

    return (
      <div key={project.id} className={`proj-wrap${isHidden ? " proj-wrap--hidden" : ""}`}>
        <div className="proj proj--line">
          <div className="proj-title">
            {project.name}
            {isHidden && <span className="proj-hidden-tag">Hidden</span>}
          </div>
          <div className="proj-meta">
            <span className={`pulse${pm.state === "warm" ? " warm" : ""}`} />
            {pm.meta}
            {linkedCount > 0 && ` · ${linkedCount} ${linkedCount === 1 ? "entry" : "entries"}`}
          </div>
          <button
            type="button"
            className={`dl-menu-btn${menuOpen ? " open" : ""}`}
            aria-label={`Actions for ${project.name}`}
            aria-expanded={menuOpen}
            onClick={() => toggleProjectMenu(project.id)}
          >
            <span aria-hidden="true">⋯</span>
          </button>
        </div>
        {menuOpen && (
          <div className="proj-actions">
            {isHidden ? (
              <button
                type="button"
                className="dl-chip"
                disabled={isUpdating}
                onClick={() => {
                  setOpenProjectMenuId(null);
                  handleProjectStatusChange(project, "active");
                }}
              >
                Restore to active
              </button>
            ) : (
              <button
                type="button"
                className="dl-chip"
                disabled={isUpdating}
                onClick={() => {
                  setOpenProjectMenuId(null);
                  handleProjectStatusChange(project, "hidden");
                }}
              >
                Hide
              </button>
            )}
            <button
              type="button"
              className="dl-chip dl-chip--ghost"
              disabled={isUpdating}
              onClick={() => {
                setOpenProjectMenuId(null);
                handleProjectStatusChange(project, "completed");
              }}
            >
              Mark complete
            </button>
          </div>
        )}
      </div>
    );
  };

  // ——— Sections (empty sections collapse — header included) ———

  const plateDeadlines = deadlines.slice(0, PLATE_DEADLINES);
  const extraDeadlines = deadlines.slice(PLATE_DEADLINES);
  const hasActiveFilter = Object.values(filters).some(Boolean);

  const overflowParts = [];
  if (extraDeadlines.length > 0) overflowParts.push(`${extraDeadlines.length} more`);
  if (missedDeadlines.length > 0) overflowParts.push(`${missedDeadlines.length} past`);
  if (hiddenProjects.length > 0) overflowParts.push(`${hiddenProjects.length} hidden`);

  const showPlate =
    plateDeadlines.length > 0 || activeProjects.length > 0 || overflowParts.length > 0;
  const showPatterns = Boolean(reflection?.synthesis_text);
  const intentions = intentionCards || [];
  const showIntentions = intentions.length > 0;
  const showEntries = entries === null || totalCount > 0 || hasActiveFilter;
  const journalEmpty = !showPlate && !showPatterns && !showIntentions && !showEntries;

  // Raw intention row — same data + actions as the old wall, none of the
  // drift-card framing (pill/prose/stat block); that stays Home-only.
  const renderIntentionRow = (card) => (
    <div key={card.id} className="intent-row">
      {selectMode ? (
        <input
          type="checkbox"
          className="intent-check"
          aria-label={`Select intention: ${card.title}`}
          checked={selectedIds.has(card.id)}
          onChange={() => toggleSelected(card.id)}
        />
      ) : null}
      <span className="intent-text">{card.title}</span>
      <span className="intent-meta">
        {card.statN !== "" ? `${card.statN} days quiet` : "quiet time unknown"}
        {card.status ? ` · ${card.status}` : ""}
      </span>
      {!selectMode && (
        <span className="intent-actions">
          <button
            type="button"
            className="po-foot-btn"
            onClick={() => handleIntentionAction(card.id, "resolve")}
          >
            Did this
          </button>
          <button
            type="button"
            className="po-foot-btn intent-dismiss"
            onClick={() => handleIntentionAction(card.id, "dismiss")}
          >
            Dismiss
          </button>
        </span>
      )}
    </div>
  );

  return (
    <AnimatedView viewKey="journal" isActive={isActive}>
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
        <div className="journal-view">
          {/* ——— On your plate ——— */}
          {showPlate && (
            <section className="journal-section journal-plate">
              <h2>
                On your plate
                {deadlines.length > 0 && (
                  <span className="count">{deadlines.length} open</span>
                )}
              </h2>
              {plateDeadlines.length > 0 && (
                <div className="deadlines">
                  {plateDeadlines.map((deadline) =>
                    renderDeadlineRow(deadline, { missed: false })
                  )}
                </div>
              )}
              {activeProjects.length > 0 && (
                <div className="proj-list">
                  {activeProjects.map((project) => renderProjectRow(project))}
                </div>
              )}
              {overflowParts.length > 0 && (
                <button
                  type="button"
                  className="plate-expander"
                  onClick={() => setOverflowOpen((v) => !v)}
                >
                  {overflowOpen ? "Show less" : overflowParts.join(" · ")}
                </button>
              )}
              {overflowOpen && (
                <div className="plate-overflow">
                  {extraDeadlines.length > 0 && (
                    <div className="deadlines">
                      {extraDeadlines.map((deadline) =>
                        renderDeadlineRow(deadline, { missed: false })
                      )}
                    </div>
                  )}
                  {missedDeadlines.length > 0 && (
                    <>
                      <div className="proj-section-label">Past</div>
                      <div className="deadlines">
                        {missedDeadlines.map((deadline) =>
                          renderDeadlineRow(deadline, { missed: true })
                        )}
                      </div>
                    </>
                  )}
                  {hiddenProjects.length > 0 && (
                    <>
                      <div className="proj-section-label">Hidden</div>
                      <div className="proj-list">
                        {hiddenProjects.map((project) => renderProjectRow(project))}
                      </div>
                    </>
                  )}
                </div>
              )}
            </section>
          )}

          {/* ——— Patterns — the FULL reflection set (Home caps at 3) ——— */}
          {showPatterns && (
            <section className="journal-section journal-patterns">
              <h2>Patterns</h2>
              <ReflectionGift
                bare
                reflection={reflection}
                onReveal={handleReflectionReveal}
              />
            </section>
          )}

          {/* ——— Intentions — raw rows; drift framing stays Home-only ——— */}
          {showIntentions && (
            <section className="journal-section journal-intentions">
              <div className="journal-intent-head">
                <h2>
                  Intentions
                  <span className="count">{intentions.length} pending</span>
                </h2>
                <div className="journal-intent-actions">
                  {selectMode && (
                    <button
                      type="button"
                      className="dl-chip dl-chip--danger"
                      disabled={selectedIds.size === 0}
                      onClick={bulkDismissSelected}
                    >
                      Dismiss {selectedIds.size || ""} selected
                    </button>
                  )}
                  <button
                    type="button"
                    className="dl-chip"
                    onClick={() => {
                      setSelectMode((v) => !v);
                      setSelectedIds(new Set());
                    }}
                  >
                    {selectMode ? "Cancel" : "Select"}
                  </button>
                </div>
              </div>
              <div className="intent-list">{intentions.map(renderIntentionRow)}</div>
            </section>
          )}

          {/* ——— Entries — reverse-chron timeline, infinite scroll only ——— */}
          {showEntries && (
            <section className="journal-section journal-entries">
              <h2>
                Entries
                <span className="count">
                  {totalCount > 0 && <span>{totalCount} total</span>}
                  <button
                    type="button"
                    className={`entries-filter-toggle${hasActiveFilter ? " active" : ""}`}
                    onClick={() => setFilterOpen((v) => !v)}
                  >
                    Filter{hasActiveFilter ? " ●" : ""}
                  </button>
                </span>
              </h2>
              {filterOpen && (
                <EntriesControls
                  filters={filters}
                  onFiltersChange={handleFiltersChange}
                  filterOptions={filterOptions}
                />
              )}
              <EntriesList
                entries={entries}
                loading={entriesLoading}
                appended={appendingMore}
              />
              <div ref={entriesSentinelRefCb} className="entries-sentinel" aria-hidden="true" />
            </section>
          )}

          {journalEmpty && (
            <p className="spread-empty journal-empty">
              Nothing here yet — write your first entry and it all fills in.
            </p>
          )}
        </div>
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

      {toasts.map((toastItem, index) => (
        <Toast
          key={toastItem.id}
          offset={index}
          message={toastItem.message}
          type={toastItem.type || "success"}
          actionLabel={toastItem.actionLabel}
          actionAriaLabel={toastItem.actionAriaLabel}
          onAction={toastItem.onAction}
          duration={toastItem.duration}
          visible
          onDismiss={() => dismissToast(toastItem.id)}
        />
      ))}
    </AnimatedView>
  );
}

export default Journal;
