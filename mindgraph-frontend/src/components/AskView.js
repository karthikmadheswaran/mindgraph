import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { API, authHeaders } from "../utils/auth";
import AnimatedView from "./AnimatedView";
import "../styles/ask.css";

const PAGE_SIZE = 20;
const MODE_STORAGE_KEY = "mindgraph_input_mode";
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
    <div className="ask-mode-toggle" role="group" aria-label="Input mode">
      <button
        type="button"
        className={mode === "ask" ? "active" : ""}
        onClick={() => onChange("ask")}
        disabled={disabled}
      >
        Ask
      </button>
      <button
        type="button"
        className={mode === "journal" ? "active" : ""}
        onClick={() => onChange("journal")}
        disabled={disabled}
      >
        Journal
      </button>
    </div>
  );
}

function SenderLine({ sender, createdAt, tone = "user", align = "left" }) {
  return (
    <div className={`message-sender ${align}`}>
      <span className={`sender-dot ${tone}`} aria-hidden="true" />
      <span className="sender-name">{sender}</span>
      <time>{formatTime(createdAt)}</time>
    </div>
  );
}

function UserMessage({ message }) {
  return (
    <article className="message-block user-message">
      <SenderLine
        sender="You"
        createdAt={message.created_at}
        tone="user"
        align="right"
      />
      <p className="message-text">{message.content}</p>
    </article>
  );
}

function AssistantMessage({ message }) {
  return (
    <article className="message-block assistant-message">
      <SenderLine
        sender="MindGraph"
        createdAt={message.created_at}
        tone="assistant"
      />
      <div className="assistant-surface">
        <ReactMarkdown>{message.content}</ReactMarkdown>
      </div>
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
    <article className="message-block assistant-message">
      <SenderLine
        sender="MindGraph"
        createdAt={message.created_at}
        tone="assistant"
      />
      <div className="assistant-surface typing-surface">
        <TypingDots />
      </div>
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

export default function AskView({ isActive }) {
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState("");
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
  const feedRef = useRef(null);
  const shouldScrollToBottomRef = useRef(true);
  const loadedInitialMessagesRef = useRef(false);

  const placeholder = useMemo(
    () =>
      mode === "ask"
        ? "Ask anything about your journal..."
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

  const toggleMemory = useCallback(() => {
    const nextIsOpen = !isMemoryOpen;
    setIsMemoryOpen(nextIsOpen);
    if (nextIsOpen && !memoryData && !isMemoryLoading) {
      loadMemory();
    }
  }, [isMemoryLoading, isMemoryOpen, loadMemory, memoryData]);

  useEffect(() => {
    window.localStorage.setItem(MODE_STORAGE_KEY, mode);
  }, [mode]);

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
          <h2 className="ask-view-title">MindGraph</h2>
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
        </header>

        {isMemoryOpen && (
          <aside className="ask-memory-panel" aria-label="MindGraph memory">
            <div className="ask-memory-panel-header">
              <div>
                <h3>Memory</h3>
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
                Close
              </button>
            </div>

            {isMemoryLoading && (
              <div className="ask-memory-state">
                <span className="spinner small" />
                Loading memory...
              </div>
            )}

            {!isMemoryLoading && memoryError && (
              <p className="ask-memory-state error">{memoryError}</p>
            )}

            {!isMemoryLoading && !memoryError && (
              <div className="ask-memory-content">
                {memoryData?.memory ? (
                  <ReactMarkdown>{memoryData.memory}</ReactMarkdown>
                ) : (
                  <p>
                    No saved memory yet. Keep chatting and MindGraph will build
                    durable context over time.
                  </p>
                )}
              </div>
            )}
          </aside>
        )}

        <div className="conversation-feed" ref={feedRef} onScroll={handleFeedScroll}>
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

        <form
          className="ask-composer"
          onSubmit={(event) => {
            event.preventDefault();
            handleSubmit();
          }}
        >
          <ModeToggle mode={mode} onChange={setMode} disabled={isLoading} />
          <div className="ask-input-shell">
            <input
              type="text"
              value={inputText}
              onChange={(event) => setInputText(event.target.value)}
              placeholder={placeholder}
              disabled={isLoading}
            />
            <button
              type="submit"
              aria-label="Send message"
              disabled={isLoading || !inputText.trim()}
            >
              <SendIcon />
            </button>
          </div>
        </form>
      </div>
    </AnimatedView>
  );
}
