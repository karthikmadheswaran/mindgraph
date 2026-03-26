import { useState, useEffect } from "react";

const USER_ID = "e5e611e2-7618-43e2-be84-bf1fc3296382";
const API = "https://mindgraph-production.up.railway.app";

const nodeLabels = {
  normalize: "Cleaning up your text",
  dedup: "Checking for duplicates",
  classify: "Categorizing entry",
  entities: "Extracting people & projects",
  deadline: "Finding deadlines",
  title_summary: "Generating title & summary",
  store: "Saving to database",
};

const entityColors = {
  person: { bg: "#e8e0d4", text: "#5a4a3a" },
  project: { bg: "#d4ddd4", text: "#3a4a3a" },
  place: { bg: "#ddd8cc", text: "#4a453a" },
  organization: { bg: "#d4d8dd", text: "#3a3f4a" },
  task: { bg: "#e0d4d4", text: "#4a3a3a" },
  event: { bg: "#d4dde0", text: "#3a4a4d" },
  tool: { bg: "#ddd4e0", text: "#453a4a" },
};

const deadlineColor = (dateStr) => {
  if (!dateStr) return { bg: "#d4ddd4", text: "#3a4a3a" };
  const days = Math.ceil((new Date(dateStr) - new Date()) / 86400000);
  if (days <= 1) return { bg: "#c4695a", text: "#fff" };
  if (days <= 3) return { bg: "#d4a574", text: "#3a2a1a" };
  return { bg: "#8a9a7a", text: "#fff" };
};

const deadlineLabel = (dateStr) => {
  if (!dateStr) return "";
  const days = Math.ceil((new Date(dateStr) - new Date()) / 86400000);
  if (days < 0) return "Overdue";
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days <= 7) {
    return new Date(dateStr).toLocaleDateString("en", { weekday: "long" });
  }
  return new Date(dateStr).toLocaleDateString("en", { month: "short", day: "numeric" });
};

