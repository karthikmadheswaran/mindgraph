import { useState, useEffect } from "react";
import { supabase } from "./supabaseClient";
import LandingPage from "./components/LandingPage";
import AuthView from "./components/AuthView";
import InputView from "./components/InputView";
import Dashboard from "./components/Dashboard";
import "./styles/variables.css";
import "./styles/global.css";
import "./styles/app-shell.css";
import "./styles/responsive.css";

export default function App() {
  const [session, setSession] = useState(null);
  const [view, setView] = useState("landing");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      if (session) setView("app");
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      if (session) setView("app");
      else setView("landing");
    });

    return () => subscription.unsubscribe();
  }, []);

  const handleLogout = async () => {
    await supabase.auth.signOut();
  };

  return (
    <>
      {view === "landing" && (
        <LandingPage onGetStarted={() => setView("auth")} />
      )}

      {view === "auth" && (
        <AuthView
          onAuth={(session) => {
            setSession(session);
            setView("app");
          }}
          onBack={() => setView("landing")}
        />
      )}

      {view === "app" && session && (
        <div className="app-shell">
          <div className="topbar">
            <div className="brand">MindGraph</div>

            <div className="topbar-right">
              <div className="nav-toggle">
                <button
                  className={`nav-btn ${view === "app" ? "active" : ""}`}
                  onClick={() => setView("app")}
                >
                  Dashboard
                </button>
              </div>

              <div className="user-email">{session.user?.email}</div>

              <button className="logout-btn" onClick={handleLogout}>
                Log out
              </button>
            </div>
          </div>

          <InputView />
          <div style={{ height: 20 }} />
          <Dashboard refreshKey={refreshKey} />
        </div>
      )}
    </>
  );
}
