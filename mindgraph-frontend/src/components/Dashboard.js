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

const Dashboard = forwardRef(function Dashboard({ isActive }, ref) {
  const [entries, setEntries] = useState([]);
  const [deadlines, setDeadlines] = useState([]);
  const [entities, setEntities] = useState([]);
  const [patterns, setPatterns] = useState({});
  const [loadingData, setLoadingData] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastSynced, setLastSynced] = useState("");
  const [expandedEntryId, setExpandedEntryId] = useState(null);
  const [liveStage, setLiveStage] = useState(null);
  const [hasActivated, setHasActivated] = useState(isActive);

  const hasLoadedRef = useRef(false);
  const refreshTimeoutRef = useRef(null);
  const retryTimeoutRef = useRef(null);
  const refreshInFlightRef = useRef(false);
  const queuedRefreshRef = useRef(false);

  const applySnapshot = useCallback((snapshot) => {
    setEntries(snapshot.entries || []);
    setDeadlines(snapshot.deadlines || []);
    setEntities(snapshot.entities || []);
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

  const fetchSnapshot = useCallback(async () => {
    const headers = await authHeaders();

    const [entriesData, deadlinesData, entitiesData, patternsData] =
      await Promise.all([
        fetch(`${API}/entries`, { headers }).then((r) => r.json()),
        fetch(`${API}/deadlines`, { headers }).then((r) => r.json()),
        fetch(`${API}/entities`, { headers }).then((r) => r.json()),
        fetch(`${API}/insights/patterns`, { headers })
          .then((r) => r.json())
          .catch(() => ({ data: {} })),
      ]);

    return {
      entries: entriesData.entries || [],
      deadlines: deadlinesData.deadlines || [],
      entities: entitiesData.entities || [],
      patterns: patternsData.data || {},
    };
  }, []);

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

  const projects = entities.filter((entity) => entity.entity_type === "project");
  const people = entities.filter((entity) => entity.entity_type === "person");
  const places = entities.filter((entity) => entity.entity_type === "place");
  const others = entities.filter(
    (entity) => !["project", "person", "place"].includes(entity.entity_type)
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
            deadlines={deadlines}
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
                  <h3>Upcoming Deadlines</h3>
                  {deadlines.length === 0 ? (
                    <p className="empty">
                      Deadlines you mention will show up here. Try: 'I need to
                      finish the report by Friday.'
                    </p>
                  ) : (
                    deadlines.slice(0, 5).map((deadline) => {
                      const color = deadlineColor(deadline.due_date);
                      const label = deadlineLabel(deadline.due_date);

                      return (
                        <div key={deadline.id} className="deadline-item">
                          <span className="deadline-desc">
                            {deadline.description}
                          </span>
                          <span
                            className="deadline-badge"
                            style={{ background: color.bg, color: color.text }}
                          >
                            {label}
                          </span>
                        </div>
                      );
                    })
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
    </AnimatedView>
  );
});

export default Dashboard;
