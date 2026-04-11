import "../styles/sidebar.css";

const icons = {
  write: (
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
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
    </svg>
  ),
  dashboard: (
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
    >
      <circle cx="6" cy="7" r="3" />
      <circle cx="17" cy="6" r="3" />
      <circle cx="18" cy="17" r="3" />
      <circle cx="7" cy="18" r="3" />
      <path d="m9 7 5-.5" />
      <path d="m16 9 1.4 5" />
      <path d="m15.5 18-5.5.2" />
      <path d="m7 15 .2-5" />
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
  const navItems = [
    { id: "ask", label: "Ask", icon: icons.ask },
    { id: "write", label: "Write", icon: icons.write },
    { id: "dashboard", label: "Dashboard", icon: icons.dashboard },
    { id: "graph", label: "Knowledge Graph", icon: icons.graph },
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
            MindGraph
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
          <button type="button" className="sidebar-logout" onClick={onLogout}>
            Log out
          </button>
        </div>
      </aside>

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
