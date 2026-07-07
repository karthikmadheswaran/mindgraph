import { useState } from "react";
import SettingsModal from "./SettingsModal";
import "../styles/sidebar.css";

const icons = {
  home: (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3 11.5 12 4l9 7.5" />
      <path d="M5 10.5V20h14v-9.5" />
    </svg>
  ),
  journal: (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  ),
  progress: (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M8 21h8" />
      <path d="M12 17v4" />
      <path d="M7 4h10l-1 5a4 4 0 0 1-4 3 4 4 0 0 1-4-3L7 4Z" />
      <path d="M5 4h14" />
    </svg>
  ),
  ask: (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5A8.48 8.48 0 0 1 21 11v.5z" />
      <path d="M8 10h8" />
      <path d="M8 14h5" />
    </svg>
  ),
  graph: (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="graph-icon"
    >
      <circle cx="6" cy="7" r="3" />
      <circle cx="17" cy="6" r="3" />
      <circle cx="18" cy="17" r="3" />
      <circle cx="7" cy="18" r="3" />
      <path className="graph-edge" d="m9 7 5-.5" />
      <path className="graph-edge" d="m16 9 1.4 5" />
      <path className="graph-edge" d="m15.5 18-5.5.2" />
      <path className="graph-edge" d="m7 15 .2-5" />
    </svg>
  ),
};

export default function Sidebar({
  currentView,
  onViewChange,
  userEmail,
  onLogout,
  onBrandClick,
}) {
  const [settingsOpen, setSettingsOpen] = useState(false);

  const navItems = [
    { id: "home", label: "Home", icon: icons.home },
    { id: "journal", label: "Journal", icon: icons.journal },
    { id: "ask", label: "Ask", icon: icons.ask },
    { id: "graph", label: "Graph", icon: icons.graph },
  ];

  return (
    <>
      <aside className="sidebar">
        <div className="sidebar-top">
          <button
            type="button"
            className="sidebar-brand"
            onClick={onBrandClick}
          >
            <span className="brand-mind">mind</span><span className="brand-graph">graph</span>
          </button>
          <nav className="sidebar-nav" aria-label="Primary">
            {navItems.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`sidebar-nav-item ${
                  currentView === item.id ? "active" : ""
                }`}
                onClick={() => onViewChange(item.id)}
              >
                <span className="sidebar-nav-icon">{item.icon}</span>
                <span className="sidebar-nav-label">{item.label}</span>
              </button>
            ))}
          </nav>
        </div>

        <div className="sidebar-bottom">
          <div className="sidebar-email" title={userEmail}>
            {userEmail}
          </div>
          <div className="sidebar-bottom-actions">
            <button
              type="button"
              className="sidebar-settings-btn"
              onClick={() => setSettingsOpen(true)}
              title="Settings"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </button>
            <button type="button" className="sidebar-logout" onClick={onLogout}>
              Log out
            </button>
          </div>
        </div>
      </aside>
      <SettingsModal isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />

      <nav className="mobile-tabs" aria-label="Mobile navigation">
        {navItems.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`mobile-tab ${currentView === item.id ? "active" : ""}`}
            onClick={() => onViewChange(item.id)}
          >
            <span className="mobile-tab-icon">{item.icon}</span>
            <span className="mobile-tab-label">{item.label}</span>
          </button>
        ))}
      </nav>
    </>
  );
}
