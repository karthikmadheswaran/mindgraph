import { useCallback, useEffect, useRef, useState } from "react";
import { supabase } from "./supabaseClient";
import { API, authHeaders } from "./utils/auth";
import { identifyUser, resetUser, trackEvent } from "./posthog";
import {
  clearDashboardSnapshotCache,
  loadDashboardSnapshot,
  prefetchDashboardSnapshot,
  updateDashboardSnapshot,
} from "./utils/dashboardSnapshot";
import { installInviteGate, INVITE_ONLY_EVENT } from "./utils/inviteGate";
import LandingPage from "./components/LandingPage";
import AuthView from "./components/AuthView";
import InviteOnlyView from "./components/InviteOnlyView";
import Sidebar from "./components/Sidebar";
import Journal from "./components/Journal";
import AskView from "./components/AskView";
import KnowledgeGraphView from "./components/KnowledgeGraphView";
import Home from "./components/Home";
import "./styles/variables.css";
import "./styles/global.css";
import "./styles/app-shell.css";
import "./styles/responsive.css";

// Capture-first IA: "home" absorbed the old "write" view and "journal"
// replaced "dashboard" (Today). Legacy #write / #dashboard / #/progress
// hashes fall through normalizeHashView to the default, which is home.
const APP_VIEWS = new Set(["home", "journal", "ask", "graph"]);
const DEFAULT_APP_VIEW = "home";

