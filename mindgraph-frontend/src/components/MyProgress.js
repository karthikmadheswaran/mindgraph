import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { API, authHeaders } from "../utils/auth";
import { loadDashboardSnapshot } from "../utils/dashboardSnapshot";
import { parseDeadlineDate } from "../utils/dateHelpers";
import AnimatedView from "./AnimatedView";
import DateTimePicker from "./DateTimePicker";
import Toast from "./Toast";
import "../styles/my-progress.css";

const GROUP_LABELS = [
  ["thisWeek", "This Week"],
  ["lastWeek", "Last Week"],
  ["earlier", "Earlier"],
];

const normalizeDeadline = (deadline) => ({
  ...deadline,
  status: deadline.status || "done",
});

const normalizeProject = (project) => ({
  ...project,
  status: project.status || "completed",
});

const startOfDay = (value) => {
  const date = new Date(value);
  date.setHours(0, 0, 0, 0);
  return date;
};

const startOfWeek = (value) => {
  const date = startOfDay(value);
  const dayOffset = (date.getDay() + 6) % 7;
  date.setDate(date.getDate() - dayOffset);
  return date;
};

const getTimeGroupKey = (value) => {
  const date = new Date(value || "");
  if (Number.isNaN(date.getTime())) {
    return "earlier";
  }

  const thisWeekStart = startOfWeek(new Date());
  const lastWeekStart = new Date(thisWeekStart);
  lastWeekStart.setDate(lastWeekStart.getDate() - 7);

  if (date >= thisWeekStart) {
    return "thisWeek";
  }

  if (date >= lastWeekStart) {
    return "lastWeek";
  }

  return "earlier";
};

const groupByTime = (items, dateField) => {
  const grouped = {
    thisWeek: [],
    lastWeek: [],
    earlier: [],
  };

  items.forEach((item) => {
    grouped[getTimeGroupKey(item?.[dateField])].push(item);
  });

  return GROUP_LABELS.map(([key, label]) => ({
    key,
    label,
    items: grouped[key],
  })).filter((group) => group.items.length > 0);
};

const formatTimestamp = (value, { includeTime = true } = {}) => {
  const date = new Date(value || "");
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  const options = {
    month: "short",
    day: "numeric",
    year: "numeric",
  };

  if (includeTime) {
    options.hour = "numeric";
    options.minute = "2-digit";
  }

  return date.toLocaleString([], options);
};

const formatDueDate = (value) => {
  const parsed = parseDeadlineDate(value);
  if (!parsed) {
    return "";
  }

  const baseLabel = parsed.dateOnly.toLocaleDateString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  if (!parsed.hasMeaningfulTime) {
    return baseLabel;
  }

  return `${baseLabel} at ${parsed.timeLabel}`;
};

