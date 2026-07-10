import { useState } from "react";
import { API } from "../utils/auth";

// Inline "request access" form for invite-gated visitors. Posts to the
// unauthenticated backend route; no auth header needed. Reuses auth-* tokens.
export default function RequestAccessForm({ defaultEmail = "" }) {
  const [email, setEmail] = useState(defaultEmail);
  const [note, setNote] = useState("");
  const [status, setStatus] = useState("idle"); // idle | sending | done | error

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus("sending");
    try {
      const res = await fetch(`${API}/access-requests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), note: note.trim() || null }),
      });
      setStatus(res.ok ? "done" : "error");
    } catch {
      setStatus("error");
    }
  };

  if (status === "done") {
    return (
      <p className="auth-info request-access-done">
        Thanks — you'll hear from Karthik.
      </p>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="auth-form request-access-form">
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Email"
        required
        className="auth-input"
      />
      <input
        type="text"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="What brings you here? (optional)"
        maxLength={280}
        className="auth-input"
      />
      <button
        type="submit"
        className="auth-submit"
        disabled={status === "sending"}
      >
        {status === "sending" ? <span className="spinner" /> : "Request access"}
      </button>
      {status === "error" && (
        <div className="auth-error">Something went wrong. Please try again.</div>
      )}
    </form>
  );
}
