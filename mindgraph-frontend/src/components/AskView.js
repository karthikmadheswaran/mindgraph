import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { API, authHeaders } from "../utils/auth";
import AnimatedView from "./AnimatedView";
import "../styles/ask.css";

const PAGE_SIZE = 20;
const MODE_STORAGE_KEY = "mindgraph_input_mode";

const FOLLOW_UP_PILLS = [
  "What have I been avoiding?",
  "Summarize last week",
  "What projects have gone quiet?",
  "What am I most focused on?",
];

function timeAgo(isoStr) {
  if (!isoStr) return "";
  const diffMs = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "JUST NOW";
  if (mins < 60) return `${mins} MIN AGO`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} HR AGO`;
  const days = Math.floor(hrs / 24);
  return `${days} DAY${days === 1 ? "" : "S"} AGO`;
}
const FINAL_STAGES = new Set(["completed", "error"]);
const DEFAULT_PIPELINE_STATUS = "Processing...";
const PIPELINE_STATUS_MAP = {
  queued: "Getting ready...",
  normalize: "Reading your entry...",
  dedup: "Reading your entry...",
  classify: "Understanding the context...",
  entities: "Finding people, projects, and tools...",
  deadline: "Checking for deadlines...",
  title_summary: "Generating a title...",
  extract_relations: "Connecting the dots...",
  store: "Saving everything...",
  completed: null,
};

function getInitialMode() {
  const storedMode = window.localStorage.getItem(MODE_STORAGE_KEY);
  return storedMode === "journal" ? "journal" : "ask";
}

function normalizeMessage(message) {
  return {
    ...message,
    metadata: message?.metadata || {},
    entry_id: message?.entry_id || null,
  };
}

function makeTempMessage(role, content, extra = {}) {
  return {
    id: `temp-${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
    created_at: new Date().toISOString(),
    metadata: {},
    entry_id: null,
    isTemp: true,
    ...extra,
  };
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function mergeUniqueMessages(incoming, existing) {
  const seen = new Set();
  return [...incoming, ...existing].filter((message) => {
    if (!message?.id || seen.has(message.id)) return false;
    seen.add(message.id);
    return true;
  });
}

function getPipelineStatus(stage) {
  if (Object.prototype.hasOwnProperty.call(PIPELINE_STATUS_MAP, stage)) {
    return PIPELINE_STATUS_MAP[stage];
  }
  return DEFAULT_PIPELINE_STATUS;
}

function ModeToggle({ mode, onChange, disabled }) {
  return (
    <div className="ask-mode" role="group" aria-label="Input mode">
      <button
        type="button"
        className={mode === "ask" ? "on" : ""}
        onClick={() => onChange("ask")}
        disabled={disabled}
      >
        Ask
      </button>
      <button
        type="button"
        className={mode === "journal" ? "on" : ""}
        onClick={() => onChange("journal")}
        disabled={disabled}
      >
        Journal
      </button>
    </div>
  );
}

function UserMessage({ message }) {
  return (
    <article className="ask-user">
      <div className="q-kicker">YOU ASKED · {formatTime(message.created_at)}</div>
      <div className="q-text">{message.content}</div>
    </article>
  );
}

function AssistantMessage({ message }) {
  return (
    <article className="ask-assistant">
      <ReactMarkdown>{message.content}</ReactMarkdown>
    </article>
  );
}

function TypingDots() {
  return (
    <span className="typing-dots" aria-label="MindGraph is thinking">
      <span className="typing-dot" />
      <span className="typing-dot" />
      <span className="typing-dot" />
    </span>
  );
}

function TypingIndicator({ message }) {
  return (
    <article className="ask-assistant typing-surface">
      <TypingDots />
    </article>
  );
}

function EntityChip({ entity }) {
  const type = String(entity.type || entity.entity_type || "entity").toLowerCase();
  return (
    <span className={`entity-chip ${type}`}>
      {entity.name}
    </span>
  );
}