function MyProgress({ isActive, userId }) {
  const [progress, setProgress] = useState({ deadlines: [], projects: [] });
  const [loadingData, setLoadingData] = useState(true);
  const [deadlineActionState, setDeadlineActionState] = useState({});
  const [projectActionState, setProjectActionState] = useState({});
  const [rescheduleDeadlineId, setRescheduleDeadlineId] = useState(null);
  const [toast, setToast] = useState(null);

  const hasFetchedRef = useRef(false);
  const previousUserIdRef = useRef(userId);
  const rescheduleButtonRefs = useRef({});

  const refreshDashboardData = useCallback(() => {
    if (!userId) {
      return Promise.resolve();
    }

    return loadDashboardSnapshot({ force: true, userId }).catch(() => {
      // dashboard cache refresh should not block the progress page
    });
  }, [userId]);

  const fetchProgress = useCallback(async ({ showLoading = false } = {}) => {
    if (showLoading) {
      setLoadingData(true);
    }

    try {
      const headers = await authHeaders();
      const response = await fetch(`${API}/progress`, { headers });

      if (response.status === 401) {
        throw new Error("Session expired. Please log in again.");
      }

      if (!response.ok) {
        throw new Error("Failed to load your progress. Please try again.");
      }

      const data = await response.json();
      setProgress({
        deadlines: (data.deadlines || []).map(normalizeDeadline),
        projects: (data.projects || []).map(normalizeProject),
      });
    } catch (error) {
      setToast({
        message: error.message || "Failed to load your progress. Please try again.",
        type: "error",
      });
    } finally {
      setLoadingData(false);
    }
  }, []);

  useEffect(() => {
    if (!userId || !isActive) {
      return;
    }

    fetchProgress({ showLoading: !hasFetchedRef.current });
    hasFetchedRef.current = true;
  }, [fetchProgress, isActive, userId]);

  useEffect(() => {
    if (previousUserIdRef.current === userId) {
      return;
    }

    previousUserIdRef.current = userId;
    hasFetchedRef.current = false;
    setProgress({ deadlines: [], projects: [] });
    setLoadingData(true);
    setRescheduleDeadlineId(null);
  }, [userId]);

  const updateDeadlineStatus = useCallback(async (deadlineId, status) => {
    const headers = await authHeaders();
    const response = await fetch(`${API}/deadlines/${deadlineId}/status`, {
      method: "PATCH",
      headers,
      body: JSON.stringify({ status }),
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
      throw new Error("Failed to reschedule deadline. Please try again.");
    }

    return response.json();
  }, []);

  const updateProjectStatus = useCallback(async (projectId, status) => {
    const headers = await authHeaders();
    const response = await fetch(`${API}/projects/${projectId}/status`, {
      method: "PATCH",
      headers,
      body: JSON.stringify({ status }),
    });

    if (response.status === 401) {
      throw new Error("Session expired. Please log in again.");
    }

    if (!response.ok) {
      throw new Error("Failed to update project. Please try again.");
    }

    return response.json();
  }, []);

  const handleDeadlineStatusChange = useCallback(
    async (deadline, nextStatus) => {
      setDeadlineActionState((current) => ({
        ...current,
        [deadline.id]: true,
      }));

      try {
        await updateDeadlineStatus(deadline.id, nextStatus);
        await Promise.all([
          fetchProgress(),
          refreshDashboardData(),
        ]);
      } catch (error) {
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
    [fetchProgress, refreshDashboardData, updateDeadlineStatus]
  );

  const handleProjectStatusChange = useCallback(
    async (project, nextStatus) => {
      setProjectActionState((current) => ({
        ...current,
        [project.id]: true,
      }));

      try {
        await updateProjectStatus(project.id, nextStatus);
        await Promise.all([
          fetchProgress(),
          refreshDashboardData(),
        ]);
      } catch (error) {
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
    [fetchProgress, refreshDashboardData, updateProjectStatus]
  );

  const handleRescheduleSave = useCallback(
    async (deadline, nextDueDate) => {
      setDeadlineActionState((current) => ({
        ...current,
        [deadline.id]: true,
      }));
      setRescheduleDeadlineId(null);

      try {
        await updateDeadlineDate(deadline.id, nextDueDate);
        await updateDeadlineStatus(deadline.id, "pending");
        await Promise.all([
          fetchProgress(),
          refreshDashboardData(),
        ]);
      } catch (error) {
        setToast({
          message: error.message || "Failed to reschedule deadline. Please try again.",
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
      fetchProgress,
      refreshDashboardData,
      updateDeadlineDate,
      updateDeadlineStatus,
    ]
  );

  const activeRescheduleDeadline =
    progress.deadlines.find((deadline) => deadline.id === rescheduleDeadlineId) ||
    null;

  useEffect(() => {
    if (rescheduleDeadlineId && !activeRescheduleDeadline) {
      setRescheduleDeadlineId(null);
    }
  }, [activeRescheduleDeadline, rescheduleDeadlineId]);

  const doneDeadlines = progress.deadlines.filter(
    (deadline) => deadline.status === "done"
  );
  const missedDeadlines = progress.deadlines.filter(
    (deadline) => deadline.status === "missed"
  );
  const completedProjects = progress.projects.filter(
    (project) => project.status === "completed"
  );

  const doneGroups = groupByTime(doneDeadlines, "status_changed_at");
  const missedGroups = groupByTime(missedDeadlines, "status_changed_at");
  const projectGroups = groupByTime(completedProjects, "status_changed_at");
  const isEmpty =
    doneDeadlines.length === 0 &&
    missedDeadlines.length === 0 &&
    completedProjects.length === 0;

  return (
    <AnimatedView viewKey="progress" isActive={isActive}>
      {loadingData ? (
        <div className="progress-loading">
          <span className="spinner" />
          <p>Loading your progress...</p>
        </div>
      ) : (
        <div className="progress-page">
          <div className="progress-hero">
            <div>
              <p className="progress-kicker">My Progress</p>
              <h2 className="progress-title">A warm look at what you moved forward.</h2>
            </div>
            <p className="progress-subtitle">
              What&apos;s ahead lives on the dashboard. This is the quieter page for
              what you finished, what slipped, and what still counts.
            </p>
          </div>

          {isEmpty ? (
            <div className="progress-empty">
              <h3>Nothing here yet.</h3>
              <p>
                Complete your first deadline or finish a project and it&apos;ll show
                up here.
              </p>
            </div>
          ) : (
            <div className="progress-sections">
              {doneDeadlines.length > 0 && (
                <motion.section
                  className="progress-section"
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ type: "spring", stiffness: 380, damping: 30 }}
                >
                  <div className="progress-section-header">
                    <h3>Things I Got Done</h3>
                    <p>Proof that follow-through happened.</p>
                  </div>

                  {doneGroups.map((group) => (
                    <div key={group.key} className="progress-group">
                      <div className="progress-group-label">{group.label}</div>
                      <div className="progress-item-list">
                        {group.items.map((deadline) => {
                          const isUpdating = Boolean(deadlineActionState[deadline.id]);

                          return (
                            <div key={deadline.id} className="progress-item">
                              <div className="progress-item-main">
                                <div className="progress-item-title">
                                  {deadline.description}
                                </div>
                                <div className="progress-item-meta">
                                  Due {formatDueDate(deadline.due_date)}
                                </div>
                                <div className="progress-item-meta">
                                  Completed {formatTimestamp(deadline.status_changed_at)}
                                </div>
                              </div>

                              <div className="progress-item-actions">
                                <button
                                  type="button"
                                  className="progress-action-btn"
                                  disabled={isUpdating}
                                  onClick={() =>
                                    handleDeadlineStatusChange(deadline, "pending")
                                  }
                                >
                                  Restore
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </motion.section>
              )}

              {missedDeadlines.length > 0 && (
                <motion.section
                  className="progress-section missed"
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ type: "spring", stiffness: 380, damping: 30, delay: 0.04 }}
                >
                  <div className="progress-section-header">
                    <h3>Ones That Slipped</h3>
                    <p>Honest, useful, and still easy to move forward.</p>
                  </div>

                  {missedGroups.map((group) => (
                    <div key={group.key} className="progress-group">
                      <div className="progress-group-label">{group.label}</div>
                      <div className="progress-item-list">
                        {group.items.map((deadline) => {
                          const isUpdating = Boolean(deadlineActionState[deadline.id]);

                          return (
                            <div
                              key={deadline.id}
                              className="progress-item progress-item-missed"
                            >
                              <div className="progress-item-main">
                                <div className="progress-item-title">
                                  {deadline.description}
                                </div>
                                <div className="progress-item-meta">
                                  Was due {formatDueDate(deadline.due_date)}
                                </div>
                                <div className="progress-item-meta">
                                  Marked missed {formatTimestamp(deadline.status_changed_at)}
                                </div>
                              </div>

                              <div className="progress-item-actions">
                                <button
                                  type="button"
                                  className="progress-action-btn"
                                  disabled={isUpdating}
                                  onClick={() =>
                                    handleDeadlineStatusChange(deadline, "done")
                                  }
                                >
                                  Actually did it
                                </button>
                                <button
                                  type="button"
                                  className="progress-action-btn subtle"
                                  ref={(node) => {
                                    if (node) {
                                      rescheduleButtonRefs.current[deadline.id] = node;
                                    } else {
                                      delete rescheduleButtonRefs.current[deadline.id];
                                    }
                                  }}
                                  disabled={isUpdating}
                                  onClick={() => setRescheduleDeadlineId(deadline.id)}
                                >
                                  Reschedule
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </motion.section>
              )}

              {completedProjects.length > 0 && (
                <motion.section
                  className="progress-section projects"
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ type: "spring", stiffness: 380, damping: 30, delay: 0.08 }}
                >
                  <div className="progress-section-header">
                    <h3>Projects I Finished</h3>
                    <p>Big or small, this is the shipped pile.</p>
                  </div>

                  {projectGroups.map((group) => (
                    <div key={group.key} className="progress-group">
                      <div className="progress-group-label">{group.label}</div>
                      <div className="progress-item-list">
                        {group.items.map((project) => {
                          const isUpdating = Boolean(projectActionState[project.id]);

                          return (
                            <div
                              key={project.id}
                              className="progress-item progress-item-project"
                            >
                              <div className="progress-item-main">
                                <div className="progress-item-title">
                                  {project.name}
                                </div>
                                <div className="progress-item-meta">
                                  First mentioned {formatTimestamp(project.first_mentioned_at)}
                                </div>
                                <div className="progress-item-meta">
                                  Finished {formatTimestamp(project.status_changed_at)}
                                </div>
                                <div className="progress-item-meta">
                                  Mentioned {project.mention_count || 0} time
                                  {(project.mention_count || 0) === 1 ? "" : "s"}
                                </div>
                              </div>

                              <div className="progress-item-actions">
                                <button
                                  type="button"
                                  className="progress-action-btn"
                                  disabled={isUpdating}
                                  onClick={() =>
                                    handleProjectStatusChange(project, "active")
                                  }
                                >
                                  Reopen
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </motion.section>
              )}
            </div>
          )}
        </div>
      )}

      <AnimatePresence>
        {activeRescheduleDeadline && (
          <DateTimePicker
            currentDate={activeRescheduleDeadline.due_date}
            anchorRef={{
              current:
                rescheduleButtonRefs.current[activeRescheduleDeadline.id] || null,
            }}
            onCancel={() => setRescheduleDeadlineId(null)}
            onSave={(nextDueDate) =>
              handleRescheduleSave(activeRescheduleDeadline, nextDueDate)
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

export default MyProgress;
