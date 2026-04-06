import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { API, authHeaders } from "../utils/auth";
import "../styles/ask.css";

export default function AskView() {
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleAsk = async () => {
    if (!query.trim() || loading) return;

    const userMessage = query.trim();
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setQuery("");
    setLoading(true);

    try {
      const headers = await authHeaders();
      const res = await fetch(
        `${API}/ask?question=${encodeURIComponent(userMessage)}`,
        {
          method: "POST",
          headers,
        }
      );

      if (!res.ok) {
        throw new Error(`Ask request failed: ${res.status}`);
      }

      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer || "I could not find an answer for that yet.",
        },
      ]);
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Something went wrong. Please try again.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="ask-view">
      <div className="ask-view-header">
        <h2 className="ask-view-title">Ask your journal</h2>
        <p className="ask-view-subtitle">
          Ask questions about your entries, patterns, and reflections.
        </p>
      </div>

      <div className="ask-thread">
        {messages.length === 0 && (
          <div className="ask-empty">
            <p>Try asking something like:</p>
            <div className="ask-suggestions">
              {[
                "What have I been working on lately?",
                "What patterns do you see in my entries?",
                "When did I last mention feeling stressed?",
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  className="ask-suggestion"
                  onClick={() => setQuery(suggestion)}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, index) => (
          <div key={`${msg.role}-${index}`} className={`ask-message ${msg.role}`}>
            <div className="ask-message-label">
              {msg.role === "user" ? "You" : "MindGraph"}
            </div>
            <div className="ask-message-content">
              {msg.role === "assistant" ? (
                <ReactMarkdown>{msg.content}</ReactMarkdown>
              ) : (
                msg.content
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="ask-message assistant">
            <div className="ask-message-label">MindGraph</div>
            <div className="ask-message-content">
              <span className="spinner small" /> Thinking...
            </div>
          </div>
        )}
      </div>

      <div className="ask-input-area">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask your journal anything..."
          onKeyDown={(e) => {
            if (e.key === "Enter") handleAsk();
          }}
          disabled={loading}
        />
        <button type="button" onClick={handleAsk} disabled={loading || !query.trim()}>
          Ask
        </button>
      </div>
    </div>
  );
}
