import { API, authHeaders } from "./auth";

let cachedSnapshot = null;
let cachedUserId = null;
let inFlightPromise = null;
let queuedForceRequested = false;
let queuedForcePromise = null;

const listeners = new Set();

const normalizeProgress = (progress = {}) => ({
  deadlines: progress.deadlines || [],
  projects: progress.projects || [],
});

const normalizeStats = (stats = {}) => ({
  total_entries: Number(stats.total_entries) || 0,
  entries_this_week: Number(stats.entries_this_week) || 0,
  active_projects: Number(stats.active_projects) || 0,
  completed_projects: Number(stats.completed_projects) || 0,
  entities_tracked: Number(stats.entities_tracked) || 0,
});

const normalizeTagline = (tagline = {}) => ({
  text: typeof tagline.text === "string" ? tagline.text : "",
  cached: Boolean(tagline.cached),
});

const normalizeSnapshot = (snapshot = {}) => ({
  entries: snapshot.entries || [],
  deadlines: snapshot.deadlines || [],
  projects: snapshot.projects || [],
  entities: snapshot.entities || [],
  relations: snapshot.relations || [],
  patterns: snapshot.patterns || {},
  progress: normalizeProgress(snapshot.progress),
  stats: normalizeStats(snapshot.stats),
  tagline: normalizeTagline(snapshot.tagline),
});

const getUserTimezone = () => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
};

const stampSnapshot = (snapshot) => ({
  ...normalizeSnapshot(snapshot),
  fetchedAt: Date.now(),
});

const notifyListeners = () => {
  listeners.forEach((listener) => {
    try {
      listener(cachedSnapshot);
    } catch {
      // listeners should not break cache updates
    }
  });
};

const resetCacheState = () => {
  cachedSnapshot = null;
  inFlightPromise = null;
  queuedForceRequested = false;
  queuedForcePromise = null;
};

const syncUserScope = (userId) => {
  const nextUserId = userId || null;

  if (cachedUserId !== nextUserId) {
    cachedUserId = nextUserId;
    resetCacheState();
  }
};

const fetchDashboardSnapshot = async () => {
  const headers = await authHeaders();
  const userTz = encodeURIComponent(getUserTimezone());

  const [
    entriesData,
    deadlinesData,
    projectsData,
    progressData,
    entitiesData,
    relationsData,
    patternsData,
    statsData,
    taglineData,
  ] = await Promise.all([
    fetch(`${API}/entries`, { headers }).then((response) => response.json()),
    fetch(`${API}/deadlines?status=pending,snoozed,missed`, { headers }).then(
      async (response) => {
        if (!response.ok) {
          throw new Error("Failed to fetch deadlines");
        }

        return response.json();
      }
    ),
    fetch(`${API}/projects?status=active,hidden`, { headers }).then(
      async (response) => {
        if (!response.ok) {
          throw new Error("Failed to fetch projects");
        }

        return response.json();
      }
    ),
    fetch(`${API}/progress`, { headers }).then(async (response) => {
      if (!response.ok) {
        throw new Error("Failed to fetch progress");
      }

      return response.json();
    }),
    fetch(`${API}/entities`, { headers }).then((response) => response.json()),
    fetch(`${API}/entity-relations`, { headers })
      .then((response) => response.json())
      .catch(() => ({ relations: [] })),
    fetch(`${API}/insights/patterns`, { headers })
      .then((response) => response.json())
      .catch(() => ({ data: {} })),
    fetch(`${API}/stats/dashboard?user_tz=${userTz}`, { headers })
      .then((response) => (response.ok ? response.json() : {}))
      .catch(() => ({})),
    fetch(`${API}/insights/tagline?user_tz=${userTz}`, { headers })
      .then((response) => (response.ok ? response.json() : {}))
      .catch(() => ({})),
  ]);

  return stampSnapshot({
    entries: entriesData.entries || [],
    deadlines: deadlinesData.deadlines || [],
    projects: projectsData.projects || [],
    progress: normalizeProgress(progressData),
    entities: entitiesData.entities || [],
    relations: relationsData.relations || [],
    patterns: patternsData.data || {},
    stats: statsData,
    tagline: taglineData,
  });
};

const startSnapshotFetch = () => {
  const request = fetchDashboardSnapshot()
    .then((snapshot) => {
      cachedSnapshot = snapshot;
      notifyListeners();
      return snapshot;
    })
    .finally(() => {
      if (inFlightPromise === request) {
        inFlightPromise = null;
      }
    });

  inFlightPromise = request;
  return request;
};

const queueForceRefresh = () => {
  queuedForceRequested = true;

  if (!queuedForcePromise) {
    const waitFor = inFlightPromise || Promise.resolve(cachedSnapshot);

    queuedForcePromise = waitFor
      .catch(() => null)
      .then(() => {
        if (!queuedForceRequested) {
          return cachedSnapshot;
        }

        queuedForceRequested = false;

        if (inFlightPromise) {
          return queueForceRefresh();
        }

        return startSnapshotFetch();
      })
      .finally(() => {
        queuedForcePromise = null;
      });
  }

  return queuedForcePromise;
};

export function getCachedDashboardSnapshot({ userId } = {}) {
  syncUserScope(userId);
  return cachedSnapshot;
}

export function subscribeDashboardSnapshot(listener) {
  listeners.add(listener);

  return () => {
    listeners.delete(listener);
  };
}

export function updateDashboardSnapshot(updater, { userId } = {}) {
  syncUserScope(userId);

  if (!cachedSnapshot) {
    return null;
  }

  const nextSnapshot =
    typeof updater === "function" ? updater(cachedSnapshot) : updater;

  if (!nextSnapshot) {
    return cachedSnapshot;
  }

  cachedSnapshot = {
    ...normalizeSnapshot(nextSnapshot),
    fetchedAt: nextSnapshot.fetchedAt || cachedSnapshot.fetchedAt || Date.now(),
  };

  notifyListeners();
  return cachedSnapshot;
}

export async function loadDashboardSnapshot({ force = false, userId } = {}) {
  syncUserScope(userId);

  if (!force && cachedSnapshot) {
    return cachedSnapshot;
  }

  if (inFlightPromise) {
    return force ? queueForceRefresh() : inFlightPromise;
  }

  if (queuedForcePromise) {
    return force || !cachedSnapshot ? queuedForcePromise : cachedSnapshot;
  }

  return startSnapshotFetch();
}

export function prefetchDashboardSnapshot({ userId } = {}) {
  return loadDashboardSnapshot({ userId });
}

export function clearDashboardSnapshotCache() {
  cachedUserId = null;
  resetCacheState();
  notifyListeners();
}
