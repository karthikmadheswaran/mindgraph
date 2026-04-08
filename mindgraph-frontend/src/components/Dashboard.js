import {
  useState,
  useEffect,
  useCallback,
  useRef,
  forwardRef,
  useImperativeHandle,
} from "react";
import { motion, AnimatePresence } from "framer-motion";
import { API, authHeaders } from "../utils/auth";
import { entityColors, nodeLabels, pipelineOrder } from "../utils/constants";
import { deadlineColor, deadlineLabel } from "../utils/dateHelpers";
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

const normalizeDeadlines = (items = []) => items.map(normalizeDeadline);

const sortDeadlines = (items) =>
  [...items].sort(
    (left, right) => new Date(left.due_date || 0) - new Date(right.due_date || 0)
  );

const Dashboard = forwardRef(function Dashboard({ isActive }, ref) {
  const [entries, setEntries] = useState([]);
  const [deadlines, setDeadlines] = useState([]);
  const [entities, setEntities] = useState([]);
  const [relations, setRelations] = useState([]);
  const [patterns, setPatterns] = useState({});
  const [loadingData, setLoadingData] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastSynced, setLastSynced] = useState("");
  const [expandedEntryId, setExpandedEntryId] = useState(null);
  const [liveStage, setLiveStage] = useState(null);
  const [hasActivated, setHasActivated] = useState(isActive);
  const [showSnoozed, setShowSnoozed] = useState(false);
  const [deadlineActionState, setDeadlineActionState] = useState({});
  const [toast, setToast] = useState(null);

  const hasLoadedRef = useRef(false);
  const refreshTimeoutRef = useRef(null);
  const retryTimeoutRef = useRef(null);
  const refreshInFlightRef = useRef(false);
  const queuedRefreshRef = useRef(false);

  const applySnapshot = useCallback((snapshot) => {
    setEntries(snapshot.entries || []);
    setDeadlines(normalizeDeadlines(snapshot.deadlines || []));
    setEntities(snapshot.entities || []);
    setRelations(snapshot.relations || []);
    setPatterns(snapshot.patterns || {});
    setRefreshing(false);
    setLastSynced(
      new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      })
    );
  }, []);

  const fetchEntries = useCallback(async () => {
    const headers = await authHeaders();
    return fetch(`${API}/entries`, { headers }).then((r) => r.json());
  }, []);

  const fetchDeadlines = useCallback(
    async (includeSnoozed = showSnoozed) => {
      const headers = await authHeaders();
      const query = includeSnoozed ? "?status=pending,snoozed" : "";
      const response = await fetch(`${API}/deadlines${query}`, { headers });

      if (!response.ok) {
        throw new Error("Failed to fetch deadlines");
      }

      return response.json();
    },
    [showSnoozed]
  );

  const fetchSnapshot = useCallback(async () => {
    const headers = await authHeaders();

    const [entriesData, deadlinesData, entitiesData, relationsData, patternsData] =
      await Promise.all([
        fetch(`${API}/entries`, { headers }).then((r) => r.json()),
        fetchDeadlines(showSnoozed),
        fetch(`${API}/entities`, { headers }).then((r) => r.json()),
        fetch(`${API}/entity-relations`, { headers })
          .then((r) => r.json())
          .catch(() => ({ relations: [] })),
        fetch(`${API}/insights/patterns`, { headers })
          .then((r) => r.json())
          .catch(() => ({ data: {} })),
      ]);

    return {
      entries: entriesData.entries || [],
      deadlines: deadlinesData.deadlines || [],
      entities: entitiesData.entities || [],
      relations: relationsData.relations || [],
      patterns: patternsData.data || {},
    };
  }, [fetchDeadlines, showSnoozed]);

  const initialLoad = useCallback(async () => {
    if (hasLoadedRef.current) return;

    setLoadingData(true);
    try {
      const snapshot = await fetchSnapshot();
      applySnapshot(snapshot);
      hasLoadedRef.current = true;
    } catch {
      setRefreshing(false);
    } finally {
      setLoadingData(false);
    }
  }, [fetchSnapshot, applySnapshot]);

  const runSilentRefresh = useCallback(async () => {
    if (refreshInFlightRef.current) {
      queuedRefreshRef.current = true;
      return;
    }

    refreshInFlightRef.current = true;

    try {
      const snapshot = await fetchSnapshot();
      applySnapshot(snapshot);
      hasLoadedRef.current = true;
    } catch {
      setRefreshing(false);
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = setTimeout(() => {
        runSilentRefresh();
      }, 1500);
    } finally {
      refreshInFlightRef.current = false;

      if (queuedRefreshRef.current) {
        queuedRefreshRef.current = false;
        runSilentRefresh();
      }
    }
  }, [fetchSnapshot, applySnapshot]);

  const scheduleSilentRefresh = useCallback(
    (delay = 500) => {
      clearTimeout(refreshTimeoutRef.current);
      refreshTimeoutRef.current = setTimeout(() => {
        runSilentRefresh();
      }, delay);
    },
    [runSilentRefresh]
  );

  useImperativeHandle(
    ref,
    () => ({
      triggerRefresh: () => scheduleSilentRefresh(0),
    }),
    [scheduleSilentRefresh]
  );

  useEffect(() => {
    initialLoad();
  }, [initialLoad]);

  useEffect(() => {
    if (isActive && !hasActivated) {
      setHasActivated(true);
    }
  }, [isActive, hasActivated]);

  useEffect(() => {
    if (!hasLoadedRef.current) return;

    setRefreshing(true);
    scheduleSilentRefresh(0);
  }, [showSnoozed, scheduleSilentRefresh]);

  useEffect(() => {
    if (!hasLoadedRef.current) return;

    const interval = setInterval(() => {
      scheduleSilentRefresh(0);
    }, 45000);

    return () => clearInterval(interval);
  }, [scheduleSilentRefresh]);

  useEffect(() => {
    if (!entries.some((entry) => entry.status === "processing")) return;

    const interval = setInterval(async () => {
      try {
        const data = await fetchEntries();
        setEntries(data.entries || []);
      } catch {
        // silently fail
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [entries, fetchEntries]);

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

  const handleDeadlineStatusChange = useCallback(
    async (deadline, nextStatus) => {
      const currentStatus = deadline.status || "pending";
      const isUnsnooze = currentStatus === "snoozed" && nextStatus === "pending";
      const normalizedDeadline = normalizeDeadline(deadline);

      setDeadlineActionState((current) => ({
        ...current,
        [deadline.id]: true,
      }));

      if (isUnsnooze) {
        setDeadlines((current) =>
          current.map((item) =>
            item.id === deadline.id ? { ...item, status: "pending" } : item
          )
        );
      } else {
        setDeadlines((current) =>
          current.filter((item) => item.id !== deadline.id)
        );
      }

      try {
        const updatedDeadline = normalizeDeadline(
          await updateDeadlineStatus(deadline.id, nextStatus)
        );

        if (isUnsnooze) {
          setDeadlines((current) =>
            current.map((item) =>
              item.id === deadline.id ? updatedDeadline : item
            )
          );
        }

        if (nextStatus === "snoozed" && showSnoozed) {
          const refreshedDeadlines = await fetchDeadlines(true);
          setDeadlines(normalizeDeadlines(refreshedDeadlines.deadlines || []));
        }
      } catch (error) {
        if (isUnsnooze) {
          setDeadlines((current) =>
            current.map((item) =>
              item.id === deadline.id ? normalizedDeadline : item
            )
          );
        } else {
          setDeadlines((current) => {
            if (current.some((item) => item.id === deadline.id)) {
              return current;
            }

            return sortDeadlines([...current, normalizedDeadline]);
          });
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
    [fetchDeadlines, showSnoozed, updateDeadlineStatus]
  );

  const projects = entities.filter((entity) => entity.entity_type === "project");
  const people = entities.filter((entity) => entity.entity_type === "person");
  const places = entities.filter((entity) => entity.entity_type === "place");
  const others = entities.filter(
    (entity) => !["project", "person", "place"].includes(entity.entity_type)
  );
  const graphDeadlines = deadlines.filter(
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
                  <h3>Active Projects</h3>
                  {projects.length === 0 ? (
                    <p className="empty">
                      Your projects will appear here as you journal. Try writing
                      about something you're working on.
                    </p>
                  ) : (
                    projects.slice(0, 5).map((project) => (
                      <div key={project.id} className="project-item">
                        <div className="project-name">{project.name}</div>
                        <div className="project-meta">
                          Mentioned {project.mention_count} time
                          {project.mention_count !== 1 ? "s" : ""}
                          <span className="status-badge active">Active</span>
                        </div>
                      </div>
                    ))
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
});

export default Dashboard;
