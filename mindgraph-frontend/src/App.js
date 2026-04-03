import { useState, useEffect, useCallback, useRef } from "react";
import { supabase } from "./supabaseClient";
import ReactMarkdown from "react-markdown";

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
  return new Date(dateStr).toLocaleDateString("en", {
    month: "short",
    day: "numeric",
  });
};

async function authHeaders() {
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) return {};

  return {
    Authorization: `Bearer ${session.access_token}`,
    "Content-Type": "application/json",
  };
}

/* ─── Landing Page ─── */
function LandingPage({ onGetStarted }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 100);
    return () => clearTimeout(t);
  }, []);

  return (
    <div className={`landing ${visible ? "visible" : ""}`}>
      <div className="landing-inner">
        <div className="hero">
          <div className="hero-badge">AI-Powered Journal</div>
          <h1 className="hero-title">MindGraph</h1>
          <p className="hero-subtitle">
            One textbox. Zero friction.
            <br />
            Your AI organizes everything.
          </p>
          <p className="hero-desc">
            Write freely. MindGraph&apos;s 7-node AI pipeline extracts people,
            projects, deadlines, emotions, and patterns from your thoughts —
            automatically.
          </p>
          <button className="hero-cta" onClick={onGetStarted}>
            Start journaling
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="5" y1="12" x2="19" y2="12" />
              <polyline points="12 5 19 12 12 19" />
            </svg>
          </button>
        </div>

        <div className="how-section">
          <h2 className="section-label">How it works</h2>
          <div className="how-grid">
            <div className="how-card">
              <div className="how-num">1</div>
              <h3>Write anything</h3>
              <p>
                Journal your thoughts, rants, plans, or reflections. No
                structure needed.
              </p>
            </div>
            <div className="how-card">
              <div className="how-num">2</div>
              <h3>AI processes</h3>
              <p>
                A 7-node LangGraph pipeline classifies, extracts entities,
                detects deadlines, and summarizes — in under 7 seconds.
              </p>
            </div>
            <div className="how-card">
              <div className="how-num">3</div>
              <h3>See your mind</h3>
              <p>
                Dashboard shows active projects, upcoming deadlines, people in
                your life, and behavioral patterns over time.
              </p>
            </div>
          </div>
        </div>

        <div className="features-section">
          <h2 className="section-label">What MindGraph captures</h2>
          <div className="features-grid">
            {[
              {
                icon: "🎯",
                title: "Projects & Tasks",
                desc: "Automatically tracks what you're working on",
              },
              {
                icon: "📅",
                title: "Deadlines",
                desc: "Extracts real commitments with dates",
              },
              {
                icon: "👥",
                title: "People",
                desc: "Maps who you mention and how often",
              },
              {
                icon: "🔍",
                title: "Ask Your Journal",
                desc: "RAG-powered Q&A over your entries",
              },
              {
                icon: "🧠",
                title: "Pattern Detection",
                desc: "Finds emotional patterns and recurring themes",
              },
              {
                icon: "⚡",
                title: "7-Second Pipeline",
                desc: "LangGraph + Gemini for real-time processing",
              },
            ].map((f, i) => (
              <div key={i} className="feature-card">
                <span className="feature-icon">{f.icon}</span>
                <h3>{f.title}</h3>
                <p>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="stack-section">
          <h2 className="section-label">Built with</h2>
          <div className="stack-pills">
            {[
              "LangGraph",
              "FastAPI",
              "React",
              "Supabase",
              "Gemini API",
              "pgvector",
              "Langfuse",
              "Railway",
            ].map((t) => (
              <span key={t} className="stack-pill">
                {t}
              </span>
            ))}
          </div>
        </div>

        <div className="bottom-cta">
          <p>Your thoughts deserve better than a blank notes app.</p>
          <button className="hero-cta" onClick={onGetStarted}>
            Get started — free
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="5" y1="12" x2="19" y2="12" />
              <polyline points="12 5 19 12 12 19" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Auth View ─── */
function AuthView({ onAuth, onBack }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setInfo("");

    if (mode === "signup") {
      const { error } = await supabase.auth.signUp({ email, password });
      if (error) {
        setError(error.message);
      } else {
        setInfo("Check your email for a confirmation link, then log in.");
        setMode("login");
        setPassword("");
      }
    } else {
      const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });
      if (error) {
        setError(error.message);
      } else if (data.session) {
        onAuth(data.session);
      }
    }

    setLoading(false);
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <button className="auth-back" onClick={onBack}>
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </svg>
          Back
        </button>

        <h1 className="auth-title">MindGraph</h1>
        <p className="auth-subtitle">Your AI-powered journal</p>

        <div className="auth-tabs">
          <button
            className={`auth-tab ${mode === "login" ? "active" : ""}`}
            onClick={() => {
              setMode("login");
              setError("");
              setInfo("");
            }}
          >
            Log in
          </button>
          <button
            className={`auth-tab ${mode === "signup" ? "active" : ""}`}
            onClick={() => {
              setMode("signup");
              setError("");
              setInfo("");
            }}
          >
            Sign up
          </button>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Email"
            required
            className="auth-input"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            required
            minLength={6}
            className="auth-input"
          />
          <button type="submit" className="auth-submit" disabled={loading}>
            {loading ? (
              <span className="spinner" />
            ) : mode === "login" ? (
              "Log in"
            ) : (
              "Create account"
            )}
          </button>
        </form>

        {error && <div className="auth-error">{error}</div>}
        {info && <div className="auth-info">{info}</div>}
      </div>
    </div>
  );
}

/* ─── Input View ─── */
const pipelineOrder = [
  "normalize",
  "dedup",
  "classify",
  "entities",
  "deadline",
  "title_summary",
  "store",
];

function InputView() {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const handleSubmit = async () => {
    if (!text.trim()) return;

    setLoading(true);
    setResult(null);

    try {
      const headers = await authHeaders();
      const response = await fetch(`${API}/entries/async`, {
        method: "POST",
        headers,
        body: JSON.stringify({ raw_text: text }),
      });

      if (response.status === 401) {
        setResult({
          type: "error",
          message: "Session expired. Please log in again.",
        });
        setLoading(false);
        return;
      }

      const data = await response.json();
      setResult({ type: "confirmation", message: data.message });
      setText("");
    } catch (err) {
      console.error(err);
      setResult({
        type: "error",
        message: "Failed to submit entry. Please try again.",
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
          placeholder="What's on your mind?"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSubmit();
          }}
        />
        <div className="input-actions">
          <span className="input-hint">Ctrl+Enter to submit</span>
          <button
            className="submit-btn"
            onClick={handleSubmit}
            disabled={loading || !text.trim()}
          >
            {loading ? (
              <span className="spinner small" />
            ) : (
              <>
                Send
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <line x1="5" y1="12" x2="19" y2="12" />
                  <polyline points="12 5 19 12 12 19" />
                </svg>
              </>
            )}
          </button>
        </div>
      </div>
      {result && (
        <div
          className={`result-card ${result.type === "error" ? "error" : ""}`}
        >
          {result.message}
        </div>
      )}
    </div>
  );
}

/* ─── Mind Lately Card ─── */
function MindLatelyCard({ nodes, selectedNodeId, onSelectNode }) {
  const selectedNode =
    nodes.find((node) => node.id === selectedNodeId) || nodes[0] || null;

  const nonCenterNodes = nodes.filter((node) => node.kind !== "self");

  const getNodeClass = (kind) => {
    if (kind === "self") return "mind-node self";
    if (kind === "project") return "mind-node project";
    return "mind-node entity";
  };

  const renderDetail = (node) => {
    if (!node) {
      return "A gentle snapshot of what your mind has been orbiting around lately.";
    }

    if (node.kind === "self") {
      return "You are at the center of this snapshot — the projects, people, places, and ideas your mind has been returning to recently.";
    }

    const mentionText =
      node.mentionCount && node.mentionCount > 0
        ? `Mentioned ${node.mentionCount} time${node.mentionCount > 1 ? "s" : ""}`
        : "Recently active";

    const recentText = node.lastMentionedLabel
      ? ` · last seen ${node.lastMentionedLabel}`
      : "";

    if (node.kind === "project") {
      return `${node.label} is one of your most recent active projects. ${mentionText}${recentText}.`;
    }

    return `${node.label} is showing up in your recent mental landscape. ${mentionText}${recentText}.`;
  };

  return (
    <div className="grid-card mind-card mind-card-span">
      <div className="mind-card-header">
        <div>
          <h3>Your Mind Lately</h3>
          <p className="mind-card-subtext">
            A calm snapshot of what has been most present recently.
          </p>
        </div>
      </div>

      <div className="mind-map-shell">
        <svg
          className="mind-lines"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          {nonCenterNodes.map((node, index) => {
            const curveX = node.x < 50 ? node.x + 10 : node.x - 10;
            const curveY = node.y < 46 ? node.y + 8 : node.y - 8;

            return (
              <path
                key={node.id}
                d={`M 50 46 Q ${curveX} ${curveY}, ${node.x} ${node.y}`}
                className="mind-line"
                style={{
                  opacity: selectedNodeId === node.id ? 0.9 : 0.5,
                  transitionDelay: `${index * 40}ms`,
                }}
              />
            );
          })}
        </svg>

        {nodes.map((node) => (
          <button
            key={node.id}
            type="button"
            className={`${getNodeClass(node.kind)}${
              selectedNodeId === node.id ? " active" : ""
            }`}
            style={{
              left: `${node.x}%`,
              top: `${node.y}%`,
            }}
            onClick={() => onSelectNode(node.id)}
            title={node.label}
          >
            <span className="mind-node-label">{node.label}</span>
            {node.kind !== "self" && node.mentionCount > 1 && (
              <span className="mind-node-count">{node.mentionCount}</span>
            )}
          </button>
        ))}
      </div>

      <div className="mind-detail-box">{renderDetail(selectedNode)}</div>
    </div>
  );
}

/* ─── Dashboard ─── */
function Dashboard({ refreshKey }) {
  const [entries, setEntries] = useState([]);
  const [deadlines, setDeadlines] = useState([]);
  const [entities, setEntities] = useState([]);
  const [patterns, setPatterns] = useState({});
  const [askQuery, setAskQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [asking, setAsking] = useState(false);
  const [loadingData, setLoadingData] = useState(true);
  const [expandedEntryId, setExpandedEntryId] = useState(null);
  const [liveStage, setLiveStage] = useState(null);
  const [selectedMindNodeId, setSelectedMindNodeId] = useState("you");

  const hasLoadedRef = useRef(false);
  const refreshTimeoutRef = useRef(null);
  const retryTimeoutRef = useRef(null);
  const refreshInFlightRef = useRef(false);
  const queuedRefreshRef = useRef(false);

  const applySnapshot = useCallback((snapshot) => {
    setEntries(snapshot.entries || []);
    setDeadlines(snapshot.deadlines || []);
    setEntities(snapshot.entities || []);
    setPatterns(snapshot.patterns || {});
  }, []);

  const fetchEntries = useCallback(async () => {
    const headers = await authHeaders();
    return fetch(`${API}/entries`, { headers }).then((r) => r.json());
  }, []);

  const fetchSnapshot = useCallback(async () => {
    const headers = await authHeaders();

    const [entriesData, deadlinesData, entitiesData, patternsData] =
      await Promise.all([
        fetch(`${API}/entries`, { headers }).then((r) => r.json()),
        fetch(`${API}/deadlines`, { headers }).then((r) => r.json()),
        fetch(`${API}/entities`, { headers }).then((r) => r.json()),
        fetch(`${API}/insights/patterns`, { headers })
          .then((r) => r.json())
          .catch(() => ({ data: {} })),
      ]);

    return {
      entries: entriesData.entries || [],
      deadlines: deadlinesData.deadlines || [],
      entities: entitiesData.entities || [],
      patterns: patternsData.data || {},
    };
  }, []);

  const initialLoad = useCallback(async () => {
    setLoadingData(true);
    try {
      const snapshot = await fetchSnapshot();
      applySnapshot(snapshot);
      hasLoadedRef.current = true;
    } catch (err) {
      console.error("Initial dashboard load failed:", err);
    } finally {
      setLoadingData(false);
    }
  }, [fetchSnapshot, applySnapshot]);

  const runSilentRefresh = useCallback(async () => {
    if (refreshInFlightRef.current) {
      queuedRefreshRef.current = true;
      return;
    }

    refreshInFlightRef.current = true;

    try {
      const snapshot = await fetchSnapshot();
      applySnapshot(snapshot);
      hasLoadedRef.current = true;
    } catch (err) {
      console.error("Silent refresh failed:", err);
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = setTimeout(() => {
        runSilentRefresh();
      }, 1500);
    } finally {
      refreshInFlightRef.current = false;

      if (queuedRefreshRef.current) {
        queuedRefreshRef.current = false;
        runSilentRefresh();
      }
    }
  }, [fetchSnapshot, applySnapshot]);

  const scheduleSilentRefresh = useCallback(
    (delay = 500) => {
      clearTimeout(refreshTimeoutRef.current);
      refreshTimeoutRef.current = setTimeout(() => {
        runSilentRefresh();
      }, delay);
    },
    [runSilentRefresh]
  );

  useEffect(() => {
    initialLoad();
  }, [initialLoad]);

  useEffect(() => {
    if (!hasLoadedRef.current) return;
    scheduleSilentRefresh(0);
  }, [refreshKey, scheduleSilentRefresh]);

  useEffect(() => {
    if (!hasLoadedRef.current) return;

    const interval = setInterval(() => {
      scheduleSilentRefresh(0);
    }, 45000);

    return () => clearInterval(interval);
  }, [scheduleSilentRefresh]);

  useEffect(() => {
    if (!entries.some((e) => e.status === "processing")) return;

    const interval = setInterval(async () => {
      try {
        const data = await fetchEntries();
        setEntries(data.entries || []);
      } catch (err) {
        console.error("Processing poll failed:", err);
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [entries, fetchEntries]);

  useEffect(() => {
    if (!expandedEntryId) return;

    const entry = entries.find((e) => e.id === expandedEntryId);
    if (!entry || entry.status !== "processing") return;

    setLiveStage(entry.pipeline_stage);

    const interval = setInterval(async () => {
      try {
        const headers = await authHeaders();
        const data = await fetch(`${API}/entries/${expandedEntryId}/status`, {
          headers,
        }).then((r) => r.json());

        if (data) setLiveStage(data.pipeline_stage);

        if (data && data.status !== "processing") {
          setExpandedEntryId(null);
          setLiveStage(null);
          scheduleSilentRefresh(0);
        }
      } catch (err) {
        console.error("Expanded entry status poll failed:", err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [expandedEntryId, entries, scheduleSilentRefresh]);

  useEffect(() => {
    return () => {
      clearTimeout(refreshTimeoutRef.current);
      clearTimeout(retryTimeoutRef.current);
    };
  }, []);
  const handleAsk = async () => {
    if (!askQuery.trim()) return;

    setAsking(true);
    setAnswer("");

    try {
      const headers = await authHeaders();
      const res = await fetch(
        `${API}/ask?question=${encodeURIComponent(askQuery)}`,
        {
          method: "POST",
          headers,
        }
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

  const getRecencyTs = (item) => {
    const raw =
      item?.last_mentioned_at ||
      item?.updated_at ||
      item?.created_at ||
      item?.last_seen_at ||
      null;

    const ts = raw ? new Date(raw).getTime() : 0;
    return Number.isNaN(ts) ? 0 : ts;
  };

  const formatMindDate = (value) => {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleDateString("en", {
      month: "short",
      day: "numeric",
    });
  };

  const sortRecentAndRelevant = (items) =>
    [...items].sort((a, b) => {
      const recencyDiff = getRecencyTs(b) - getRecencyTs(a);
      if (recencyDiff !== 0) return recencyDiff;

      const mentionDiff = (b.mention_count || 0) - (a.mention_count || 0);
      if (mentionDiff !== 0) return mentionDiff;

      return (a.name || "").localeCompare(b.name || "");
    });

  const mindProjects = sortRecentAndRelevant(projects).slice(0, 2);
  const mindEntities = sortRecentAndRelevant([
    ...people,
    ...places,
    ...others,
  ]).slice(0, 3);

  const mindNodes = [
    {
      id: "you",
      label: "You",
      kind: "self",
      x: 50,
      y: 46,
      mentionCount: 0,
      lastMentionedLabel: "",
    },
    ...mindProjects.map((item, index) => ({
      id: `project-${item.id ?? item.name ?? index}`,
      label: item.name,
      kind: "project",
      x: index === 0 ? 24 : 76,
      y: index === 0 ? 22 : 26,
      mentionCount: item.mention_count || 0,
      lastMentionedLabel: formatMindDate(
        item.last_mentioned_at || item.updated_at || item.created_at
      ),
    })),
    ...mindEntities.map((item, index) => {
      const positions = [
        { x: 20, y: 68 },
        { x: 50, y: 78 },
        { x: 80, y: 66 },
      ];
      const pos = positions[index] || { x: 50, y: 70 };

      return {
        id: `entity-${item.id ?? item.name ?? index}`,
        label: item.name,
        kind: "entity",
        x: pos.x,
        y: pos.y,
        mentionCount: item.mention_count || 0,
        lastMentionedLabel: formatMindDate(
          item.last_mentioned_at || item.updated_at || item.created_at
        ),
      };
    }),
  ];

  useEffect(() => {
    if (!mindNodes.some((node) => node.id === selectedMindNodeId)) {
      setSelectedMindNodeId("you");
    }
  }, [selectedMindNodeId, mindNodes]);

  if (loadingData) {
    return (
      <div
        style={{
          textAlign: "center",
          padding: 40,
          color: "var(--text-muted)",
        }}
      >
        <span className="spinner" />
        <p style={{ marginTop: 12 }}>Loading your journal...</p>
      </div>
    );
  }

  return (
    <div className="dashboard">
      <div className="ask-card">
        <div className="ask-label">Ask your journal anything</div>
        <div className="ask-row">
          <input
            value={askQuery}
            onChange={(e) => setAskQuery(e.target.value)}
            placeholder="What have I been working on lately?"
            onKeyDown={(e) => e.key === "Enter" && handleAsk()}
          />
          <button onClick={handleAsk} disabled={asking}>
            {asking ? "..." : "Ask"}
          </button>
        </div>

        {answer && (
          <div className="ask-answer">
            <ReactMarkdown>{answer}</ReactMarkdown>
          </div>
        )}
      </div>

      <div className="dashboard-grid">
        <MindLatelyCard
          nodes={mindNodes}
          selectedNodeId={selectedMindNodeId}
          onSelectNode={setSelectedMindNodeId}
        />

        <div className="grid-card">
          <h3>Active Projects</h3>
          {projects.length === 0 ? (
            <p className="empty">No projects detected yet</p>
          ) : (
            projects.slice(0, 5).map((p) => (
              <div key={p.id} className="project-item">
                <div className="project-name">{p.name}</div>
                <div className="project-meta">
                  Mentioned {p.mention_count} time{" "}
                  {p.mention_count !== 1 ? "s" : ""}
                  <span className="status-badge active">Active</span>
                </div>
              </div>
            ))
          )}
        </div>

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
                  <span
                    className="deadline-badge"
                    style={{ background: color.bg, color: color.text }}
                  >
                    {label}
                  </span>
                </div>
              );
            })
          )}
        </div>

        <div className="grid-card">
          <h3>People & Entities</h3>
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

        <div className="grid-card">
          <h3>Patterns Detected</h3>
          {!patterns.repeated_themes ? (
            <p className="empty">Analyzing your patterns...</p>
          ) : patterns.repeated_themes.length === 0 ? (
            <p className="empty">No patterns yet — keep journaling!</p>
          ) : (
            patterns.repeated_themes.map((t, i) => (
              <div key={i} className="pattern-item">
                <div className="pattern-title">{t.theme}</div>
                <div className="pattern-obs">{t.observation}</div>
              </div>
            ))
          )}
        </div>
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginTop: 4,
        }}
      >
        <h3 className="section-title">Recent Entries</h3>
        <button
          onClick={() => scheduleSilentRefresh(0)}
          className="refresh-btn"
          title="Refresh"
        >
          Refresh
        </button>
      </div>

      {entries.length === 0 ? (
        <p className="empty" style={{ padding: 16 }}>
          No entries yet. Start writing!
                </p>
      ) : (
        entries.map((e) => (
          <div
            key={e.id}
            className={`entry-card${e.status === "processing" ? " processing" : ""}`}
            onClick={() => {
              if (e.status === "processing") {
                setExpandedEntryId(expandedEntryId === e.id ? null : e.id);
              }
            }}
            style={e.status === "processing" ? { cursor: "pointer" } : {}}
          >
            <div className="entry-header">
              {e.status === "processing" ? (
                <>
                  <span className="entry-title processing-title">
                    <span className="spinner small" style={{ marginRight: 8 }} />
                    Processing your entry...
                  </span>
                  <span className="entry-date">
                    {new Date(e.created_at).toLocaleString()}
                  </span>
                </>
              ) : (
                <>
                  <span className="entry-title">
                    {e.auto_title || "Untitled Entry"}
                  </span>
                  <span className="entry-date">
                    {new Date(e.created_at).toLocaleString()}
                  </span>
                </>
              )}
            </div>

            {e.status === "processing" ? (
              <div className="entry-summary">
                {expandedEntryId === e.id ? (
                  <div className="pipeline-tracker">
                    {pipelineOrder.map((stage, idx) => {
                      const currentIndex = liveStage
                        ? pipelineOrder.indexOf(liveStage)
                        : -1;
                      const isDone = idx < currentIndex;
                      const isActive = stage === liveStage;

                      return (
                        <div
                          key={stage}
                          className={`pipeline-node ${
                            isDone ? "done" : isActive ? "active" : ""
                          }`}
                        >
                          <div className="pipeline-dot" />
                          <div className="pipeline-label">
                            {nodeLabels[stage] || stage}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <em>Click to view live progress...</em>
                )}
              </div>
            ) : (
              <div className="entry-summary">{e.summary || e.raw_text}</div>
            )}
          </div>
        ))
      )}
    </div>
  );
}

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
      <style>{`
        :root {
          --bg: #f4efe8;
          --bg-card: rgba(255, 253, 249, 0.72);
          --bg-card-solid: #fffdf9;
          --border: rgba(107, 93, 77, 0.16);
          --border-light: rgba(107, 93, 77, 0.08);
          --text-primary: #2c2418;
          --text-secondary: #5f5244;
          --text-muted: #8b7b69;
          --accent: #8a9a7a;
          --accent-soft: #d4ddd4;
          --accent-warm: #c4695a;
          --accent-warm-soft: #f5e6e4;
          --font-display: "Georgia", "Times New Roman", serif;
          --font-body: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          --radius-lg: 20px;
          --radius-md: 14px;
          --radius-sm: 10px;
          --radius-pill: 999px;
          --shadow-sm: 0 2px 12px rgba(44, 36, 24, 0.03);
          --shadow-md: 0 8px 28px rgba(44, 36, 24, 0.06);
          --shadow-lg: 0 16px 42px rgba(44, 36, 24, 0.08);
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

        /* Landing */
        .landing {
          max-width: 760px;
          margin: 0 auto;
          padding: 48px 24px 80px;
          opacity: 0;
          transform: translateY(12px);
          transition: all 0.6s ease;
        }
        .landing.visible {
          opacity: 1;
          transform: translateY(0);
        }
        .landing-inner {
          display: flex;
          flex-direction: column;
          gap: 56px;
        }
        .hero {
          text-align: center;
          padding: 40px 0 0;
        }
        .hero-badge {
          display: inline-block;
          padding: 4px 16px;
          border-radius: var(--radius-pill);
          background: var(--bg-card);
          border: 1px solid var(--border);
          font-size: 12px;
          color: var(--text-secondary);
          margin-bottom: 20px;
          backdrop-filter: blur(12px);
        }
        .hero-title {
          font-family: var(--font-display);
          font-size: clamp(52px, 10vw, 72px);
          font-weight: 400;
          line-height: 1;
          margin-bottom: 16px;
          letter-spacing: -0.03em;
        }
        .hero-subtitle {
          font-size: 22px;
          line-height: 1.4;
          color: var(--text-secondary);
          margin-bottom: 24px;
          font-weight: 400;
        }
        .hero-desc {
          font-size: 17px;
          line-height: 1.7;
          color: var(--text-muted);
          max-width: 620px;
          margin: 0 auto 32px;
        }
        .hero-cta {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          padding: 14px 28px;
          border-radius: var(--radius-pill);
          border: none;
          background: var(--text-primary);
          color: #fff;
          font-family: var(--font-body);
          font-size: 15px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
        }
        .hero-cta:hover {
          transform: translateY(-1px);
          box-shadow: var(--shadow-md);
        }

        .section-label {
          font-family: var(--font-display);
          font-size: 28px;
          font-weight: 400;
          margin-bottom: 20px;
        }
        .how-grid,
        .features-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 16px;
        }
        .how-card,
        .feature-card {
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: var(--radius-lg);
          padding: 24px;
          backdrop-filter: blur(20px);
          box-shadow: var(--shadow-sm);
        }
        .how-num {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: var(--accent-soft);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 14px;
          font-weight: 600;
          margin-bottom: 16px;
          color: var(--text-secondary);
        }
        .how-card h3,
        .feature-card h3 {
          font-size: 17px;
          font-weight: 500;
          margin-bottom: 8px;
        }
        .how-card p,
        .feature-card p {
          font-size: 14px;
          color: var(--text-muted);
          line-height: 1.65;
        }
        .feature-icon {
          font-size: 28px;
          display: block;
          margin-bottom: 14px;
        }

        .stack-pills {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
        }
        .stack-pill {
          padding: 8px 16px;
          border-radius: var(--radius-pill);
          background: var(--bg-card);
          border: 1px solid var(--border);
          font-size: 13px;
          color: var(--text-secondary);
        }
        .bottom-cta {
          text-align: center;
          padding: 24px 0 0;
        }
        .bottom-cta p {
          font-size: 18px;
          color: var(--text-secondary);
          margin-bottom: 20px;
        }

        /* Auth */
        .auth-container {
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 24px;
        }
        .auth-card {
          width: 100%;
          max-width: 420px;
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: 28px;
          padding: 36px;
          backdrop-filter: blur(24px);
          box-shadow: var(--shadow-lg);
          position: relative;
        }
        .auth-back {
          position: absolute;
          top: 18px;
          left: 18px;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          background: transparent;
          border: none;
          color: var(--text-muted);
          font-size: 13px;
          cursor: pointer;
          transition: color 0.2s;
        }
        .auth-back:hover {
          color: var(--text-primary);
        }
        .auth-title {
          font-family: var(--font-display);
          font-size: 42px;
          font-weight: 400;
          text-align: center;
          margin-bottom: 8px;
        }
        .auth-subtitle {
          text-align: center;
          color: var(--text-muted);
          margin-bottom: 28px;
          font-size: 14px;
        }
        .auth-tabs {
          display: flex;
          gap: 8px;
          margin-bottom: 24px;
          padding: 4px;
          background: rgba(255,255,255,0.45);
          border-radius: var(--radius-pill);
        }
        .auth-tab {
          flex: 1;
          padding: 10px;
          border: none;
          border-radius: var(--radius-pill);
          background: transparent;
          color: var(--text-muted);
          font-family: var(--font-body);
          font-size: 14px;
          cursor: pointer;
          transition: all 0.2s;
        }
        .auth-tab.active {
          background: var(--bg-card-solid);
          color: var(--text-primary);
          box-shadow: var(--shadow-sm);
        }
        .auth-form {
          display: flex;
          flex-direction: column;
          gap: 14px;
        }
        .auth-input {
          width: 100%;
          padding: 14px 16px;
          border-radius: var(--radius-md);
          border: 1px solid var(--border);
          background: rgba(255,255,255,0.7);
          font-size: 15px;
          font-family: var(--font-body);
          color: var(--text-primary);
          outline: none;
          transition: all 0.2s;
        }
        .auth-input:focus {
          border-color: var(--accent);
          background: #fff;
        }
        .auth-submit {
          margin-top: 8px;
          padding: 14px;
          border-radius: var(--radius-pill);
          border: none;
          background: var(--text-primary);
          color: #fff;
          font-family: var(--font-body);
          font-size: 15px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s;
          display: flex;
          justify-content: center;
          align-items: center;
          min-height: 48px;
        }
        .auth-submit:hover:not(:disabled) {
          transform: translateY(-1px);
          box-shadow: var(--shadow-md);
        }
        .auth-submit:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }
        .auth-error,
        .auth-info {
          margin-top: 16px;
          padding: 12px 14px;
          border-radius: var(--radius-md);
          font-size: 13px;
          line-height: 1.5;
        }
        .auth-error {
          background: var(--accent-warm-soft);
          color: var(--accent-warm);
        }
        .auth-info {
          background: rgba(138, 154, 122, 0.12);
          color: #4f5c45;
        }

        /* App shell */
        .app-shell {
          min-height: 100vh;
          max-width: 1200px;
          margin: 0 auto;
          padding: 24px;
        }
        .topbar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 28px;
          padding: 8px 0;
        }
        .brand {
          font-family: var(--font-display);
          font-size: 34px;
          font-weight: 400;
          letter-spacing: -0.02em;
        }
        .topbar-right {
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .nav-toggle {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 4px;
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: var(--radius-pill);
          backdrop-filter: blur(14px);
        }
        .nav-btn {
          padding: 8px 16px;
          border-radius: var(--radius-pill);
          border: none;
          background: transparent;
          color: var(--text-muted);
          font-family: var(--font-body);
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
        }
        .nav-btn:hover {
          background: var(--bg-card);
        }
        .nav-btn.active {
          background: var(--text-primary);
          color: var(--bg);
          border-color: var(--text-primary);
        }
        .logout-btn {
          padding: 6px 14px;
          border-radius: var(--radius-pill);
          border: 1px solid var(--border);
          background: transparent;
          color: var(--text-muted);
          font-family: var(--font-body);
          font-size: 12px;
          cursor: pointer;
          transition: all 0.2s;
          margin-left: 8px;
        }
        .logout-btn:hover {
          background: #f5e6e4;
          color: var(--accent-warm);
          border-color: var(--accent-warm);
        }
        .user-email {
          font-size: 12px;
          color: var(--text-muted);
          max-width: 140px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        /* Input */
        .input-view {
          max-width: 860px;
          margin: 10vh auto 0;
          display: flex;
          flex-direction: column;
          gap: 18px;
        }
        .input-card {
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: 28px;
          padding: 28px 28px 20px;
          backdrop-filter: blur(24px);
          box-shadow: var(--shadow-md);
        }
        .input-card textarea {
          width: 100%;
          min-height: 220px;
          border: none;
          outline: none;
          resize: none;
          background: transparent;
          font-family: var(--font-body);
          font-size: 20px;
          line-height: 1.7;
          color: var(--text-primary);
        }
        .input-card textarea::placeholder {
          color: #a89a89;
        }
        .input-actions {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-top: 20px;
          padding-top: 18px;
          border-top: 1px solid var(--border-light);
        }
        .input-hint {
          font-size: 13px;
          color: var(--text-muted);
        }
        .submit-btn {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 12px 22px;
          border-radius: var(--radius-pill);
          border: none;
          background: var(--text-primary);
          color: #fff;
          font-family: var(--font-body);
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
        }
        .submit-btn:hover:not(:disabled) {
          transform: translateY(-1px);
          box-shadow: var(--shadow-md);
        }
        .submit-btn:disabled {
          opacity: 0.55;
          cursor: not-allowed;
        }
        .result-card {
          padding: 16px 18px;
          border-radius: 16px;
          background: rgba(138, 154, 122, 0.12);
          color: #4f5c45;
          border: 1px solid rgba(138, 154, 122, 0.18);
        }
        .result-card.error {
          background: var(--accent-warm-soft);
          color: var(--accent-warm);
          border-color: rgba(196, 105, 90, 0.18);
        }

        /* Dashboard */
        .dashboard {
          display: flex;
          flex-direction: column;
          gap: 18px;
        }
        .ask-card,
        .grid-card,
        .entry-card {
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: 20px;
          padding: 18px 20px;
          backdrop-filter: blur(20px);
          box-shadow: var(--shadow-sm);
        }
        .ask-label {
          font-size: 13px;
          color: var(--text-muted);
          margin-bottom: 10px;
        }
        .ask-row {
          display: flex;
          gap: 10px;
        }
        .ask-row input {
          flex: 1;
          padding: 12px 14px;
          border-radius: 12px;
          border: 1px solid var(--border);
          background: rgba(255,255,255,0.7);
          font-size: 14px;
          color: var(--text-primary);
          outline: none;
        }
        .ask-row button,
        .refresh-btn {
          padding: 10px 16px;
          border-radius: var(--radius-pill);
          border: none;
          background: var(--text-primary);
          color: #fff;
          font-family: var(--font-body);
          font-size: 13px;
          cursor: pointer;
          transition: all 0.2s ease;
        }
        .ask-row button:hover,
        .refresh-btn:hover {
          transform: translateY(-1px);
          box-shadow: var(--shadow-sm);
        }
        .ask-answer {
          margin-top: 14px;
          padding-top: 14px;
          border-top: 1px solid var(--border-light);
          color: var(--text-secondary);
        }
        .dashboard-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
          gap: 16px;
        }

        .mind-card-span {
          grid-column: 1 / -1;
        }
        .mind-card {
          padding: 20px;
          background:
            radial-gradient(circle at top, rgba(212, 165, 116, 0.08), transparent 38%),
            linear-gradient(180deg, rgba(255,255,255,0.28), rgba(255,255,255,0.06)),
            var(--bg-card);
        }
        .mind-card-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 12px;
        }
        .mind-card-subtext {
          font-size: 13px;
          color: var(--text-muted);
          line-height: 1.6;
          margin-top: -4px;
        }
        .mind-map-shell {
          position: relative;
          height: 290px;
          border-radius: 16px;
          background:
            radial-gradient(circle at 50% 44%, rgba(138, 154, 122, 0.10), transparent 20%),
            linear-gradient(180deg, rgba(255,255,255,0.45), rgba(245,240,232,0.55));
          border: 1px solid var(--border-light);
          overflow: hidden;
        }
        .mind-lines {
          position: absolute;
          inset: 0;
          width: 100%;
          height: 100%;
          pointer-events: none;
        }
        .mind-line {
          fill: none;
          stroke: rgba(107, 93, 77, 0.32);
          stroke-width: 1.25;
          stroke-linecap: round;
          stroke-dasharray: 4 5;
          transition: opacity 0.25s ease, stroke 0.25s ease;
        }
        .mind-node {
          position: absolute;
          transform: translate(-50%, -50%);
          border: 1px solid var(--border);
          border-radius: 999px;
          background: rgba(250, 247, 242, 0.94);
          color: var(--text-primary);
          box-shadow: 0 8px 24px rgba(44, 36, 24, 0.08);
          padding: 10px 14px;
          min-width: 92px;
          max-width: 150px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          cursor: pointer;
          transition:
            transform 0.22s ease,
            box-shadow 0.22s ease,
            border-color 0.22s ease,
            background 0.22s ease;
        }
        .mind-node:hover {
          transform: translate(-50%, -50%) translateY(-2px) scale(1.02);
          box-shadow: 0 12px 30px rgba(44, 36, 24, 0.12);
          border-color: rgba(107, 93, 77, 0.35);
        }
        .mind-node.active {
          background: #fffdf9;
          border-color: rgba(107, 93, 77, 0.45);
          box-shadow: 0 14px 30px rgba(44, 36, 24, 0.14);
        }
        .mind-node.self {
          min-width: 104px;
          padding: 14px 18px;
          background: linear-gradient(180deg, #f7f3ec, #f2ece2);
          border-color: rgba(138, 154, 122, 0.45);
        }
        .mind-node.project {
          background: linear-gradient(
            180deg,
            rgba(212, 221, 212, 0.95),
            rgba(250, 247, 242, 0.96)
          );
        }
        .mind-node.entity {
          background: linear-gradient(
            180deg,
            rgba(232, 224, 212, 0.92),
            rgba(250, 247, 242, 0.96)
          );
        }
        .mind-node-label {
          display: block;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-size: 13px;
          font-weight: 500;
        }
        .mind-node-count {
          width: 18px;
          height: 18px;
          border-radius: 50%;
          background: rgba(44, 36, 24, 0.08);
          color: var(--text-secondary);
          display: inline-flex;
          align-items: center;
          justify-content: center;
          font-size: 10px;
          flex-shrink: 0;
        }
        .mind-detail-box {
          margin-top: 12px;
          padding: 12px 14px;
          border-top: 1px solid var(--border-light);
          font-size: 13px;
          color: var(--text-secondary);
          line-height: 1.65;
          min-height: 56px;
        }
        @media (max-width: 560px) {
          .mind-map-shell {
            height: 320px;
          }
          .mind-node {
            min-width: 84px;
            max-width: 120px;
            padding: 9px 12px;
          }
          .mind-node.self {
            min-width: 92px;
          }
        }
        .grid-card h3 {
          font-family: var(--font-display);
          font-size: 16px;
          font-weight: 400;
          margin-bottom: 12px;
          color: var(--text-primary);
        }
        .empty {
          font-size: 13px;
          color: var(--text-muted);
        }

        .project-item {
          padding: 8px 0;
          border-bottom: 1px solid var(--border-light);
        }
        .project-item:last-child {
          border-bottom: none;
        }
        .project-name {
          font-weight: 500;
          margin-bottom: 4px;
        }
        .project-meta {
          font-size: 12px;
          color: var(--text-muted);
          display: flex;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;
        }
        .status-badge {
          display: inline-flex;
          padding: 3px 8px;
          border-radius: var(--radius-pill);
          font-size: 11px;
          font-weight: 500;
        }
        .status-badge.active {
          background: rgba(138, 154, 122, 0.14);
          color: #4f5c45;
        }

        .deadline-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 12px;
          padding: 8px 0;
          border-bottom: 1px solid var(--border-light);
        }
        .deadline-item:last-child {
          border-bottom: none;
        }
        .deadline-desc {
          font-size: 14px;
          color: var(--text-secondary);
        }
        .deadline-badge {
          padding: 4px 10px;
          border-radius: var(--radius-pill);
          font-size: 11px;
          font-weight: 600;
          white-space: nowrap;
        }

        .entity-group {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        .entity-chip {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 7px 12px;
          border-radius: var(--radius-pill);
          font-size: 12px;
          font-weight: 500;
        }
        .mention-count {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-width: 18px;
          height: 18px;
          padding: 0 5px;
          border-radius: 999px;
          background: rgba(0,0,0,0.08);
          font-size: 10px;
        }

        .pattern-item {
          padding: 10px 0;
          border-bottom: 1px solid var(--border-light);
        }
        .pattern-item:last-child {
          border-bottom: none;
        }
        .pattern-title {
          font-weight: 500;
          margin-bottom: 4px;
        }
        .pattern-obs {
          font-size: 13px;
          color: var(--text-muted);
          line-height: 1.6;
        }

        .section-title {
          font-family: var(--font-display);
          font-size: 22px;
          font-weight: 400;
          margin: 0;
        }
        .entry-card {
          transition: all 0.2s ease;
        }
        .entry-card.processing:hover {
          transform: translateY(-1px);
          box-shadow: var(--shadow-md);
        }
        .entry-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 16px;
          margin-bottom: 10px;
        }
        .entry-title {
          font-weight: 600;
          color: var(--text-primary);
        }
        .processing-title {
          display: inline-flex;
          align-items: center;
        }
        .entry-date {
          font-size: 12px;
          color: var(--text-muted);
          white-space: nowrap;
        }
        .entry-summary {
          color: var(--text-secondary);
          line-height: 1.7;
        }

        .pipeline-tracker {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
          gap: 10px;
          margin-top: 8px;
        }
        .pipeline-node {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 10px 12px;
          border-radius: 12px;
          background: rgba(255,255,255,0.35);
          border: 1px solid var(--border-light);
          color: var(--text-muted);
        }
        .pipeline-node.done {
          background: rgba(138, 154, 122, 0.10);
          color: #4f5c45;
        }
        .pipeline-node.active {
          background: rgba(212, 165, 116, 0.14);
          color: #6a4d2a;
          border-color: rgba(212, 165, 116, 0.24);
        }
        .pipeline-dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          background: currentColor;
          flex-shrink: 0;
        }
        .pipeline-label {
          font-size: 13px;
          line-height: 1.4;
        }

        .spinner {
          width: 18px;
          height: 18px;
          border: 2px solid rgba(0,0,0,0.12);
          border-top-color: currentColor;
          border-radius: 50%;
          display: inline-block;
          animation: spin 0.8s linear infinite;
        }
        .spinner.small {
          width: 14px;
          height: 14px;
          border-width: 2px;
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        @media (max-width: 900px) {
          .topbar {
            flex-direction: column;
            align-items: flex-start;
            gap: 14px;
          }
          .topbar-right {
            width: 100%;
            justify-content: space-between;
          }
          .ask-row {
            flex-direction: column;
          }
        }

        @media (max-width: 640px) {
          .app-shell {
            padding: 16px;
          }
          .brand {
            font-size: 28px;
          }
          .auth-card {
            padding: 28px 20px;
          }
          .input-card {
            padding: 22px 18px 18px;
            border-radius: 22px;
          }
          .input-card textarea {
            min-height: 180px;
            font-size: 18px;
          }
          .input-actions {
            flex-direction: column;
            align-items: stretch;
            gap: 12px;
          }
          .entry-header {
            flex-direction: column;
            align-items: flex-start;
            gap: 6px;
          }
        }
      `}</style>

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