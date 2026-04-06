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
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
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
    { id: "write", label: "Write", icon: icons.write },
    { id: "dashboard", label: "Dashboard", icon: icons.dashboard },
    { id: "ask", label: "Ask", icon: icons.ask },
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