function JournalEntryCard({ message }) {
  const metadata = message.metadata || {};
  const stage = metadata.pipeline_stage || "queued";
  const isCompleted = stage === "completed";
  const isError = stage === "error";
  const entities = metadata.entities || [];
  const currentStatus = getPipelineStatus(stage);
  const [statusText, setStatusText] = useState(
    () => currentStatus || DEFAULT_PIPELINE_STATUS
  );
  const [statusVisible, setStatusVisible] = useState(true);

  useEffect(() => {
    const nextText = getPipelineStatus(stage);
    if (!nextText || nextText === statusText) return undefined;

    setStatusVisible(false);
    const timeout = window.setTimeout(() => {
      setStatusText(nextText);
      setStatusVisible(true);
    }, 150);

    return () => window.clearTimeout(timeout);
  }, [stage, statusText]);

  return (
    <article className="message-block journal-message">
      <div className={`journal-card ${isCompleted ? "completed" : ""}`}>
        <div className="journal-card-header">
          <span className="journal-badge">Journal entry</span>
          <time>{formatTime(message.created_at)}</time>
        </div>

        {isCompleted && (
          <div className="journal-card-content loaded">
            {metadata.auto_title && (
              <h4 className="journal-title">{metadata.auto_title}</h4>
            )}
            <p className="journal-body">{message.content}</p>
            <div className="journal-divider" />
            {entities.length > 0 && (
              <div className="entity-row">
                {entities.map((entity, index) => (
                  <EntityChip
                    key={`${entity.name}-${entity.type || entity.entity_type}-${index}`}
                    entity={entity}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {!isCompleted && !isError && (
          <div className="journal-card-content loading">
            <div className="skeleton-bar skeleton-title" />
            <p className="journal-body">{message.content}</p>
            <div className="journal-divider" />
            <div
              className={`pipeline-status ${statusVisible ? "visible" : ""}`}
            >
              {statusText}
            </div>
            <div className="skeleton-chips" aria-hidden="true">
              <div className="skeleton-bar skeleton-chip short" />
              <div className="skeleton-bar skeleton-chip long" />
              <div className="skeleton-bar skeleton-chip medium" />
            </div>
          </div>
        )}

        {isError && (
          <div className="journal-card-content loaded">
            <p className="journal-body">{message.content}</p>
            <div className="journal-divider" />
            <div className="journal-error">
              Processing failed. This entry can still be found in your feed.
            </div>
          </div>
        )}
      </div>
    </article>
  );
}

function SendIcon() {
  return (
    <svg
      width="17"
      height="17"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </svg>
  );
}

// Minimal SVG icons matched to the warm parchment theme
const SectionIcons = {
  project: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2" y="7" width="20" height="14" rx="2" />
      <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
    </svg>
  ),
  work: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2" y="7" width="20" height="14" rx="2" />
      <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
    </svg>
  ),
  focus: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="4" />
    </svg>
  ),
  goal: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="4" />
    </svg>
  ),
  people: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  ),
  person: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  ),
  emotion: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <path d="M8 14s1.5 2 4 2 4-2 4-2" />
      <line x1="9" y1="9" x2="9.01" y2="9" />
      <line x1="15" y1="9" x2="15.01" y2="9" />
    </svg>
  ),
  health: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 0 0 0-7.78z" />
    </svg>
  ),
  habit: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74" />
      <path d="M3 3v4h4" />
    </svg>
  ),
  context: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  ),
  summary: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="8" y1="6" x2="21" y2="6" />
      <line x1="8" y1="12" x2="21" y2="12" />
      <line x1="8" y1="18" x2="21" y2="18" />
      <line x1="3" y1="6" x2="3.01" y2="6" />
      <line x1="3" y1="12" x2="3.01" y2="12" />
      <line x1="3" y1="18" x2="3.01" y2="18" />
    </svg>
  ),
  recent: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  ),
  deadline: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
      <line x1="16" y1="2" x2="16" y2="6" />
      <line x1="8" y1="2" x2="8" y2="6" />
      <line x1="3" y1="10" x2="21" y2="10" />
    </svg>
  ),
  task: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="9 11 12 14 22 4" />
      <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
    </svg>
  ),
  decision: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="12" y1="2" x2="12" y2="6" />
      <line x1="12" y1="10" x2="12" y2="22" />
      <path d="M5 12H2" />
      <path d="M22 12h-3" />
    </svg>
  ),
  tool: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
    </svg>
  ),
  default: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="8" y1="6" x2="21" y2="6" />
      <line x1="8" y1="12" x2="21" y2="12" />
      <line x1="8" y1="18" x2="21" y2="18" />
      <line x1="3" y1="6" x2="3.01" y2="6" />
      <line x1="3" y1="12" x2="3.01" y2="12" />
      <line x1="3" y1="18" x2="3.01" y2="18" />
    </svg>
  ),
};

