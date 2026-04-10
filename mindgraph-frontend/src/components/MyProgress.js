import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { API, authHeaders } from "../utils/auth";
import {
  getCachedDashboardSnapshot,
  loadDashboardSnapshot,
  subscribeDashboardSnapshot,
  updateDashboardSnapshot,
} from "../utils/dashboardSnapshot";
import { deadlineSortValue, parseDeadlineDate } from "../utils/dateHelpers";
import AnimatedView from "./AnimatedView";
import DateTimePicker from "./DateTimePicker";
import Toast from "./Toast";
import "../styles/my-progress.css";

const GROUP_LABELS = [
  ["thisWeek", "This Week"],
  ["lastWeek", "Last Week"],
  ["earlier", "Earlier"],
];

const sectionMotionProps = (delay = 0) => ({
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0 },
  transition: { type: "spring", stiffness: 380, damping: 30, delay },
});

const normalizeDeadline = (deadline) => ({
  ...deadline,
  status: deadline.status || "done",
});

const normalizeProject = (project) => ({
  ...project,
  status: project.status || "completed",
});

const normalizeProgress = (progress = {}) => ({
  deadlines: (progress.deadlines || []).map(normalizeDeadline),
  projects: (progress.projects || []).map(normalizeProject),
});

const sortDashboardDeadlines = (items) =>
  [...items].sort(
    (left, right) =>
      deadlineSortValue(left.due_date).localeCompare(deadlineSortValue(right.due_date))
  );

const sortDashboardProjects = (items) =>
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

const formatNarrativeDay = (value) => {
  const date = new Date(value || "");
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return date.toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
};

const formatDueNarrative = (value, prefix = "Due") => {
  const parsed = parseDeadlineDate(value);
  if (!parsed) {
    return "";
  }

  const dateLabel = parsed.dateOnly.toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });

  if (!parsed.hasMeaningfulTime) {
    return `${prefix} ${dateLabel}`;
  }

  return `${prefix} ${dateLabel} at ${parsed.timeLabel}`;
};

const formatDoneNarrative = (value) => {
  const dateLabel = formatNarrativeDay(value);
  return dateLabel ? `Done on ${dateLabel}` : "Done recently";
};

const formatMissedNarrative = (value) => {
  const dateLabel = formatNarrativeDay(value);
  return dateLabel ? `Marked missed on ${dateLabel}` : "Marked missed recently";
};

const formatFinishedNarrative = (value) => {
  const dateLabel = formatNarrativeDay(value);
  return dateLabel ? `Finished on ${dateLabel}` : "Finished recently";
};

const formatMentionNarrative = (project) => {
  const mentionCount = project.mention_count || 0;
  const firstMentionLabel = formatNarrativeDay(project.first_mentioned_at);

  if (mentionCount && firstMentionLabel) {
    return `Mentioned ${mentionCount} time${
      mentionCount === 1 ? "" : "s"
    } since ${firstMentionLabel}`;
  }

  if (mentionCount) {
    return `Mentioned ${mentionCount} time${mentionCount === 1 ? "" : "s"}`;
  }

  if (firstMentionLabel) {
    return `First mentioned ${firstMentionLabel}`;
  }

  return "";
};

function SectionEmpty({ tone = "sage", message }) {
  return (
    <div className={`progress-section-empty ${tone}`}>
      <div className="progress-empty-icon" aria-hidden="true">
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M6 4.75h9.5L19 8.2V19.25A1.75 1.75 0 0 1 17.25 21H6.75A1.75 1.75 0 0 1 5 19.25V6.5A1.75 1.75 0 0 1 6.75 4.75Z" />
          <path d="M15 4.75V8.5h3.75" />
          <path d="M8.5 12.25h7" />
          <path d="M8.5 15.75h5.5" />
        </svg>
      </div>
      <p>{message}</p>
    </div>
  );
}

