import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { API, authHeaders } from "../utils/auth";
import AnimatedView from "./AnimatedView";
import "../styles/ask.css";

const PAGE_SIZE = 20;
const MODE_STORAGE_KEY = "mindgraph_input_mode";
const FINAL_STAGES = new Set(["completed", "error"]);

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

function ModeToggle({ mode, onChange, disabled }) {
  return (
    <div className="ask-mode-toggle" role="group" aria-label="Input mode">
      <button
        type="button"
        className={mode === "ask" ? "active" : ""}
        onClick={() => onChange("ask")}
        disabled={disabled}
      >
        Ask <span aria-hidden="true">💬</span>
      </button>
      <button
        type="button"
        className={mode === "journal" ? "active" : ""}
        onClick={() => onChange("journal")}
        disabled={disabled}
      >
        Journal <span aria-hidden="true">📝</span>
      </button>
    </div>
  );
}

function UserMessage({ message }) {
  return (
    <article className="chat-row user">
      <div className="chat-bubble user">
        <p>{message.content}</p>
        <time>{formatTime(message.created_at)}</time>
      </div>
    </article>
  );
}

function AssistantMessage({ message }) {
  return (
    <article className="chat-row assistant">
      <div className="chat-bubble assistant">
        <ReactMarkdown>{message.content}</ReactMarkdown>
        <time>{formatTime(message.created_at)}</time>
      </div>
    </article>
  );
}

function TypingIndicator() {
  return (
    <article className="chat-row assistant">
      <div className="chat-bubble assistant typing" aria-label="MindGraph is thinking">
        <span />
        <span />
        <span />
      </div>
    </article>
  );
}

function EntityChip({ entity }) {
  const type = String(entity.type || entity.entity_type || "entity").toLowerCase();
  return (
    <span className={`entity-chip ${type}`}>
      {entity.name}
      <small>{type}</small>
    </span>
  );
}

function JournalEntryCard({ message }) {
  const metadata = message.metadata || {};
  const stage = metadata.pipeline_stage || "queued";
  const isCompleted = stage === "completed";
  const isError = stage === "error";
  const entities = metadata.entities || [];
  const deadlines = metadata.deadlines || [];
  const categories = metadata.categories || [];

  return (
    <article className={`journal-card ${isCompleted ? "completed" : ""}`}>
      <div className="journal-card-header">
        <span className="journal-badge">Journal Entry</span>
        <time>{formatTime(message.created_at)}</time>
      </div>

      <p className="journal-content">{message.content}</p>

      {!isCompleted && !isError && (
        <div className="journal-processing">
          <span className="journal-processing-dot" />
          <span>
            {stage === "queued" ? "Queued" : `Processing: ${stage}`}
          </span>
        </div>
      )}

      {isError && (
        <div className="journal-error">
          Processing failed. This entry can still be found in your feed.
        </div>
      )}

      {isCompleted && (
        <div className="journal-results">
          {metadata.auto_title && (
            <div className="journal-result-block">
              <h4>{metadata.auto_title}</h4>
              {metadata.summary && <p>{metadata.summary}</p>}
            </div>
          )}

          {entities.length > 0 && (
            <div className="journal-result-block">
              <span className="journal-result-label">Entities</span>
              <div className="entity-chip-list">
                {entities.map((entity, index) => (
                  <EntityChip
                    key={`${entity.name}-${entity.type || entity.entity_type}-${index}`}
                    entity={entity}
                  />
                ))}
              </div>
            </div>
          )}

          {deadlines.length > 0 && (
            <div className="journal-result-block">
              <span className="journal-result-label">Deadlines</span>
              <div className="deadline-list">
                {deadlines.map((deadline, index) => (
                  <div
                    key={`${deadline.description}-${deadline.due_date}-${index}`}
                    className="deadline-pill"
                  >
                    <strong>{formatDate(deadline.due_date)}</strong>
                    <span>{deadline.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {categories.length > 0 && (
            <div className="journal-result-block">
              <span className="journal-result-label">Categories</span>
              <div className="category-list">
                {categories.map((category) => (
                  <span key={category} className="category-chip">
                    {category}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </article>
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
          <div>
            <h2 className="ask-view-title">MindGraph</h2>
          </div>
          <div className="ask-memory-icon" aria-label="Memory enabled">
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
          </div>
        </header>

        <div className="conversation-feed" ref={feedRef} onScroll={handleFeedScroll}>
          {isLoadingMore && (
            <div className="older-loader">
              <span className="spinner small" />
              Loading older messages...
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
              <h3>Welcome to MindGraph.</h3>
              <p>Write a thought or ask a question to get started.</p>
            </div>
          )}

          {messages.map((message) => {
            if (message.isTyping) {
              return <TypingIndicator key={message.id} />;
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
            <textarea
              value={inputText}
              onChange={(event) => setInputText(event.target.value)}
              placeholder={placeholder}
              rows={1}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  handleSubmit();
                }
              }}
              disabled={isLoading}
            />
            <button
              type="submit"
              aria-label="Send message"
              disabled={isLoading || !inputText.trim()}
            >
              →
            </button>
          </div>
        </form>
      </div>
    </AnimatedView>
  );
}
