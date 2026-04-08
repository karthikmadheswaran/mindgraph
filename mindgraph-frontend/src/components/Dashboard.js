import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { API, authHeaders } from "../utils/auth";
import { entityColors, nodeLabels, pipelineOrder } from "../utils/constants";
import { deadlineColor, deadlineLabel } from "../utils/dateHelpers";
import {
  getCachedDashboardSnapshot,
  loadDashboardSnapshot,
  subscribeDashboardSnapshot,
  updateDashboardSnapshot,
} from "../utils/dashboardSnapshot";
import AnimatedView from "./AnimatedView";
import KnowledgeGraph from "./KnowledgeGraph";
import Toast from "./Toast";
import "../styles/dashboard.css";

const staggerContainer = {
  initial: {},
  animate: {
    transition: {
      staggerChildren: 0.06,
    },
  },
};

const cardEntrance = {
  initial: { opacity: 0, y: 16 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { type: "spring", stiffness: 400, damping: 28 },
  },
};

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
    (left, right) => new Date(left.due_date || 0) - new Date(right.due_date || 0)
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
  const [patterns, setPatterns] = useState(cachedSnapshot?.patterns || {});
  const [loadingData, setLoadingData] = useState(!cachedSnapshot);
  const [refreshing, setRefreshing] = useState(false);
  const [lastSynced, setLastSynced] = useState(
    cachedSnapshot?.fetchedAt ? formatSyncTime(cachedSnapshot.fetchedAt) : ""
  );
  const [expandedEntryId, setExpandedEntryId] = useState(null);
  const [liveStage, setLiveStage] = useState(null);
  const [hasActivated, setHasActivated] = useState(isActive);
  const [snapshotReady, setSnapshotReady] = useState(Boolean(cachedSnapshot));
  const [showHidden, setShowHidden] = useState(false);
  const [showSnoozed, setShowSnoozed] = useState(false);
  const [projectActionState, setProjectActionState] = useState({});
  const [deadlineActionState, setDeadlineActionState] = useState({});
  const [toast, setToast] = useState(null);

  const hasLoadedRef = useRef(Boolean(cachedSnapshot));
  const refreshTimeoutRef = useRef(null);
  const retryTimeoutRef = useRef(null);

  const applySnapshot = useCallback((snapshot) => {
    setEntries(snapshot.entries || []);
    setAllDeadlines(normalizeDeadlines(snapshot.deadlines || []));
    setAllProjects(normalizeProjects(snapshot.projects || []));
    setEntities(snapshot.entities || []);
    setRelations(snapshot.relations || []);
    setPatterns(snapshot.patterns || {});
    setLoadingData(false);
    setRefreshing(false);
    setSnapshotReady(true);
    setLastSynced(formatSyncTime(snapshot.fetchedAt));
  }, []);

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
    if (!expandedEntryId) return;

    const entry = entries.find((item) => item.id === expandedEntryId);
    if (!entry || entry.status !== "processing") return;

    setLiveStage(entry.pipeline_stage);

    const interval = setInterval(async () => {
      try {
        const headers = await authHeaders();
        const data = await fetch(`${API}/entries/${expandedEntryId}/status`, {
          headers,
        }).then((r) => r.json());

        if (data) setLiveStage(data.pipeline_stage);

        if (data && data.status !== "processing") {
          setExpandedEntryId(null);
          setLiveStage(null);
          scheduleSilentRefresh(0);
        }
      } catch {
        // silently fail
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [expandedEntryId, entries, scheduleSilentRefresh]);

  useEffect(() => {
    return () => {
      clearTimeout(refreshTimeoutRef.current);
      clearTimeout(retryTimeoutRef.current);
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

  const handleProjectStatusChange = useCallback(
    async (project, nextStatus) => {
      const normalizedProject = normalizeProject(project);

      setProjectActionState((current) => ({
        ...current,
        [project.id]: true,
      }));

      setProjectsState((current) =>
        current.map((item) =>
          item.id === project.id ? { ...item, status: nextStatus } : item
        )
      );

      try {
        const updatedProject = normalizeProject(
          await updateProjectStatus(project.id, nextStatus)
        );

        setProjectsState((current) =>
          current.map((item) =>
            item.id === project.id ? updatedProject : item
          )
        );
      } catch (error) {
        setProjectsState((current) =>
          current.map((item) =>
            item.id === project.id ? normalizedProject : item
          )
        );

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
    [setProjectsState, updateProjectStatus]
  );

  const handleDeadlineStatusChange = useCallback(
    async (deadline, nextStatus) => {
      const isTerminalStatus = nextStatus === "done";
      const normalizedDeadline = normalizeDeadline(deadline);

      setDeadlineActionState((current) => ({
        ...current,
        [deadline.id]: true,
      }));

      if (isTerminalStatus) {
        setDeadlinesState((current) =>
          current.filter((item) => item.id !== deadline.id)
        );
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

        if (!isTerminalStatus) {
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
    [setDeadlinesState, updateDeadlineStatus]
  );

  const deadlines = showSnoozed
    ? allDeadlines
    : allDeadlines.filter((deadline) => deadline.status === "pending");
  const projects = showHidden
    ? allProjects
    : allProjects.filter((project) => project.status === "active");

  const people = entities.filter((entity) => entity.entity_type === "person");
  const places = entities.filter((entity) => entity.entity_type === "place");
  const others = entities.filter(
    (entity) => !["project", "person", "place"].includes(entity.entity_type)
  );
  const graphDeadlines = allDeadlines.filter(
    (deadline) => (deadline.status || "pending") === "pending"
  );

  const dashboardMotionState = hasActivated ? "animate" : "initial";

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
        <div className="dashboard">
          <div className="dashboard-header">
            <h2 className="dashboard-title">Dashboard</h2>
            <div className="dashboard-sync">
              <span className="sync-time">
                {lastSynced ? `Synced ${lastSynced}` : ""}
              </span>
              <button
                type="button"
                onClick={() => {
                  setRefreshing(true);
                  scheduleSilentRefresh(0);
                }}
                className="refresh-btn"
                title="Refresh"
                disabled={refreshing}
              >
                <svg
                  className={`refresh-icon ${refreshing ? "spinning" : ""}`}
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <polyline points="23 4 23 10 17 10" />
                  <polyline points="1 20 1 14 7 14" />
                  <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
                </svg>
              </button>
            </div>
          </div>

          <KnowledgeGraph
            entities={entities}
            entries={entries}
            deadlines={graphDeadlines}
            relations={relations}
          />

          <motion.div
            className="dashboard-columns"
            variants={staggerContainer}
            initial="initial"
            animate={dashboardMotionState}
          >
            <div className="dashboard-col-left">
              <motion.div variants={cardEntrance}>
                <div className="grid-card">
                  <h3>Patterns Detected</h3>
                  {!patterns.repeated_themes ? (
                    <p className="empty">
                      Keep journaling - MindGraph detects patterns after a few
                      entries.
                    </p>
                  ) : patterns.repeated_themes.length === 0 ? (
                    <p className="empty">
                      No patterns yet. Write a few more entries and check back.
                    </p>
                  ) : (
                    patterns.repeated_themes.map((theme, index) => (
                      <div key={`${theme.theme}-${index}`} className="pattern-item">
                        <div className="pattern-title">{theme.theme}</div>
                        <div className="pattern-obs">{theme.observation}</div>
                      </div>
                    ))
                  )}
                </div>
              </motion.div>
            </div>

            <div className="dashboard-col-right">
              <motion.div variants={cardEntrance}>
                <div className="grid-card">
                  <div className="projects-card-header">
                    <h3>Active Projects</h3>
                    <label className="deadline-toggle" htmlFor="show-hidden">
                      <span className="deadline-toggle-label">Show hidden</span>
                      <span
                        className={`deadline-toggle-switch ${
                          showHidden ? "active" : ""
                        }`}
                        aria-hidden="true"
                      >
                        <span className="deadline-toggle-thumb" />
                      </span>
                      <input
                        id="show-hidden"
                        type="checkbox"
                        checked={showHidden}
                        onChange={(event) => setShowHidden(event.target.checked)}
                      />
                    </label>
                  </div>
                  {projects.length === 0 ? (
                    <p className="empty">
                      {showHidden
                        ? "No active or hidden projects right now."
                        : "Your projects will appear here as you journal. Try writing about something you're working on."}
                    </p>
                  ) : (
                    <div className="project-list" role="list">
                      {projects.map((project) => {
                        const isHidden = project.status === "hidden";
                        const isUpdating = Boolean(projectActionState[project.id]);

                        return (
                          <div
                            key={project.id}
                            className={`project-item ${isHidden ? "hidden" : ""}`}
                            role="listitem"
                          >
                            <div className="project-main">
                              <div className="project-name">{project.name}</div>
                              <div className="project-meta">
                                Mentioned {project.mention_count || 0} time
                                {(project.mention_count || 0) !== 1 ? "s" : ""}
                                <span
                                  className={`status-badge ${
                                    isHidden ? "hidden" : "active"
                                  }`}
                                >
                                  {isHidden ? "Hidden" : "Active"}
                                </span>
                              </div>
                            </div>

                            <div className="project-actions">
                              {isHidden ? (
                                <button
                                  type="button"
                                  className="deadline-action-btn"
                                  aria-label={`Unhide ${project.name}`}
                                  title="Unhide"
                                  disabled={isUpdating}
                                  onClick={() =>
                                    handleProjectStatusChange(project, "active")
                                  }
                                >
                                  <svg
                                    width="14"
                                    height="14"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    aria-hidden="true"
                                  >
                                    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
                                    <circle cx="12" cy="12" r="3" />
                                  </svg>
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  className="deadline-action-btn"
                                  aria-label={`Hide ${project.name}`}
                                  title="Hide"
                                  disabled={isUpdating}
                                  onClick={() =>
                                    handleProjectStatusChange(project, "hidden")
                                  }
                                >
                                  <svg
                                    width="14"
                                    height="14"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    aria-hidden="true"
                                  >
                                    <path d="M10.73 5.08A11.2 11.2 0 0 1 12 5c6.5 0 10 7 10 7a17.7 17.7 0 0 1-2.18 2.93" />
                                    <path d="M6.61 6.61A17.2 17.2 0 0 0 2 12s3.5 7 10 7a9.8 9.8 0 0 0 5.39-1.61" />
                                    <line x1="2" y1="2" x2="22" y2="22" />
                                  </svg>
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </motion.div>

              <motion.div variants={cardEntrance}>
                <div className="grid-card">
                  <div className="deadlines-card-header">
                    <h3>Upcoming Deadlines</h3>
                    <label className="deadline-toggle" htmlFor="show-snoozed">
                      <span className="deadline-toggle-label">Show snoozed</span>
                      <span
                        className={`deadline-toggle-switch ${
                          showSnoozed ? "active" : ""
                        }`}
                        aria-hidden="true"
                      >
                        <span className="deadline-toggle-thumb" />
                      </span>
                      <input
                        id="show-snoozed"
                        type="checkbox"
                        checked={showSnoozed}
                        onChange={(event) => setShowSnoozed(event.target.checked)}
                      />
                    </label>
                  </div>
                  {deadlines.length === 0 ? (
                    <p className="empty">
                      {showSnoozed
                        ? "No pending or snoozed deadlines right now."
                        : "Deadlines you mention will show up here. Try: 'I need to finish the report by Friday.'"}
                    </p>
                  ) : (
                    <div className="deadline-list" role="list">
                      {deadlines.map((deadline) => {
                        const color = deadlineColor(deadline.due_date);
                        const label = deadlineLabel(deadline.due_date);
                        const isSnoozed = deadline.status === "snoozed";
                        const isUpdating = Boolean(deadlineActionState[deadline.id]);

                        return (
                          <div
                            key={deadline.id}
                            className={`deadline-item ${
                              isSnoozed ? "snoozed" : ""
                            }`}
                            role="listitem"
                          >
                            <div className="deadline-main">
                              <span className="deadline-desc">
                                {deadline.description}
                              </span>
                              <div className="deadline-meta">
                                {isSnoozed && (
                                  <span className="deadline-status-tag">
                                    Snoozed
                                  </span>
                                )}
                                <span
                                  className="deadline-badge"
                                  style={{
                                    background: color.bg,
                                    color: color.text,
                                  }}
                                >
                                  {label}
                                </span>
                              </div>
                            </div>

                            <div className="deadline-actions">
                              <button
                                type="button"
                                className="deadline-action-btn"
                                aria-label={`Mark ${deadline.description} as done`}
                                title="Mark done"
                                disabled={isUpdating}
                                onClick={() =>
                                  handleDeadlineStatusChange(deadline, "done")
                                }
                              >
                                <svg
                                  width="14"
                                  height="14"
                                  viewBox="0 0 24 24"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="2.2"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  aria-hidden="true"
                                >
                                  <polyline points="20 6 9 17 4 12" />
                                </svg>
                              </button>

                              {isSnoozed ? (
                                <button
                                  type="button"
                                  className="deadline-action-btn"
                                  aria-label={`Unsnooze ${deadline.description}`}
                                  title="Unsnooze"
                                  disabled={isUpdating}
                                  onClick={() =>
                                    handleDeadlineStatusChange(deadline, "pending")
                                  }
                                >
                                  <svg
                                    width="14"
                                    height="14"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2.2"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    aria-hidden="true"
                                  >
                                    <path d="M12 19V5" />
                                    <polyline points="7 10 12 5 17 10" />
                                  </svg>
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  className="deadline-action-btn"
                                  aria-label={`Snooze ${deadline.description}`}
                                  title="Snooze"
                                  disabled={isUpdating}
                                  onClick={() =>
                                    handleDeadlineStatusChange(deadline, "snoozed")
                                  }
                                >
                                  <svg
                                    width="14"
                                    height="14"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    aria-hidden="true"
                                  >
                                    <path d="M18 13a6 6 0 1 1-6-6 4 4 0 0 0 6 6Z" />
                                  </svg>
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </motion.div>

              <motion.div variants={cardEntrance}>
                <div className="grid-card">
                  <h3>People & Entities</h3>
                  <div className="entity-group">
                    {[...people, ...places, ...others]
                      .slice(0, 15)
                      .map((entity) => {
                        const color =
                          entityColors[entity.entity_type] || entityColors.task;

                        return (
                          <span
                            key={entity.id}
                            className="entity-chip"
                            style={{ background: color.bg, color: color.text }}
                          >
                            {entity.name}
                            {entity.mention_count > 1 && (
                              <span className="mention-count">
                                {entity.mention_count}
                              </span>
                            )}
                          </span>
                        );
                      })}
                  </div>
                </div>
              </motion.div>
            </div>
          </motion.div>

          <div className="entries-section">
            <div className="entries-header">
              <h3 className="section-title">Recent Entries</h3>
            </div>

            {entries.length === 0 ? (
              <p className="empty entries-empty">
                Your journal is empty. Switch to Write and share what's on your
                mind.
              </p>
            ) : (
              <motion.div
                className="entries-list"
                variants={staggerContainer}
                initial="initial"
                animate={dashboardMotionState}
              >
                {entries.map((entry) => (
                  <motion.div key={entry.id} variants={cardEntrance}>
                    <div
                      className={`entry-card${
                        entry.status === "processing" ? " processing" : ""
                      }`}
                      onClick={() =>
                        setExpandedEntryId(
                          expandedEntryId === entry.id ? null : entry.id
                        )
                      }
                    >
                      <div className="entry-header">
                        <div className="entry-header-main">
                          {entry.status === "processing" ? (
                            <span className="entry-title processing-title">
                              <span
                                className="spinner small"
                                style={{ marginRight: 8 }}
                              />
                              Processing your entry...
                            </span>
                          ) : (
                            <span className="entry-title">
                              {entry.auto_title || "Untitled Entry"}
                            </span>
                          )}
                        </div>

                        <div className="entry-header-meta">
                          <span className="entry-date">
                            {new Date(entry.created_at).toLocaleString()}
                          </span>
                          <svg
                            className={`entry-chevron ${
                              expandedEntryId === entry.id ? "expanded" : ""
                            }`}
                            width="16"
                            height="16"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            aria-hidden="true"
                          >
                            <polyline points="6 9 12 15 18 9" />
                          </svg>
                        </div>
                      </div>

                      {entry.status === "processing" ? (
                        <div className="entry-summary">
                          {expandedEntryId === entry.id ? (
                            <div className="pipeline-tracker">
                              {pipelineOrder.map((stage, idx) => {
                                const currentIndex = liveStage
                                  ? pipelineOrder.indexOf(liveStage)
                                  : -1;
                                const isDone = idx < currentIndex;
                                const isActive = stage === liveStage;

                                return (
                                  <div
                                    key={stage}
                                    className={`pipeline-node ${
                                      isDone ? "done" : isActive ? "active" : ""
                                    }`}
                                  >
                                    <div className="pipeline-dot" />
                                    <div className="pipeline-label">
                                      {nodeLabels[stage] || stage}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          ) : (
                            <em>Click to view live progress...</em>
                          )}
                        </div>
                      ) : (
                        <AnimatePresence mode="wait" initial={false}>
                          {expandedEntryId === entry.id ? (
                            <motion.div
                              key="raw"
                              className="entry-expanded"
                              initial={{ height: 0, opacity: 0 }}
                              animate={{ height: "auto", opacity: 1 }}
                              exit={{ height: 0, opacity: 0 }}
                              transition={{
                                type: "spring",
                                stiffness: 400,
                                damping: 32,
                              }}
                            >
                              <div className="entry-raw-text">
                                {entry.raw_text}
                              </div>
                            </motion.div>
                          ) : (
                            <motion.div
                              key="summary"
                              className="entry-summary"
                              initial={{ opacity: 0 }}
                              animate={{ opacity: 1 }}
                              exit={{ opacity: 0 }}
                              transition={{ duration: 0.16 }}
                            >
                              {entry.summary || entry.raw_text}
                            </motion.div>
                          )}
                        </AnimatePresence>
                      )}
                    </div>
                  </motion.div>
                ))}
              </motion.div>
            )}
          </div>
        </div>
      )}

      <Toast
        message={toast?.message}
        type={toast?.type || "success"}
        visible={!!toast}
        onDismiss={() => setToast(null)}
      />
    </AnimatedView>
  );
}

export default Dashboard;
