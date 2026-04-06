import { useState, useEffect, useCallback, useRef } from "react";
import { API, authHeaders } from "../utils/auth";
import { entityColors, nodeLabels, pipelineOrder } from "../utils/constants";
import { deadlineColor, deadlineLabel } from "../utils/dateHelpers";
import MindLatelyCard from "./MindLatelyCard";
import "../styles/dashboard.css";

function Dashboard() {
  const [entries, setEntries] = useState([]);
  const [deadlines, setDeadlines] = useState([]);
  const [entities, setEntities] = useState([]);
  const [patterns, setPatterns] = useState({});
  const [loadingData, setLoadingData] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastSynced, setLastSynced] = useState("");
  const [expandedEntryId, setExpandedEntryId] = useState(null);
  const [liveStage, setLiveStage] = useState(null);
  const [selectedMindNodeId, setSelectedMindNodeId] = useState("you");

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
    setLoadingData(true);
    try {
      const snapshot = await fetchSnapshot();
      applySnapshot(snapshot);
      hasLoadedRef.current = true;
    } catch (err) {
      console.error("Initial dashboard load failed:", err);
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
    } catch (err) {
      console.error("Silent refresh failed:", err);
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

  useEffect(() => {
    initialLoad();
  }, [initialLoad]);

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
      } catch (err) {
        console.error("Processing poll failed:", err);
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
      } catch (err) {
        console.error("Expanded entry status poll failed:", err);
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

  const getRecencyTs = (item) => {
    const raw =
      item?.last_mentioned_at ||
      item?.updated_at ||
      item?.created_at ||
      item?.last_seen_at ||
      null;

    const ts = raw ? new Date(raw).getTime() : 0;
    return Number.isNaN(ts) ? 0 : ts;
  };

  const formatMindDate = (value) => {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleDateString("en", {
      month: "short",
      day: "numeric",
    });
  };

  const sortRecentAndRelevant = (items) =>
    [...items].sort((a, b) => {
      const recencyDiff = getRecencyTs(b) - getRecencyTs(a);
      if (recencyDiff !== 0) return recencyDiff;

      const mentionDiff = (b.mention_count || 0) - (a.mention_count || 0);
      if (mentionDiff !== 0) return mentionDiff;

      return (a.name || "").localeCompare(b.name || "");
    });

  const mindProjects = sortRecentAndRelevant(projects).slice(0, 2);
  const mindEntities = sortRecentAndRelevant([
    ...people,
    ...places,
    ...others,
  ]).slice(0, 3);

  const mindNodes = [
    {
      id: "you",
      label: "You",
      kind: "self",
      x: 50,
      y: 46,
      mentionCount: 0,
      lastMentionedLabel: "",
    },
    ...mindProjects.map((item, index) => ({
      id: `project-${item.id ?? item.name ?? index}`,
      label: item.name,
      kind: "project",
      x: index === 0 ? 24 : 76,
      y: index === 0 ? 22 : 26,
      mentionCount: item.mention_count || 0,
      lastMentionedLabel: formatMindDate(
        item.last_mentioned_at || item.updated_at || item.created_at
      ),
    })),
    ...mindEntities.map((item, index) => {
      const positions = [
        { x: 20, y: 68 },
        { x: 50, y: 78 },
        { x: 80, y: 66 },
      ];
      const pos = positions[index] || { x: 50, y: 70 };

      return {
        id: `entity-${item.id ?? item.name ?? index}`,
        label: item.name,
        kind: "entity",
        x: pos.x,
        y: pos.y,
        mentionCount: item.mention_count || 0,
        lastMentionedLabel: formatMindDate(
          item.last_mentioned_at || item.updated_at || item.created_at
        ),
      };
    }),
  ];

  const resolvedSelectedMindNodeId = mindNodes.some(
    (node) => node.id === selectedMindNodeId
  )
    ? selectedMindNodeId
    : "you";

  if (loadingData) {
    return (
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
    );
  }

  return (
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

      <div className="dashboard-columns">
        <div className="dashboard-col-left">
          <MindLatelyCard
            nodes={mindNodes}
            selectedNodeId={resolvedSelectedMindNodeId}
            onSelectNode={setSelectedMindNodeId}
          />

          <div className="grid-card">
            <h3>Patterns Detected</h3>
            {!patterns.repeated_themes ? (
              <p className="empty">Analyzing your patterns...</p>
            ) : patterns.repeated_themes.length === 0 ? (
              <p className="empty">No patterns yet - keep journaling!</p>
            ) : (
              patterns.repeated_themes.map((theme, index) => (
                <div key={`${theme.theme}-${index}`} className="pattern-item">
                  <div className="pattern-title">{theme.theme}</div>
                  <div className="pattern-obs">{theme.observation}</div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="dashboard-col-right">
          <div className="grid-card">
            <h3>Active Projects</h3>
            {projects.length === 0 ? (
              <p className="empty">No projects detected yet</p>
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

          <div className="grid-card">
            <h3>Upcoming Deadlines</h3>
            {deadlines.length === 0 ? (
              <p className="empty">No deadlines found</p>
            ) : (
              deadlines.slice(0, 5).map((deadline) => {
                const color = deadlineColor(deadline.due_date);
                const label = deadlineLabel(deadline.due_date);

                return (
                  <div key={deadline.id} className="deadline-item">
                    <span className="deadline-desc">{deadline.description}</span>
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

          <div className="grid-card">
            <h3>People & Entities</h3>
            <div className="entity-group">
              {[...people, ...places, ...others].slice(0, 15).map((entity) => {
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
                      <span className="mention-count">{entity.mention_count}</span>
                    )}
                  </span>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      <div className="entries-section">
        <div className="entries-header">
          <h3 className="section-title">Recent Entries</h3>
        </div>

        {entries.length === 0 ? (
          <p className="empty" style={{ padding: 16 }}>
            No entries yet. Start writing!
          </p>
        ) : (
          entries.map((entry) => (
            <div
              key={entry.id}
              className={`entry-card${
                entry.status === "processing" ? " processing" : ""
              }`}
              onClick={() => {
                if (entry.status === "processing") {
                  setExpandedEntryId(
                    expandedEntryId === entry.id ? null : entry.id
                  );
                }
              }}
              style={entry.status === "processing" ? { cursor: "pointer" } : {}}
            >
              <div className="entry-header">
                {entry.status === "processing" ? (
                  <>
                    <span className="entry-title processing-title">
                      <span className="spinner small" style={{ marginRight: 8 }} />
                      Processing your entry...
                    </span>
                    <span className="entry-date">
                      {new Date(entry.created_at).toLocaleString()}
                    </span>
                  </>
                ) : (
                  <>
                    <span className="entry-title">
                      {entry.auto_title || "Untitled Entry"}
                    </span>
                    <span className="entry-date">
                      {new Date(entry.created_at).toLocaleString()}
                    </span>
                  </>
                )}
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
                <div className="entry-summary">
                  {entry.summary || entry.raw_text}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default Dashboard;
