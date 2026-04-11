import { useCallback, useEffect, useRef, useState } from "react";
import { supabase } from "./supabaseClient";
import { API, authHeaders } from "./utils/auth";
import {
  clearDashboardSnapshotCache,
  loadDashboardSnapshot,
  prefetchDashboardSnapshot,
  updateDashboardSnapshot,
} from "./utils/dashboardSnapshot";
import LandingPage from "./components/LandingPage";
import AuthView from "./components/AuthView";
import Sidebar from "./components/Sidebar";
import InputView from "./components/InputView";
import Dashboard from "./components/Dashboard";
import MyProgress from "./components/MyProgress";
import AskView from "./components/AskView";
import KnowledgeGraphView from "./components/KnowledgeGraphView";
import "./styles/variables.css";
import "./styles/global.css";
import "./styles/app-shell.css";
import "./styles/responsive.css";

const APP_VIEWS = new Set(["ask", "write", "dashboard", "graph", "progress"]);
const DEFAULT_APP_VIEW = "ask";

const normalizeHashView = (hashValue) => {
  const hash = String(hashValue || "")
    .replace(/^#/, "")
    .trim()
    .toLowerCase();
  const normalizedHash = hash.startsWith("/") ? hash.slice(1) : hash;

  return APP_VIEWS.has(normalizedHash) ? normalizedHash : DEFAULT_APP_VIEW;
};

const formatHashView = (view) =>
  view === "progress" ? "#/progress" : `#${view}`;

const isHashForView = (hashValue, view) => {
  const normalizedHash = String(hashValue || "").trim().toLowerCase();
  return (
    normalizedHash === `#${view}` || normalizedHash === `#/${view}`
  );
};

const getHashView = () => {
  return normalizeHashView(window.location.hash);
};

const setHashView = (nextView, { replace = false } = {}) => {
  const normalizedView = APP_VIEWS.has(nextView) ? nextView : DEFAULT_APP_VIEW;
  const nextHash = formatHashView(normalizedView);

  if (replace) {
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${window.location.search}${nextHash}`
    );
  } else if (window.location.hash !== nextHash) {
    window.location.hash = nextHash;
  }

  return normalizedView;
};

const clearHashView = () => {
  window.history.replaceState(
    null,
    "",
    `${window.location.pathname}${window.location.search}`
  );
};

const hasProcessingEntries = (entries = []) =>
  entries.some((entry) => entry.status === "processing");

export default function App() {
  const initialAppView = getHashView();
  const [session, setSession] = useState(null);
  const [view, setView] = useState("landing");
  const [currentView, setCurrentView] = useState(initialAppView);
  const [hasVisitedDashboard, setHasVisitedDashboard] = useState(
    initialAppView === "dashboard"
  );

  const hasBootstrappedAuthViewRef = useRef(false);
  const activeUserIdRef = useRef(null);
  const backgroundEntriesPollRef = useRef(null);

  const stopBackgroundEntriesPolling = useCallback(() => {
    if (backgroundEntriesPollRef.current) {
      clearInterval(backgroundEntriesPollRef.current);
      backgroundEntriesPollRef.current = null;
    }
  }, []);

  const syncCurrentViewFromHash = useCallback((replaceInvalid = false) => {
    const normalizedView = getHashView();

    if (replaceInvalid || !isHashForView(window.location.hash, normalizedView)) {
      setHashView(normalizedView, { replace: true });
    }

    setCurrentView(normalizedView);

    if (normalizedView === "dashboard") {
      setHasVisitedDashboard(true);
    }

    return normalizedView;
  }, []);

  const navigateToAppView = useCallback((nextView) => {
    const normalizedView = setHashView(nextView);
    setCurrentView(normalizedView);

    if (normalizedView === "dashboard") {
      setHasVisitedDashboard(true);
    }
  }, []);

  const startBackgroundEntriesPolling = useCallback((userId) => {
    if (!userId || hasVisitedDashboard || backgroundEntriesPollRef.current) {
      return;
    }

    backgroundEntriesPollRef.current = setInterval(async () => {
      try {
        const headers = await authHeaders();
        const data = await fetch(`${API}/entries`, { headers }).then((response) =>
          response.json()
        );
        const nextEntries = data.entries || [];

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

        if (!hasProcessingEntries(nextEntries)) {
          stopBackgroundEntriesPolling();
          await loadDashboardSnapshot({ force: true, userId });
        }
      } catch {
        // silently fail
      }
    }, 4000);
  }, [hasVisitedDashboard, stopBackgroundEntriesPolling]);

  const syncBackgroundEntriesPolling = useCallback((entries, userId) => {
    if (hasVisitedDashboard || !hasProcessingEntries(entries)) {
      stopBackgroundEntriesPolling();
      return;
    }

    startBackgroundEntriesPolling(userId);
  }, [hasVisitedDashboard, startBackgroundEntriesPolling, stopBackgroundEntriesPolling]);

  const handlePublicBrandClick = () => {
    setView("landing");
  };

  const handleAppBrandClick = () => {
    navigateToAppView("ask");
  };

  const handleEntrySubmitted = useCallback(() => {
    const userId = session?.user?.id;

    if (!userId) {
      return;
    }

    loadDashboardSnapshot({ force: true, userId })
      .then((snapshot) => {
        if (!hasVisitedDashboard) {
          syncBackgroundEntriesPolling(snapshot?.entries || [], userId);
        }
      })
      .catch(() => {
        // silently fail
      });
  }, [hasVisitedDashboard, session?.user?.id, syncBackgroundEntriesPolling]);

  useEffect(() => {
    const handleHashChange = () => {
      const normalizedView = getHashView();
      setCurrentView(normalizedView);

      if (normalizedView === "dashboard") {
        setHasVisitedDashboard(true);
      }
    };

    handleHashChange();
    window.addEventListener("hashchange", handleHashChange);

    return () => {
      window.removeEventListener("hashchange", handleHashChange);
    };
  }, []);

  useEffect(() => {
    let isMounted = true;

    const handleSignedOut = () => {
      activeUserIdRef.current = null;
      hasBootstrappedAuthViewRef.current = false;
      stopBackgroundEntriesPolling();
      clearDashboardSnapshotCache();
      clearHashView();
      setSession(null);
      setView("landing");
      setCurrentView(DEFAULT_APP_VIEW);
      setHasVisitedDashboard(false);
    };

    const handleSignedIn = (nextSession) => {
      const nextUserId = nextSession.user?.id || null;

      if (activeUserIdRef.current && activeUserIdRef.current !== nextUserId) {
        clearDashboardSnapshotCache();
        setHasVisitedDashboard(false);
      }

      activeUserIdRef.current = nextUserId;
      setSession(nextSession);
      setView("app");

      if (!hasBootstrappedAuthViewRef.current) {
        hasBootstrappedAuthViewRef.current = true;
        syncCurrentViewFromHash(true);
      }
    };

    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!isMounted) {
        return;
      }

      if (session) {
        handleSignedIn(session);
      } else {
        handleSignedOut();
      }
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, nextSession) => {
      if (!isMounted) {
        return;
      }

      if (nextSession) {
        handleSignedIn(nextSession);
      } else {
        handleSignedOut();
      }
    });

    return () => {
      isMounted = false;
      stopBackgroundEntriesPolling();
      subscription.unsubscribe();
    };
  }, [stopBackgroundEntriesPolling, syncCurrentViewFromHash]);

  useEffect(() => {
    if (currentView === "dashboard") {
      setHasVisitedDashboard(true);
    }
  }, [currentView]);

  useEffect(() => {
    if (hasVisitedDashboard) {
      stopBackgroundEntriesPolling();
    }
  }, [hasVisitedDashboard, stopBackgroundEntriesPolling]);

  useEffect(() => {
    const userId = session?.user?.id;

    if (view !== "app" || !userId || hasVisitedDashboard) {
      stopBackgroundEntriesPolling();
      return undefined;
    }

    let cancelled = false;

    prefetchDashboardSnapshot({ userId })
      .then((snapshot) => {
        if (cancelled) {
          return;
        }

        syncBackgroundEntriesPolling(snapshot?.entries || [], userId);
      })
      .catch(() => {
        // prefetch failures should not block the app shell
      });

    return () => {
      cancelled = true;
      stopBackgroundEntriesPolling();
    };
  }, [
    hasVisitedDashboard,
    session?.user?.id,
    stopBackgroundEntriesPolling,
    syncBackgroundEntriesPolling,
    view,
  ]);

  const handleLogout = async () => {
    await supabase.auth.signOut();
  };

  return (
    <>
      {view === "landing" && (
        <LandingPage
          onGetStarted={() => setView("auth")}
          onBrandClick={handlePublicBrandClick}
        />
      )}

      {view === "auth" && (
        <AuthView
          onAuth={(nextSession) => {
            clearDashboardSnapshotCache();
            activeUserIdRef.current = nextSession.user?.id || null;
            hasBootstrappedAuthViewRef.current = true;
            setSession(nextSession);
            setHasVisitedDashboard(false);
            setCurrentView(setHashView(DEFAULT_APP_VIEW, { replace: true }));
            setView("app");
          }}
          onBack={() => setView("landing")}
          onBrandClick={handlePublicBrandClick}
        />
      )}

      {view === "app" && session && (
        <div className="app-layout">
          <Sidebar
            currentView={currentView}
            onViewChange={navigateToAppView}
            userEmail={session.user?.email}
            onLogout={handleLogout}
            onBrandClick={handleAppBrandClick}
          />

          <main className="main-content">
            <div style={{ display: currentView === "write" ? "block" : "none" }}>
              <InputView
                isActive={currentView === "write"}
                onEntrySubmitted={handleEntrySubmitted}
              />
            </div>
            {hasVisitedDashboard && (
              <div
                style={{ display: currentView === "dashboard" ? "block" : "none" }}
              >
                <Dashboard
                  key={session.user?.id || session.user?.email}
                  isActive={currentView === "dashboard"}
                  userId={session.user?.id}
                />
              </div>
            )}
            <div style={{ display: currentView === "progress" ? "block" : "none" }}>
              <MyProgress
                isActive={currentView === "progress"}
                userId={session.user?.id}
              />
            </div>
            <div style={{ display: currentView === "graph" ? "block" : "none" }}>
              <KnowledgeGraphView isActive={currentView === "graph"} />
            </div>
            <div style={{ display: currentView === "ask" ? "block" : "none" }}>
              <AskView isActive={currentView === "ask"} />
            </div>
          </main>
        </div>
      )}
    </>
  );
}
