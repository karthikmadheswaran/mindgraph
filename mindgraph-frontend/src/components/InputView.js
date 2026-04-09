import { useState } from "react";
import { API, authHeaders } from "../utils/auth";
import AnimatedView from "./AnimatedView";
import Toast from "./Toast";
import "../styles/input.css";

function InputView({ isActive, onEntrySubmitted }) {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState(null);

  const handleSubmit = async () => {
    if (!text.trim()) return;

    setLoading(true);

    try {
      const userTimezone =
        Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
      const headers = await authHeaders();
      const response = await fetch(`${API}/entries/async`, {
        method: "POST",
        headers,
        body: JSON.stringify({ raw_text: text, user_timezone: userTimezone }),
      });

      if (response.status === 401) {
        setToast({
          message: "Session expired. Please log in again.",
          type: "error",
        });
        return;
      }

      if (!response.ok) {
        throw new Error("Entry submission failed");
      }

      await response.json();
      setToast({
        message: "Entry submitted! Processing...",
        type: "success",
      });
      setText("");
      if (onEntrySubmitted) onEntrySubmitted();
    } catch {
      setToast({
        message: "Failed to submit entry. Please try again.",
        type: "error",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <AnimatedView viewKey="write" isActive={isActive}>
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
            <span className="input-hint">
              {text.trim() ? `${text.trim().split(/\s+/).length} words - ` : ""}
              Ctrl+Enter to submit
            </span>
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

        <Toast
          message={toast?.message}
          type={toast?.type || "success"}
          visible={!!toast}
          onDismiss={() => setToast(null)}
        />
      </div>
    </AnimatedView>
  );
}

export default InputView;