function getSectionIcon(heading) {
  const lower = (heading || "").toLowerCase();
  const keys = Object.keys(SectionIcons).filter((k) => k !== "default");
  for (const key of keys) {
    if (lower.includes(key)) return SectionIcons[key];
  }
  return SectionIcons.default;
}

// Parse raw markdown into structured sections
function parseMemorySections(raw) {
  const lines = raw.split("\n");
  const sections = [];
  let currentSection = null;

  for (const line of lines) {
    const h2 = line.match(/^##\s+(.+)/);
    const h3 = line.match(/^###\s+(.+)/);
    const bullet = line.match(/^[-*]\s+(.+)/);
    const bold = line.match(/^\*\*(.+?)\*\*:?\s*(.*)/);
    const trimmed = line.trim();

    if (h2 || h3) {
      const heading = (h2 || h3)[1].trim();
      currentSection = { heading, icon: getSectionIcon(heading), items: [], prose: [] };
      sections.push(currentSection);
    } else if (bullet && currentSection) {
      currentSection.items.push(bullet[1].trim());
    } else if (bold && currentSection && bold[2]) {
      currentSection.items.push(`**${bold[1]}**: ${bold[2]}`);
    } else if (trimmed && currentSection) {
      currentSection.prose.push(trimmed);
    } else if (trimmed && !currentSection) {
      sections.push({ heading: null, icon: null, items: [], prose: [trimmed] });
    }
  }

  return sections.filter((s) => s.items.length > 0 || s.prose.length > 0);
}

function renderInline(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}

function MemoryPanel({ raw }) {
  const sections = parseMemorySections(raw);

  if (sections.length === 0) {
    return (
      <div className="memory-prose">
        <ReactMarkdown>{raw}</ReactMarkdown>
      </div>
    );
  }

  return (
    <div className="memory-sections">
      {sections.map((section, i) => (
        <div
          key={`${section.heading || "prose"}-${i}`}
          className="memory-section"
          style={{ animationDelay: `${i * 40}ms` }}
        >
          {section.heading && (
            <div className="memory-section-heading">
              <span className="memory-section-icon">{section.icon}</span>
              <span>{section.heading}</span>
            </div>
          )}
          {section.prose.length > 0 && (
            <p
              className="memory-section-prose"
              // eslint-disable-next-line react/no-danger
              dangerouslySetInnerHTML={{
                __html: section.prose.map(renderInline).join(" "),
              }}
            />
          )}
          {section.items.length > 0 && (
            <ul className="memory-section-list">
              {section.items.map((item, j) => (
                <li
                  key={j}
                  // eslint-disable-next-line react/no-danger
                  dangerouslySetInnerHTML={{ __html: renderInline(item) }}
                />
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

export default function AskView({ isActive }) {
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState("");
  const [entryCount, setEntryCount] = useState(null);
  const [mode, setMode] = useState(getInitialMode);
  const [isLoading, setIsLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [hasMore, setHasMore] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [pollingMessageIds, setPollingMessageIds] = useState(new Set());
  const [isMemoryOpen, setIsMemoryOpen] = useState(false);
  const [memoryData, setMemoryData] = useState(null);
  const [isMemoryLoading, setIsMemoryLoading] = useState(false);
  const [memoryError, setMemoryError] = useState("");
  const [isNewSessionLoading, setIsNewSessionLoading] = useState(false);
  const feedRef = useRef(null);
  const shouldScrollToBottomRef = useRef(true);
  const loadedInitialMessagesRef = useRef(false);

  const placeholder = useMemo(
    () =>
      mode === "ask"
        ? "Ask anything about your life..."
        : "Write a thought...",
    [mode]
  );

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      if (feedRef.current) {
        feedRef.current.scrollTop = feedRef.current.scrollHeight;
      }
    });
  }, []);

  const fetchConversationMessages = useCallback(async (before) => {
    const headers = await authHeaders();
    const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
    if (before) params.set("before", before);

    const res = await fetch(`${API}/conversations/messages?${params}`, {
      headers,
    });
    if (!res.ok) {
      throw new Error(`Conversation fetch failed: ${res.status}`);
    }

    return res.json();
  }, []);

  const loadAskHistoryFallback = useCallback(async () => {
    const headers = await authHeaders();
    const res = await fetch(`${API}/ask/history`, { headers });
    if (!res.ok) throw new Error("Ask history fallback failed");
    const data = await res.json();
    return {
      messages: (data.messages || []).map((message, index) =>
        normalizeMessage({
          ...message,
          id: `history-${index}-${message.created_at || ""}`,
          user_id: "",
          metadata: {},
          entry_id: null,
        })
      ),
      has_more: false,
    };
  }, []);

  const loadMemory = useCallback(async () => {
    setIsMemoryLoading(true);
    setMemoryError("");
    try {
      const headers = await authHeaders();
      const res = await fetch(`${API}/ask/memory`, { headers });
      if (!res.ok) throw new Error(`Memory fetch failed: ${res.status}`);
      const data = await res.json();
      setMemoryData(data);
    } catch {
      setMemoryError("Could not load memory right now.");
    } finally {
      setIsMemoryLoading(false);
    }
  }, []);

  // Prefetch memory in background on mount so it's instant when opened
  const memoryFetchedRef = useRef(false);
  useEffect(() => {
    if (memoryFetchedRef.current) return;
    memoryFetchedRef.current = true;
    loadMemory();
  }, [loadMemory]);

  const toggleMemory = useCallback(() => {
    setIsMemoryOpen((prev) => !prev);
  }, []);

  const handleNewSession = useCallback(async () => {
    const confirmed = window.confirm(
      "Start a new session? Your conversation history will be compacted into memory and cleared."
    );
    if (!confirmed) return;

    setIsNewSessionLoading(true);
    try {
      const headers = await authHeaders();
      const res = await fetch(`${API}/ask/new-session`, {
        method: "POST",
        headers,
      });
      if (!res.ok) throw new Error(`New session failed: ${res.status}`);
      setMessages([]);
      setHasMore(false);
      setMemoryData(null);
    } catch {
      window.alert("Could not start a new session. Please try again.");
    } finally {
      setIsNewSessionLoading(false);
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(MODE_STORAGE_KEY, mode);
  }, [mode]);

  useEffect(() => {
    authHeaders().then((headers) =>
      fetch(`${API}/entries`, { headers })
        .then((r) => r.ok ? r.json() : Promise.reject())
        .then((data) => setEntryCount((data.entries || []).length))
        .catch(() => setEntryCount(null))
    );
  }, []);

  useEffect(() => {
    if (loadedInitialMessagesRef.current) return;
    loadedInitialMessagesRef.current = true;

    const loadMessages = async () => {
      setInitialLoading(true);
      try {
        const data = await fetchConversationMessages();
        const nextMessages = (data.messages || []).map(normalizeMessage).reverse();
        setMessages(nextMessages);
        setHasMore(Boolean(data.has_more));
      } catch {
        try {
          const fallback = await loadAskHistoryFallback();
          setMessages((fallback.messages || []).map(normalizeMessage));
          setHasMore(false);
        } catch {
          setMessages([]);
          setHasMore(false);
        }
      } finally {
        setInitialLoading(false);
        shouldScrollToBottomRef.current = true;
      }
    };

    loadMessages();
  }, [fetchConversationMessages, loadAskHistoryFallback]);

  useEffect(() => {
    if (shouldScrollToBottomRef.current) {
      scrollToBottom();
      shouldScrollToBottomRef.current = false;
    }
  }, [messages, scrollToBottom]);

  useEffect(() => {
    if (pollingMessageIds.size === 0) return undefined;

    const poll = async () => {
      const ids = Array.from(pollingMessageIds);
      const headers = await authHeaders();

      await Promise.all(
        ids.map(async (id) => {
          try {
            const res = await fetch(`${API}/conversations/messages/${id}/status`, {
              headers,
            });
            if (!res.ok) return;
            const data = await res.json();
            const metadata = data.metadata || {};

            setMessages((prev) =>
              prev.map((message) =>
                message.id === id
                  ? {
                      ...message,
                      metadata,
                      entry_id: data.entry_id || message.entry_id,
                    }
                  : message
              )
            );

            if (FINAL_STAGES.has(metadata.pipeline_stage)) {
              setPollingMessageIds((prev) => {
                const next = new Set(prev);
                next.delete(id);
                return next;
              });
            }
          } catch {
            // Polling retries on the next interval.
          }
        })
      );
    };

    poll();
    const interval = window.setInterval(poll, 2000);
    return () => window.clearInterval(interval);
  }, [pollingMessageIds]);

  const loadOlderMessages = useCallback(async () => {
    if (!hasMore || isLoadingMore || messages.length === 0) return;

    const feed = feedRef.current;
    const previousScrollHeight = feed?.scrollHeight || 0;
    const previousScrollTop = feed?.scrollTop || 0;
    const oldestMessage = messages[0];

    setIsLoadingMore(true);
    try {
      const data = await fetchConversationMessages(oldestMessage.created_at);
      const olderMessages = (data.messages || []).map(normalizeMessage).reverse();

      setMessages((prev) => mergeUniqueMessages(olderMessages, prev));
      setHasMore(Boolean(data.has_more));

      requestAnimationFrame(() => {
        if (!feedRef.current) return;
        const nextScrollHeight = feedRef.current.scrollHeight;
        feedRef.current.scrollTop =
          nextScrollHeight - previousScrollHeight + previousScrollTop;
      });
    } catch {
      // Keep the current feed stable if loading older messages fails.
    } finally {
      setIsLoadingMore(false);
    }
  }, [fetchConversationMessages, hasMore, isLoadingMore, messages]);

  const handleFeedScroll = () => {
    const feed = feedRef.current;
    if (!feed || feed.scrollTop > 24) return;
    loadOlderMessages();
  };

  const replaceMessages = useCallback((removeIds, additions) => {
    setMessages((prev) => [
      ...prev.filter((message) => !removeIds.includes(message.id)),
      ...additions.map(normalizeMessage),
    ]);
  }, []);

  const sendAskFallback = useCallback(
    async (content, tempUserId, typingId) => {
      const headers = await authHeaders();
      const res = await fetch(`${API}/ask?question=${encodeURIComponent(content)}`, {
        method: "POST",
        headers,
      });

      if (!res.ok) throw new Error(`Ask fallback failed: ${res.status}`);

      const data = await res.json();
      replaceMessages(
        [typingId],
        [
          makeTempMessage(
            "assistant",
            data.answer || "I could not find an answer for that yet.",
            { isTemp: false }
          ),
        ]
      );

      setMessages((prev) =>
        prev.map((message) =>
          message.id === tempUserId ? { ...message, isTemp: false } : message
        )
      );
    },
    [replaceMessages]
  );

  const sendAskMessage = useCallback(
    async (content) => {
      const tempUser = makeTempMessage("user", content);
      const typingMessage = makeTempMessage("assistant", "", { isTyping: true });

      setMessages((prev) => [...prev, tempUser, typingMessage]);
      shouldScrollToBottomRef.current = true;

      try {
        const headers = await authHeaders();
        const res = await fetch(`${API}/conversations/messages`, {
          method: "POST",
          headers,
          body: JSON.stringify({ content, mode: "ask" }),
        });

        if (!res.ok) throw new Error(`Conversation ask failed: ${res.status}`);

        const data = await res.json();
        replaceMessages([tempUser.id, typingMessage.id], data.messages || []);
      } catch {
        try {
          await sendAskFallback(content, tempUser.id, typingMessage.id);
        } catch {
          replaceMessages(
            [typingMessage.id],
            [
              makeTempMessage(
                "assistant",
                "Something went wrong. Please try again.",
                { isTemp: false }
              ),
            ]
          );
        }
      }
    },
    [replaceMessages, sendAskFallback]
  );

  const sendJournalMessage = useCallback(
    async (content) => {
      const tempJournal = makeTempMessage("journal_entry", content, {
        metadata: { pipeline_stage: "queued" },
      });

      setMessages((prev) => [...prev, tempJournal]);
      shouldScrollToBottomRef.current = true;

      try {
        const headers = await authHeaders();
        const res = await fetch(`${API}/conversations/messages`, {
          method: "POST",
          headers,
          body: JSON.stringify({ content, mode: "journal" }),
        });

        if (!res.ok) throw new Error(`Conversation journal failed: ${res.status}`);

        const data = await res.json();
        const realMessages = data.messages || [];
        replaceMessages([tempJournal.id], realMessages);

        const journalMessage = realMessages.find(
          (message) => message.role === "journal_entry"
        );
        if (journalMessage?.id) {
          setPollingMessageIds((prev) => new Set(prev).add(journalMessage.id));
        }
      } catch {
        setMessages((prev) =>
          prev.map((message) =>
            message.id === tempJournal.id
              ? {
                  ...message,
                  isTemp: false,
                  metadata: {
                    pipeline_stage: "error",
                    error: "Failed to queue this journal entry.",
                  },
                }
              : message
          )
        );
      }
    },
    [replaceMessages]
  );

  const handleSubmit = async () => {
    const content = inputText.trim();
    if (!content || isLoading) return;

    setInputText("");
    setIsLoading(true);

    try {
      if (mode === "ask") {
        await sendAskMessage(content);
      } else {
        await sendJournalMessage(content);
      }
    } finally {
      setIsLoading(false);
      shouldScrollToBottomRef.current = true;
    }
  };

  return (
    <AnimatedView viewKey="ask" isActive={isActive}>
      <div className="ask-view">
        <header className="ask-view-header">
          <h2 className="ask-view-title">
            Ask your <em>mind.</em>
          </h2>
          <div className="ask-header-actions">
            <span className="ask-entry-stat">
              MEMORY ·{" "}
              <strong>{entryCount === null ? "—" : entryCount}</strong>{" "}
              ENTRIES
            </span>
            <button
              type="button"
              className="ask-memory-icon"
              aria-label="New session"
              disabled={isNewSessionLoading}
              onClick={handleNewSession}
            >
              {isNewSessionLoading ? (
                <span className="spinner small" aria-hidden="true" />
              ) : (
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
                  <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74" />
                  <path d="M3 3v4h4" />
                </svg>
              )}
            </button>
            <button
              type="button"
              className="ask-memory-icon"
              aria-label="Open memory"
              aria-expanded={isMemoryOpen}
              onClick={toggleMemory}
            >
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
                <path d="M12 3v18" />
                <path d="M5 8h14" />
                <path d="M7 16h10" />
                <path d="M6 5h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z" />
              </svg>
            </button>
          </div>
        </header>

        {isMemoryOpen && (
          <aside className="ask-memory-panel" aria-label="MindGraph memory">
            <div className="ask-memory-panel-header">
              <div>
                <h3>
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="memory-title-icon"><path d="M12 3v18" /><path d="M5 8h14" /><path d="M7 16h10" /><path d="M6 5h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z" /></svg>
                  Memory
                </h3>
                {memoryData?.updated_at && (
                  <time>Updated {formatDate(memoryData.updated_at)}</time>
                )}
              </div>
              <button
                type="button"
                className="ask-memory-close"
                onClick={() => setIsMemoryOpen(false)}
                aria-label="Close memory"
              >
                ✕
              </button>
            </div>

            {isMemoryLoading && (
              <div className="ask-memory-state">
                <span className="memory-shimmer-line" style={{ width: "55%" }} />
                <span className="memory-shimmer-line" style={{ width: "80%" }} />
                <span className="memory-shimmer-line" style={{ width: "65%" }} />
                <span className="memory-shimmer-line" style={{ width: "40%" }} />
              </div>
            )}

            {!isMemoryLoading && memoryError && (
              <p className="ask-memory-state error">{memoryError}</p>
            )}

            {!isMemoryLoading && !memoryError && (
              <div className="ask-memory-content">
                {memoryData?.memory ? (
                  <MemoryPanel raw={memoryData.memory} />
                ) : (
                  <div className="memory-empty">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3v18" /><path d="M5 8h14" /><path d="M7 16h10" /><path d="M6 5h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z" /></svg>
                    <p>No saved memory yet. Keep chatting and MindGraph will build durable context over time.</p>
                  </div>
                )}
              </div>
            )}
          </aside>
        )}

        <div className="ask-wrap">
          <div className="ask-thread" ref={feedRef} onScroll={handleFeedScroll}>
            {isLoadingMore && (
              <div className="older-loader" aria-label="Loading older messages">
                <TypingDots />
              </div>
            )}

            {initialLoading && (
              <div className="ask-empty">
                <span className="spinner" />
                <p>Loading your conversation...</p>
              </div>
            )}

            {!initialLoading && messages.length === 0 && (
              <div className="ask-empty welcome">
                <h3>MindGraph</h3>
                <p>Write a thought or ask a question to get started</p>
              </div>
            )}

            {messages.map((message) => {
              if (message.isTyping) {
                return <TypingIndicator key={message.id} message={message} />;
              }
              if (message.role === "assistant") {
                return <AssistantMessage key={message.id} message={message} />;
              }
              if (message.role === "journal_entry") {
                return <JournalEntryCard key={message.id} message={message} />;
              }
              return <UserMessage key={message.id} message={message} />;
            })}
          </div>
        </div>

        <div className="ask-composer">
          {/* Follow-up pills — shown only when there are messages and not loading */}
          {!isLoading && messages.length > 0 && (
            <div className="ask-suggestions">
              {FOLLOW_UP_PILLS.map((pill) => (
                <button
                  key={pill}
                  type="button"
                  className="ask-sugg"
                  onClick={() => setInputText(pill)}
                >
                  {pill}
                </button>
              ))}
            </div>
          )}

          <form
            className="ask-input"
            onSubmit={(event) => {
              event.preventDefault();
              handleSubmit();
            }}
          >
            <ModeToggle mode={mode} onChange={setMode} disabled={isLoading} />
            <input
              type="text"
              value={inputText}
              onChange={(event) => setInputText(event.target.value)}
              placeholder={placeholder}
              disabled={isLoading}
            />
            <button
              type="submit"
              className="ask-send"
              aria-label="Send message"
              disabled={isLoading || !inputText.trim()}
            >
              <SendIcon />
            </button>
          </form>
        </div>
      </div>
    </AnimatedView>
  );
}