const normalizeHashView = (hashValue) => {
  const hash = String(hashValue || "")
    .replace(/^#/, "")
    .trim()
    .toLowerCase();
  const normalizedHash = hash.startsWith("/") ? hash.slice(1) : hash;

  return APP_VIEWS.has(normalizedHash) ? normalizedHash : DEFAULT_APP_VIEW;
};

const formatHashView = (view) => `#${view}`;

const isHashForView = (hashValue, view) => {
  const normalizedHash = String(hashValue || "").trim().toLowerCase();
  return (
    normalizedHash === `#${view}` || normalizedHash === `#/${view}`
  );
};

const getHashView = () => {
  return normalizeHashView(window.location.hash);
};

const shouldStartOnAuth = () => {
  return (
    new URLSearchParams(window.location.search).get("view") === "auth"
  );
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

const clearAuthViewSearch = () => {
  const params = new URLSearchParams(window.location.search);

  if (params.get("view") !== "auth") {
    return;
  }

  params.delete("view");

  const nextSearch = params.toString();
  const nextUrl = `${window.location.pathname}${
    nextSearch ? `?${nextSearch}` : ""
  }${window.location.hash}`;

  window.history.replaceState(
    null,
    "",
    nextUrl
  );
};

const hasProcessingEntries = (entries = []) =>
  entries.some((entry) => entry.status === "processing");

installInviteGate();

export default function App() {
  const initialAppView = getHashView();
  const [session, setSession] = useState(null);
  const [view, setView] = useState(
    shouldStartOnAuth() ? "auth" : "landing"
  );
  const [currentView, setCurrentView] = useState(initialAppView);
  const [hasVisitedJournal, setHasVisitedJournal] = useState(
    initialAppView === "journal"
  );
  const [inviteBlocked, setInviteBlocked] = useState(false);

  useEffect(() => {
    const handleInviteOnly = () => setInviteBlocked(true);
    window.addEventListener(INVITE_ONLY_EVENT, handleInviteOnly);
    return () => window.removeEventListener(INVITE_ONLY_EVENT, handleInviteOnly);
  }, []);

  const hasBootstrappedAuthViewRef = useRef(false);
  const activeUserIdRef = useRef(null);
  const authIntentRef = useRef(shouldStartOnAuth());
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

    if (normalizedView === "journal") {
      setHasVisitedJournal(true);
    }

    return normalizedView;
  }, []);

  const navigateToAppView = useCallback((nextView) => {
    const normalizedView = setHashView(nextView);
    setCurrentView(normalizedView);

    if (normalizedView === "journal") {
      setHasVisitedJournal(true);
    }
  }, []);

  const startBackgroundEntriesPolling = useCallback((userId) => {
    if (!userId || hasVisitedJournal || backgroundEntriesPollRef.current) {
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
          const recentCompleted = nextEntries
            .filter((e) => e.status === "completed" && e.created_at)
            .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0];
          if (recentCompleted) {
            trackEvent("entry_pipeline_complete", {
              processing_time_ms: Date.now() - new Date(recentCompleted.created_at).getTime(),
            });
          }
          stopBackgroundEntriesPolling();
          await loadDashboardSnapshot({ force: true, userId });
        }
      } catch {
        // silently fail
      }
    }, 4000);
  }, [hasVisitedJournal, stopBackgroundEntriesPolling]);

  const syncBackgroundEntriesPolling = useCallback((entries, userId) => {
    if (hasVisitedJournal || !hasProcessingEntries(entries)) {
      stopBackgroundEntriesPolling();
      return;
    }

    startBackgroundEntriesPolling(userId);
  }, [hasVisitedJournal, startBackgroundEntriesPolling, stopBackgroundEntriesPolling]);

  const handlePublicBrandClick = () => {
    authIntentRef.current = false;
    clearAuthViewSearch();
    setView("landing");
  };

  const handleAppBrandClick = () => {
    navigateToAppView("home");
  };

  useEffect(() => {
    const handleHashChange = () => {
      const normalizedView = getHashView();

      if (
        window.location.hash &&
        !isHashForView(window.location.hash, normalizedView)
      ) {
        setHashView(normalizedView, { replace: true });
      }

      setCurrentView(normalizedView);

      if (normalizedView === "journal") {
        setHasVisitedJournal(true);
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
      resetUser();
      clearHashView();
      setSession(null);
      setInviteBlocked(false);

      // If the user arrived via ?view=auth (e.g. "Try the App" CTA), show
      // the auth screen instead of bouncing back to the landing page.
      // This handles the expired-session flow: Supabase finds a stale
      // token in storage → handleSignedIn fires → then the token is
      // invalidated → onAuthStateChange fires with null → we land here.
      // Without this guard the user sees the landing page again instead
      // of the sign-in form they intended to reach.
      if (authIntentRef.current) {
        authIntentRef.current = false;   // consume once
        setView("auth");
      } else {
        setView("landing");
      }

      setCurrentView(DEFAULT_APP_VIEW);
      setHasVisitedJournal(false);
    };

    const handleSignedIn = (nextSession) => {
      const nextUserId = nextSession.user?.id || null;

      if (activeUserIdRef.current && activeUserIdRef.current !== nextUserId) {
        clearDashboardSnapshotCache();
        setHasVisitedJournal(false);
      }

      activeUserIdRef.current = nextUserId;
      if (nextUserId) identifyUser(nextUserId);
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
      }
      // If no session on initial mount, do NOT call handleSignedOut() —
      // it would override the initial view state (which may be "auth"
      // from ?view=auth) back to "landing". The useState initializer
      // already has the correct value. Actual sign-out events are
      // handled by onAuthStateChange below.
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      if (!isMounted) {
        return;
      }

      if (nextSession) {
        handleSignedIn(nextSession);
      } else if (activeUserIdRef.current) {
        // Only reset to landing when transitioning from signed-in →
        // signed-out (activeUserIdRef was set by handleSignedIn).
        // On initial mount with no session, activeUserIdRef is null,
        // so we skip this — preserving the useState initializer value
        // ("auth" from ?view=auth, or "landing").
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
    if (currentView === "journal") {
      setHasVisitedJournal(true);
    }
  }, [currentView]);

  useEffect(() => {
    if (currentView === "graph") trackEvent("graph_viewed");
  }, [currentView]);

  useEffect(() => {
    if (hasVisitedJournal) {
      stopBackgroundEntriesPolling();
    }
  }, [hasVisitedJournal, stopBackgroundEntriesPolling]);

  useEffect(() => {
    const userId = session?.user?.id;

    if (view !== "app" || !userId || hasVisitedJournal) {
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
    hasVisitedJournal,
    session?.user?.id,
    stopBackgroundEntriesPolling,
    syncBackgroundEntriesPolling,
    view,
  ]);

  const handleLogout = async () => {
    authIntentRef.current = false;
    clearAuthViewSearch();
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
            authIntentRef.current = false;
            clearAuthViewSearch();
            clearDashboardSnapshotCache();
            activeUserIdRef.current = nextSession.user?.id || null;
            hasBootstrappedAuthViewRef.current = true;
            setSession(nextSession);
            setHasVisitedJournal(false);
            setCurrentView(setHashView(DEFAULT_APP_VIEW, { replace: true }));
            setView("app");
          }}
          onBack={() => {
            authIntentRef.current = false;
            clearAuthViewSearch();
            setView("landing");
          }}
          onBrandClick={handlePublicBrandClick}
        />
      )}

      {view === "app" && session && inviteBlocked && (
        <InviteOnlyView userEmail={session.user?.email} onLogout={handleLogout} />
      )}

      {view === "app" && session && !inviteBlocked && (
        <div className="app-layout">
          <Sidebar
            currentView={currentView}
            onViewChange={navigateToAppView}
            userEmail={session.user?.email}
            onLogout={handleLogout}
            onBrandClick={handleAppBrandClick}
          />

          <main className={`main-content${currentView === "home" ? " main-content--home" : ""}`}>
            {hasVisitedJournal && (
              <div
                style={{ display: currentView === "journal" ? "block" : "none" }}
              >
                <Journal
                  key={session.user?.id || session.user?.email}
                  isActive={currentView === "journal"}
                  userId={session.user?.id}
                />
              </div>
            )}
            <div style={{ display: currentView === "graph" ? "block" : "none" }}>
              <KnowledgeGraphView isActive={currentView === "graph"} />
            </div>
            <div style={{ display: currentView === "ask" ? "block" : "none" }}>
              <AskView isActive={currentView === "ask"} />
            </div>
            <div style={{ display: currentView === "home" ? "block" : "none" }}>
              <Home
                isActive={currentView === "home"}
                onNavigate={navigateToAppView}
              />
            </div>
          </main>
        </div>
      )}
    </>
  );
}