/* --- Input View --- */
function InputView() {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [status, setStatus] = useState([]);

  const handleSubmit = async () => {
    if (!text.trim()) return;
    setLoading(true);
    setResult(null);
    setStatus([]);

    try {
      const response = await fetch(`${API}/entries/async`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_text: text, user_id: USER_ID }),
      });
      const data = await response.json();
      setResult({
        auto_title: "✨ Entry submitted!",
        summary: data.message,
        classifier: [],
        core_entities: [],
        deadline: [],
      });
      setText("");
    } catch (err) {
      console.error(err);
      setResult({
        auto_title: "❌ Error",
        summary: "Failed to submit entry. Please try again.",
        classifier: [],
        core_entities: [],
        deadline: [],
      });
    }
    setLoading(false);
  };

  return (
    <div className="input-view">
      <div className="input-card">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="what's on your mind?"
          onKeyDown={(e) => {
            if (e.key === "Enter" && e.metaKey) handleSubmit();
          }}
        />
        <div className="input-actions">
          <button
            className="submit-btn"
            onClick={handleSubmit}
            disabled={loading || !text.trim()}
          >
            {loading ? (
              <span className="spinner" />
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
            )}
          </button>
        </div>
      </div>

      {/* Processing Status */}
      {status.length > 0 && (
        <div className="status-card">
          {status.map((node, i) => (
            <div key={i} className="status-item completed">
              <span className="status-check">&#10003;</span>
              {nodeLabels[node] || node}
            </div>
          ))}
          {loading && (
            <div className="status-item processing">
              <span className="spinner small" />
              Processing next step...
            </div>
          )}
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="result-card">
          <div className="result-title">{result.auto_title}</div>
          <div className="result-text">{result.summary}</div>

          {/* Categories */}
          {result.classifier && result.classifier.length > 0 && (
            <div className="result-section">
              <div className="result-label">Categories</div>
              <div className="result-tags">
                {result.classifier.map((c, i) => (
                  <span key={i} className="tag category">{c}</span>
                ))}
              </div>
            </div>
          )}

          {/* Entities */}
          {result.core_entities && result.core_entities.length > 0 && (
            <div className="result-section">
              <div className="result-label">People &amp; Projects</div>
              <div className="result-tags">
                {result.core_entities.map((e, i) => {
                  const color = entityColors[e.type] || entityColors.task;
                  return (
                    <span key={i} className="entity-chip" style={{ background: color.bg, color: color.text }}>
                      {e.name}
                    </span>
                  );
                })}
              </div>
            </div>
          )}

          {/* Deadlines */}
          {result.deadline && result.deadline.length > 0 && (
            <div className="result-section">
              <div className="result-label">Deadlines</div>
              {result.deadline.map((d, i) => {
                const color = deadlineColor(d.due_at);
                const label = deadlineLabel(d.due_at);
                return (
                  <div key={i} className="deadline-item">
                    <span className="deadline-desc">{d.description}</span>
                    <span className="deadline-badge" style={{ background: color.bg, color: color.text }}>
                      {label || d.due_at?.slice(0, 10)}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* --- Dashboard --- */
function Dashboard() {
  const [entries, setEntries] = useState([]);
  const [deadlines, setDeadlines] = useState([]);
  const [entities, setEntities] = useState([]);
  const [askQuery, setAskQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [asking, setAsking] = useState(false);
  const [loadingData, setLoadingData] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`${API}/entries?user_id=${USER_ID}`).then((r) => r.json()),
      fetch(`${API}/deadlines?user_id=${USER_ID}`).then((r) => r.json()),
      fetch(`${API}/entities?user_id=${USER_ID}`).then((r) => r.json()),
    ]).then(([entriesData, deadlinesData, entitiesData]) => {
      setEntries(entriesData.entries || []);
      setDeadlines(deadlinesData.deadlines || []);
      setEntities(entitiesData.entities || []);
      setLoadingData(false);
    }).catch(() => setLoadingData(false));
  }, []);

  const handleAsk = async () => {
    if (!askQuery.trim()) return;
    setAsking(true);
    setAnswer("");
    try {
      const res = await fetch(
        `${API}/ask?question=${encodeURIComponent(askQuery)}&user_id=${USER_ID}`,
        { method: "POST" }
      );
      const data = await res.json();
      setAnswer(data.answer);
    } catch (err) {
      console.error(err);
    }
    setAsking(false);
  };

  const projects = entities.filter((e) => e.entity_type === "project");
  const people = entities.filter((e) => e.entity_type === "person");
  const places = entities.filter((e) => e.entity_type === "place");
  const others = entities.filter(
    (e) => !["project", "person", "place"].includes(e.entity_type)
  );

  if (loadingData) {
    return (
      <div style={{ textAlign: "center", padding: 40, color: "#9a8b78" }}>
        <span className="spinner" />
        <p style={{ marginTop: 12 }}>Loading your journal...</p>
      </div>
    );
  }

  return (
    <div className="dashboard">
      {/* Ask */}
      <div className="ask-card">
        <div className="ask-label">Ask your journal anything</div>
        <div className="ask-row">
          <input
            value={askQuery}
            onChange={(e) => setAskQuery(e.target.value)}
            placeholder="What have I been working on with Sneha?"
            onKeyDown={(e) => e.key === "Enter" && handleAsk()}
          />
          <button onClick={handleAsk} disabled={asking}>
            {asking ? "..." : "Ask"}
          </button>
        </div>
        {answer && <div className="ask-answer">{answer}</div>}
      </div>

      {/* Grid */}
      <div className="dashboard-grid">
        {/* Active Projects */}
        <div className="grid-card">
          <h3>Active Projects</h3>
          {projects.length === 0 ? (
            <p className="empty">No projects detected yet</p>
          ) : (
            projects.slice(0, 5).map((p) => (
              <div key={p.id} className="project-item">
                <div className="project-name">{p.name}</div>
                <div className="project-meta">
                  Mentioned {p.mention_count} time{p.mention_count !== 1 ? "s" : ""}
                  <span className="status-badge active">Active</span>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Upcoming Deadlines */}
        <div className="grid-card">
          <h3>Upcoming Deadlines</h3>
          {deadlines.length === 0 ? (
            <p className="empty">No deadlines found</p>
          ) : (
            deadlines.slice(0, 5).map((d) => {
              const color = deadlineColor(d.due_date);
              const label = deadlineLabel(d.due_date);
              return (
                <div key={d.id} className="deadline-item">
                  <span className="deadline-desc">{d.description}</span>
                  <span className="deadline-badge" style={{ background: color.bg, color: color.text }}>
                    {label}
                  </span>
                </div>
              );
            })
          )}
        </div>

        {/* People & Entities */}
        <div className="grid-card">
          <h3>People &amp; Entities</h3>
          <div className="entity-group">
            {[...people, ...places, ...others].slice(0, 15).map((e) => {
              const color = entityColors[e.entity_type] || entityColors.task;
              return (
                <span
                  key={e.id}
                  className="entity-chip"
                  style={{ background: color.bg, color: color.text }}
                >
                  {e.name}
                  {e.mention_count > 1 && (
                    <span className="mention-count">{e.mention_count}</span>
                  )}
                </span>
              );
            })}
          </div>
        </div>

        {/* Patterns placeholder */}
        <div className="grid-card">
          <h3>Patterns Detected</h3>
          <p className="empty" style={{ fontStyle: "italic" }}>
            Patterns and insights will appear here as you journal more entries over time.
          </p>
        </div>
      </div>

      {/* Recent Entries */}
      <h3 className="section-title">Recent Entries</h3>
      {entries.map((e) => (
        <div key={e.id} className="entry-card">
          <div className="entry-header">
            <span className="entry-title">{e.auto_title}</span>
            <span className="entry-date">
              {e.created_at
                ? new Date(e.created_at).toLocaleDateString("en", {
                    month: "short",
                    day: "numeric",
                  })
                : ""}
            </span>
          </div>
          <div className="entry-summary">{e.summary}</div>
        </div>
      ))}
    </div>
  );
}

/* --- App Shell --- */
function App() {
  const [view, setView] = useState("input");

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300;1,9..40,400&display=swap');

        :root {
          --bg: #f5f0e8;
          --bg-card: #faf7f2;
          --bg-input: #ffffff;
          --text-primary: #2c2418;
          --text-secondary: #6b5d4d;
          --text-muted: #9a8b78;
          --border: #e0d8cc;
          --border-light: #ebe5db;
          --accent-green: #8a9a7a;
          --accent-olive: #6b7a5a;
          --accent-warm: #c4695a;
          --accent-amber: #d4a574;
          --shadow: 0 1px 3px rgba(44, 36, 24, 0.06);
          --shadow-md: 0 4px 12px rgba(44, 36, 24, 0.08);
          --radius: 12px;
          --radius-sm: 8px;
          --radius-pill: 20px;
          --font-display: 'Instrument Serif', Georgia, serif;
          --font-body: 'DM Sans', -apple-system, sans-serif;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
          background: var(--bg);
          color: var(--text-primary);
          font-family: var(--font-body);
          font-size: 15px;
          line-height: 1.6;
          -webkit-font-smoothing: antialiased;
        }

        .app-shell {
          max-width: 720px;
          margin: 0 auto;
          padding: 24px 16px 60px;
          min-height: 100vh;
        }

        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 28px;
          padding-bottom: 16px;
          border-bottom: 1px solid var(--border-light);
        }
        .header h1 {
          font-family: var(--font-display);
          font-size: clamp(22px, 5vw, 30px);
          font-weight: 400;
          color: var(--text-primary);
          letter-spacing: -0.01em;
        }
        .nav-btns { display: flex; gap: 4px; }
        .nav-btn {
          padding: 8px 18px;
          border-radius: var(--radius-pill);
          border: 1px solid var(--border);
          background: transparent;
          color: var(--text-secondary);
          font-family: var(--font-body);
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
        }
        .nav-btn:hover { background: var(--bg-card); }
        .nav-btn.active {
          background: var(--text-primary);
          color: var(--bg);
          border-color: var(--text-primary);
        }

        .input-view { display: flex; flex-direction: column; gap: 16px; }

        .input-card {
          background: var(--bg-card);
          border: 1px solid var(--border-light);
          border-radius: var(--radius);
          padding: 20px;
          box-shadow: var(--shadow);
        }
        .input-card textarea {
          width: 100%;
          min-height: 180px;
          border: none;
          outline: none;
          resize: vertical;
          font-family: var(--font-body);
          font-size: 16px;
          line-height: 1.7;
          color: var(--text-primary);
          background: transparent;
          padding: 0;
        }
        .input-card textarea::placeholder {
          color: var(--text-muted);
          font-style: italic;
        }

        .input-actions {
          display: flex;
          justify-content: flex-end;
          margin-top: 12px;
          padding-top: 12px;
          border-top: 1px solid var(--border-light);
        }

        .submit-btn {
          width: 42px;
          height: 42px;
          border-radius: 50%;
          border: 1px solid var(--border);
          background: var(--bg-card);
          color: var(--text-secondary);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s ease;
        }
        .submit-btn:hover:not(:disabled) {
          background: var(--text-primary);
          color: var(--bg);
          border-color: var(--text-primary);
        }
        .submit-btn:disabled { opacity: 0.4; cursor: not-allowed; }

        .status-card {
          background: var(--bg-card);
          border: 1px solid var(--border-light);
          border-radius: var(--radius);
          padding: 16px;
          box-shadow: var(--shadow);
        }
        .status-item {
          font-size: 13px;
          color: var(--text-muted);
          padding: 4px 0;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .status-item.completed { color: var(--text-secondary); }
        .status-check {
          width: 18px;
          height: 18px;
          border-radius: 50%;
          background: var(--accent-green);
          color: white;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          font-size: 10px;
          flex-shrink: 0;
        }

        .result-card {
          background: var(--bg-card);
          border: 1px solid var(--border-light);
          border-radius: var(--radius);
          padding: 20px;
          box-shadow: var(--shadow);
        }
        .result-title {
          font-family: var(--font-display);
          font-size: 20px;
          margin-bottom: 8px;
          color: var(--text-primary);
        }
        .result-text {
          font-size: 14px;
          color: var(--text-secondary);
          line-height: 1.6;
          margin-bottom: 4px;
        }
        .result-section {
          padding-top: 12px;
          margin-top: 12px;
          border-top: 1px solid var(--border-light);
        }
        .result-label {
          font-size: 11px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--text-muted);
          margin-bottom: 8px;
        }
        .result-tags {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }

        .tag {
          display: inline-block;
          padding: 3px 12px;
          border-radius: var(--radius-pill);
          font-size: 12px;
          font-weight: 500;
          text-transform: capitalize;
        }
        .tag.category {
          background: #e8e0d4;
          color: var(--text-secondary);
        }

        .spinner {
          width: 16px; height: 16px;
          border: 2px solid var(--border);
          border-top-color: var(--text-secondary);
          border-radius: 50%;
          animation: spin 0.6s linear infinite;
          display: inline-block;
        }
        .spinner.small { width: 12px; height: 12px; border-width: 1.5px; }
        @keyframes spin { to { transform: rotate(360deg); } }

        .dashboard { display: flex; flex-direction: column; gap: 16px; }

        .ask-card {
          background: var(--bg-card);
          border: 1px solid var(--border-light);
          border-radius: var(--radius);
          padding: 20px;
          box-shadow: var(--shadow);
        }
        .ask-label {
          font-family: var(--font-display);
          font-size: 17px;
          margin-bottom: 10px;
          color: var(--text-primary);
        }
        .ask-row { display: flex; gap: 8px; }
        .ask-row input {
          flex: 1;
          min-width: 0;
          padding: 10px 14px;
          border-radius: var(--radius-sm);
          border: 1px solid var(--border);
          font-family: var(--font-body);
          font-size: 14px;
          background: var(--bg-input);
          color: var(--text-primary);
          outline: none;
          transition: border-color 0.2s;
        }
        .ask-row input:focus { border-color: var(--text-muted); }
        .ask-row input::placeholder { color: var(--text-muted); }
        .ask-row button {
          padding: 10px 20px;
          border-radius: var(--radius-sm);
          border: 1px solid var(--border);
          background: var(--text-primary);
          color: var(--bg);
          font-family: var(--font-body);
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          white-space: nowrap;
          transition: opacity 0.2s;
        }
        .ask-row button:disabled { opacity: 0.5; cursor: not-allowed; }
        .ask-answer {
          margin-top: 14px;
          padding-top: 14px;
          border-top: 1px solid var(--border-light);
          font-size: 14px;
          line-height: 1.7;
          color: var(--text-secondary);
          white-space: pre-wrap;
        }

        .dashboard-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
        }
        @media (max-width: 560px) {
          .dashboard-grid { grid-template-columns: 1fr; }
        }

        .grid-card {
          background: var(--bg-card);
          border: 1px solid var(--border-light);
          border-radius: var(--radius);
          padding: 18px;
          box-shadow: var(--shadow);
        }
        .grid-card h3 {
          font-family: var(--font-display);
          font-size: 16px;
          font-weight: 400;
          margin-bottom: 12px;
          color: var(--text-primary);
        }
        .empty { font-size: 13px; color: var(--text-muted); }

        .project-item {
          padding: 8px 0;
          border-bottom: 1px solid var(--border-light);
        }
        .project-item:last-child { border-bottom: none; }
        .project-name { font-size: 14px; font-weight: 500; color: var(--text-primary); }
        .project-meta {
          font-size: 12px;
          color: var(--text-muted);
          display: flex;
          align-items: center;
          gap: 8px;
          margin-top: 2px;
        }
        .status-badge {
          padding: 2px 10px;
          border-radius: var(--radius-pill);
          font-size: 11px;
          font-weight: 500;
        }
        .status-badge.active { background: var(--accent-green); color: white; }

        .deadline-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 8px 0;
          border-bottom: 1px solid var(--border-light);
        }
        .deadline-item:last-child { border-bottom: none; }
        .deadline-desc { font-size: 14px; color: var(--text-primary); }
        .deadline-badge {
          padding: 3px 12px;
          border-radius: var(--radius-pill);
          font-size: 11px;
          font-weight: 500;
          white-space: nowrap;
        }

        .entity-group { display: flex; flex-wrap: wrap; gap: 6px; }
        .entity-chip {
          padding: 4px 12px;
          border-radius: var(--radius-pill);
          font-size: 12px;
          font-weight: 500;
          display: inline-flex;
          align-items: center;
          gap: 4px;
        }
        .mention-count {
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: rgba(0,0,0,0.08);
          display: inline-flex;
          align-items: center;
          justify-content: center;
          font-size: 10px;
        }

        .section-title {
          font-family: var(--font-display);
          font-size: 18px;
          font-weight: 400;
          color: var(--text-primary);
          margin-top: 4px;
        }
        .entry-card {
          background: var(--bg-card);
          border: 1px solid var(--border-light);
          border-radius: var(--radius);
          padding: 16px;
          box-shadow: var(--shadow);
        }
        .entry-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 8px;
          margin-bottom: 4px;
        }
        .entry-title {
          font-family: var(--font-display);
          font-size: 16px;
          color: var(--text-primary);
        }
        .entry-date {
          font-size: 12px;
          color: var(--text-muted);
          white-space: nowrap;
          flex-shrink: 0;
        }
        .entry-summary {
          font-size: 13px;
          color: var(--text-secondary);
          line-height: 1.6;
        }
      `}</style>

      <div className="app-shell">
        <div className="header">
          <h1>MindGraph</h1>
          <div className="nav-btns">
            <button
              className={`nav-btn ${view === "input" ? "active" : ""}`}
              onClick={() => setView("input")}
            >
              Write
            </button>
            <button
              className={`nav-btn ${view === "dashboard" ? "active" : ""}`}
              onClick={() => setView("dashboard")}
            >
              Dashboard
            </button>
          </div>
        </div>

        {view === "input" ? <InputView /> : <Dashboard />}
      </div>
    </>
  );
}

export default App;