function MyProgress({ isActive, userId }) {
  const cachedSnapshot = getCachedDashboardSnapshot({ userId });
  const hasCachedProgress = Boolean(cachedSnapshot?.progress);

  const [progress, setProgress] = useState(() =>
    normalizeProgress(cachedSnapshot?.progress)
  );
  const [loadingData, setLoadingData] = useState(
    () => Boolean(isActive && !hasCachedProgress)
  );
  const [deadlineActionState, setDeadlineActionState] = useState({});
  const [projectActionState, setProjectActionState] = useState({});
  const [rescheduleDeadlineId, setRescheduleDeadlineId] = useState(null);
  const [toast, setToast] = useState(null);

  const hasLoadedRef = useRef(hasCachedProgress);
  const previousUserIdRef = useRef(userId);
  const rescheduleButtonRefs = useRef({});

  const applySnapshot = useCallback((snapshot) => {
    hasLoadedRef.current = Boolean(snapshot?.progress);
    setProgress(normalizeProgress(snapshot?.progress));
    setLoadingData(false);
  }, []);

  const mutateSharedSnapshot = useCallback(
    (updater) => {
      updateDashboardSnapshot(
        (snapshot) => {
          if (!snapshot) {
            return snapshot;
          }

          return updater({
            ...snapshot,
            deadlines: snapshot.deadlines || [],
            projects: snapshot.projects || [],
            progress: normalizeProgress(snapshot.progress),
          });
        },
        { userId }
      );
    },
    [userId]
  );

  useEffect(() => {
    if (!userId) {
      return undefined;
    }

    return subscribeDashboardSnapshot((snapshot) => {
      applySnapshot(snapshot);
    });
  }, [applySnapshot, userId]);

  useEffect(() => {
    if (!userId || !isActive || hasLoadedRef.current) {
      return undefined;
    }

    let cancelled = false;
    setLoadingData(true);

    loadDashboardSnapshot({ userId })
      .then((snapshot) => {
        if (cancelled) {
          return;
        }

        applySnapshot(snapshot);
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }

        setLoadingData(false);
        setToast({
          message: error.message || "Failed to load your progress. Please try again.",
          type: "error",
        });
      });

    return () => {
      cancelled = true;
    };
  }, [applySnapshot, isActive, userId]);

  useEffect(() => {
    if (previousUserIdRef.current === userId) {
      return;
    }

    previousUserIdRef.current = userId;

    const nextSnapshot = getCachedDashboardSnapshot({ userId });
    const nextHasProgress = Boolean(nextSnapshot?.progress);

    hasLoadedRef.current = nextHasProgress;
    setProgress(normalizeProgress(nextSnapshot?.progress));
    setLoadingData(Boolean(isActive && !nextHasProgress));
    setDeadlineActionState({});
    setProjectActionState({});
    setRescheduleDeadlineId(null);
  }, [isActive, userId]);

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
      const normalizedDeadline = normalizeDeadline(deadline);
      const isRestore = nextStatus === "pending";
      const optimisticDeadline = normalizeDeadline({
        ...normalizedDeadline,
        status: nextStatus,
        status_changed_at:
          nextStatus === "done"
            ? new Date().toISOString()
            : normalizedDeadline.status_changed_at,
      });

      setDeadlineActionState((current) => ({
        ...current,
        [deadline.id]: true,
      }));

      if (isRestore) {
        mutateSharedSnapshot((snapshot) => ({
          ...snapshot,
          deadlines: upsertById(
            snapshot.deadlines,
            optimisticDeadline,
            sortDashboardDeadlines
          ),
          progress: {
            ...snapshot.progress,
            deadlines: snapshot.progress.deadlines.filter(
              (item) => item.id !== deadline.id
            ),
          },
        }));
      } else {
        mutateSharedSnapshot((snapshot) => ({
          ...snapshot,
          progress: {
            ...snapshot.progress,
            deadlines: upsertById(
              snapshot.progress.deadlines,
              optimisticDeadline,
              sortProgressDeadlines
            ),
          },
        }));
      }

      try {
        const updatedDeadline = normalizeDeadline(
          await updateDeadlineStatus(deadline.id, nextStatus)
        );

        if (isRestore) {
          mutateSharedSnapshot((snapshot) => ({
            ...snapshot,
            deadlines: upsertById(
              snapshot.deadlines,
              updatedDeadline,
              sortDashboardDeadlines
            ),
            progress: {
              ...snapshot.progress,
              deadlines: snapshot.progress.deadlines.filter(
                (item) => item.id !== deadline.id
              ),
            },
          }));
        } else {
          mutateSharedSnapshot((snapshot) => ({
            ...snapshot,
            progress: {
              ...snapshot.progress,
              deadlines: upsertById(
                snapshot.progress.deadlines,
                updatedDeadline,
                sortProgressDeadlines
              ),
            },
          }));
        }
      } catch (error) {
        if (isRestore) {
          mutateSharedSnapshot((snapshot) => ({
            ...snapshot,
            deadlines: snapshot.deadlines.filter((item) => item.id !== deadline.id),
            progress: {
              ...snapshot.progress,
              deadlines: upsertById(
                snapshot.progress.deadlines,
                normalizedDeadline,
                sortProgressDeadlines
              ),
            },
          }));
        } else {
          mutateSharedSnapshot((snapshot) => ({
            ...snapshot,
            progress: {
              ...snapshot.progress,
              deadlines: upsertById(
                snapshot.progress.deadlines,
                normalizedDeadline,
                sortProgressDeadlines
              ),
            },
          }));
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
    [mutateSharedSnapshot, updateDeadlineStatus]
  );

  const handleProjectStatusChange = useCallback(
    async (project, nextStatus) => {
      const normalizedProject = normalizeProject(project);
      const optimisticProject = normalizeProject({
        ...normalizedProject,
        status: nextStatus,
      });

      setProjectActionState((current) => ({
        ...current,
        [project.id]: true,
      }));

      mutateSharedSnapshot((snapshot) => ({
        ...snapshot,
        projects: upsertById(
          snapshot.projects,
          optimisticProject,
          sortDashboardProjects
        ),
        progress: {
          ...snapshot.progress,
          projects: snapshot.progress.projects.filter(
            (item) => item.id !== project.id
          ),
        },
      }));

      try {
        const updatedProject = normalizeProject(
          await updateProjectStatus(project.id, nextStatus)
        );

        mutateSharedSnapshot((snapshot) => ({
          ...snapshot,
          projects: upsertById(
            snapshot.projects,
            updatedProject,
            sortDashboardProjects
          ),
          progress: {
            ...snapshot.progress,
            projects: snapshot.progress.projects.filter(
              (item) => item.id !== project.id
            ),
          },
        }));
      } catch (error) {
        mutateSharedSnapshot((snapshot) => ({
          ...snapshot,
          projects: snapshot.projects.filter((item) => item.id !== project.id),
          progress: {
            ...snapshot.progress,
            projects: upsertById(
              snapshot.progress.projects,
              normalizedProject,
              sortProgressProjects
            ),
          },
        }));

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
    [mutateSharedSnapshot, updateProjectStatus]
  );

  const handleRescheduleSave = useCallback(
    async (deadline, nextDueDate) => {
      const normalizedDeadline = normalizeDeadline(deadline);
      const optimisticPendingDeadline = normalizeDeadline({
        ...normalizedDeadline,
        due_date: nextDueDate,
        status: "pending",
      });
      let rollbackDeadline = normalizedDeadline;

      setDeadlineActionState((current) => ({
        ...current,
        [deadline.id]: true,
      }));
      setRescheduleDeadlineId(null);

      mutateSharedSnapshot((snapshot) => ({
        ...snapshot,
        deadlines: upsertById(
          snapshot.deadlines,
          optimisticPendingDeadline,
          sortDashboardDeadlines
        ),
        progress: {
          ...snapshot.progress,
          deadlines: snapshot.progress.deadlines.filter(
            (item) => item.id !== deadline.id
          ),
        },
      }));

      try {
        const dateUpdatedDeadline = normalizeDeadline(
          await updateDeadlineDate(deadline.id, nextDueDate)
        );
        rollbackDeadline = dateUpdatedDeadline;

        const statusUpdatedDeadline = normalizeDeadline(
          await updateDeadlineStatus(deadline.id, "pending")
        );
        const reconciledDeadline = normalizeDeadline({
          ...dateUpdatedDeadline,
          ...statusUpdatedDeadline,
          due_date: statusUpdatedDeadline.due_date || dateUpdatedDeadline.due_date,
        });

        mutateSharedSnapshot((snapshot) => ({
          ...snapshot,
          deadlines: upsertById(
            snapshot.deadlines,
            reconciledDeadline,
            sortDashboardDeadlines
          ),
          progress: {
            ...snapshot.progress,
            deadlines: snapshot.progress.deadlines.filter(
              (item) => item.id !== deadline.id
            ),
          },
        }));
      } catch (error) {
        mutateSharedSnapshot((snapshot) => ({
          ...snapshot,
          deadlines: snapshot.deadlines.filter((item) => item.id !== deadline.id),
          progress: {
            ...snapshot.progress,
            deadlines: upsertById(
              snapshot.progress.deadlines,
              rollbackDeadline,
              sortProgressDeadlines
            ),
          },
        }));

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
    [mutateSharedSnapshot, updateDeadlineDate, updateDeadlineStatus]
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

  return (
    <AnimatedView viewKey="progress" isActive={isActive}>
      {loadingData ? (
        <div className="progress-loading">
          <span className="spinner" />
          <p>Loading your progress...</p>
        </div>
      ) : (
        <div className="progress-page">
          <header className="progress-header">
            <div>
              <p className="progress-kicker">My Progress</p>
              <h2 className="progress-title">
                A warm look at what you moved forward.
              </h2>
            </div>
            <p className="progress-subtitle">
              What&apos;s ahead lives on the dashboard. This is the quieter page
              for what you finished, what slipped, and what still counts.
            </p>
          </header>

          <div className="progress-sections">
            <motion.section
              className="progress-section"
              {...sectionMotionProps(0)}
            >
              <div className="progress-section-header">
                <div className="progress-section-heading">
                  <h3>Things I Got Done</h3>
                  <p>Proof that follow-through happened.</p>
                </div>
              </div>

              {doneGroups.length === 0 ? (
                <SectionEmpty
                  tone="sage"
                  message="Nothing here yet — your first completed deadline will show up here."
                />
              ) : (
                doneGroups.map((group) => (
                  <div key={group.key} className="progress-group">
                    <div className="progress-group-divider">
                      <span>{group.label}</span>
                    </div>
                    <div className="progress-item-list">
                      {group.items.map((deadline) => {
                        const isUpdating = Boolean(deadlineActionState[deadline.id]);
                        const dueLabel = formatDueNarrative(deadline.due_date);

                        return (
                          <article
                            key={deadline.id}
                            className="progress-item progress-item-done"
                          >
                            <div className="progress-item-main">
                              <h4 className="progress-item-title">
                                {deadline.description}
                              </h4>
                              <p className="progress-item-summary">
                                {formatDoneNarrative(deadline.status_changed_at)}
                              </p>
                              {dueLabel ? (
                                <p className="progress-item-secondary">{dueLabel}</p>
                              ) : null}
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
                          </article>
                        );
                      })}
                    </div>
                  </div>
                ))
              )}
            </motion.section>

            <motion.section
              className="progress-section missed"
              {...sectionMotionProps(0.04)}
            >
              <div className="progress-section-header">
                <div className="progress-section-heading">
                  <h3>Ones That Slipped</h3>
                  <p>Honest, useful, and still easy to move forward.</p>
                </div>
              </div>

              {missedGroups.length === 0 ? (
                <SectionEmpty
                  tone="warm"
                  message="Nothing has slipped lately — and if something does, it will show up here without judgment."
                />
              ) : (
                missedGroups.map((group) => (
                  <div key={group.key} className="progress-group">
                    <div className="progress-group-divider">
                      <span>{group.label}</span>
                    </div>
                    <div className="progress-item-list">
                      {group.items.map((deadline) => {
                        const isUpdating = Boolean(deadlineActionState[deadline.id]);
                        const dueLabel = formatDueNarrative(
                          deadline.due_date,
                          "Was due"
                        );

                        return (
                          <article
                            key={deadline.id}
                            className="progress-item progress-item-missed"
                          >
                            <div className="progress-item-main">
                              <h4 className="progress-item-title">
                                {deadline.description}
                              </h4>
                              <p className="progress-item-summary">
                                {formatMissedNarrative(deadline.status_changed_at)}
                              </p>
                              {dueLabel ? (
                                <p className="progress-item-secondary">{dueLabel}</p>
                              ) : null}
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
                          </article>
                        );
                      })}
                    </div>
                  </div>
                ))
              )}
            </motion.section>

            <motion.section
              className="progress-section projects"
              {...sectionMotionProps(0.08)}
            >
              <div className="progress-section-header">
                <div className="progress-section-heading">
                  <h3>Projects I Finished</h3>
                  <p>Big or small, this is the shipped pile.</p>
                </div>
              </div>

              {projectGroups.length === 0 ? (
                <SectionEmpty
                  tone="sage"
                  message="No finished projects yet — completed projects will collect here as your shipped pile grows."
                />
              ) : (
                projectGroups.map((group) => (
                  <div key={group.key} className="progress-group">
                    <div className="progress-group-divider">
                      <span>{group.label}</span>
                    </div>
                    <div className="progress-item-list">
                      {group.items.map((project) => {
                        const isUpdating = Boolean(projectActionState[project.id]);
                        const mentionLabel = formatMentionNarrative(project);

                        return (
                          <article
                            key={project.id}
                            className="progress-item progress-item-project"
                          >
                            <div className="progress-item-main">
                              <h4 className="progress-item-title">{project.name}</h4>
                              <p className="progress-item-summary">
                                {formatFinishedNarrative(project.status_changed_at)}
                              </p>
                              {mentionLabel ? (
                                <p className="progress-item-secondary">
                                  {mentionLabel}
                                </p>
                              ) : null}
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
                          </article>
                        );
                      })}
                    </div>
                  </div>
                ))
              )}
            </motion.section>
          </div>
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
