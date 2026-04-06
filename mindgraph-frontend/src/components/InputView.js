import { useState } from "react";
import { API, authHeaders } from "../utils/auth";
import "../styles/input.css";

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

export default InputView;
