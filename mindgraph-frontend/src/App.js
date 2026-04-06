import { useState, useEffect } from "react";
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
  const [currentView, setCurrentView] = useState("dashboard");

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
        <div className="app-layout">
          <Sidebar
            currentView={currentView}
            onViewChange={setCurrentView}
            userEmail={session.user?.email}
            onLogout={handleLogout}
          />

          <main className="main-content">
            {currentView === "write" && <InputView />}
            {currentView === "dashboard" && <Dashboard />}
            {currentView === "ask" && <AskView />}
          </main>
        </div>
      )}
    </>
  );
}
