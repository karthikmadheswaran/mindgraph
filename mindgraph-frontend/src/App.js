import { useState, useEffect, useRef } from "react";
import { supabase } from "./supabaseClient";
import LandingPage from "./components/LandingPage";
import AuthView from "./components/AuthView";
import Sidebar from "./components/Sidebar";
import InputView from "./components/InputView";
import Dashboard from "./components/Dashboard";
import AskView from "./components/AskView";
import "./styles/variables.css";
import "./styles/global.css";
import "./styles/app-shell.css";
import "./styles/responsive.css";

export default function App() {
  const [session, setSession] = useState(null);
  const [view, setView] = useState("landing");
  const [currentView, setCurrentView] = useState("write");
  const [hasVisitedDashboard, setHasVisitedDashboard] = useState(false);
  const dashboardRef = useRef(null);

  const handlePublicBrandClick = () => {
    setView("landing");
  };

  const handleAppBrandClick = () => {
    setCurrentView("dashboard");
  };

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      if (session) {
        setCurrentView("write");
        setView("app");
      }
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      setSession(session);
      if (session) {
        if (event === "SIGNED_IN") {
          setCurrentView("write");
        }
        setView("app");
      }
      else setView("landing");
    });

    return () => subscription.unsubscribe();
  }, []);

  const handleLogout = async () => {
    await supabase.auth.signOut();
  };

  useEffect(() => {
    if (currentView === "dashboard") {
      setHasVisitedDashboard(true);
    }
  }, [currentView]);

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
          onAuth={(session) => {
            setSession(session);
            setCurrentView("write");
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
            onViewChange={setCurrentView}
            userEmail={session.user?.email}
            onLogout={handleLogout}
            onBrandClick={handleAppBrandClick}
          />

          <main className="main-content">
            <div style={{ display: currentView === "write" ? "block" : "none" }}>
              <InputView
                isActive={currentView === "write"}
                onEntrySubmitted={() => dashboardRef.current?.triggerRefresh()}
              />
            </div>
            {hasVisitedDashboard && (
              <div
                style={{ display: currentView === "dashboard" ? "block" : "none" }}
              >
                <Dashboard
                  ref={dashboardRef}
                  isActive={currentView === "dashboard"}
                />
              </div>
            )}
            <div style={{ display: currentView === "ask" ? "block" : "none" }}>
              <AskView isActive={currentView === "ask"} />
            </div>
          </main>
        </div>
      )}
    </>
  );
}
