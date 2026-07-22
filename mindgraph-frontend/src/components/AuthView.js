import { useState } from "react";
import { supabase } from "../supabaseClient";
import { API } from "../utils/auth";
import RequestAccessForm from "./RequestAccessForm";
import "../styles/auth.css";

// STUB strings — Karthik writes the real copy. Keys match the backend's
// /auth/signup error details (GoTrue error_code passthrough).
const SIGNUP_ERROR_STRINGS = {
  not_invited: "[[STUB: not on the invite list]]",
  over_email_send_rate_limit: "[[STUB: email limit reached, try later]]",
  weak_password: "[[STUB: weak password]]",
  signup_unavailable: "[[STUB: signup temporarily unavailable]]",
  generic: "[[STUB: signup failed, try again]]",
};

function AuthView({ onAuth, onBack, onBrandClick }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [showRequestAccess, setShowRequestAccess] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setInfo("");

    if (mode === "signup") {
      // Signup goes through the backend (POST /auth/signup), which checks the
      // invite allowlist BEFORE any Supabase auth user is created. Direct
      // supabase.auth.signUp would create orphan users for non-invited emails.
      try {
        const res = await fetch(`${API}/auth/signup`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: email.trim(), password }),
        });
        if (res.ok) {
          setInfo("Check your email for a confirmation link, then log in.");
          setMode("login");
          setPassword("");
        } else {
          let detail = "";
          try {
            detail = (await res.json())?.detail || "";
          } catch {
            // Non-JSON error body — fall through to the generic string.
          }
          if (res.status === 403 && detail === "not_invited") {
            setShowRequestAccess(true);
            setError(SIGNUP_ERROR_STRINGS.not_invited);
          } else {
            setError(
              SIGNUP_ERROR_STRINGS[detail] || SIGNUP_ERROR_STRINGS.generic
            );
          }
        }
      } catch {
        setError(SIGNUP_ERROR_STRINGS.generic);
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

        <button type="button" className="auth-brand" onClick={onBrandClick}>
          MindGraph
        </button>
        <p className="auth-subtitle">Your AI-powered journal</p>
        <p className="auth-invite-note">
          MindGraph is invite-only right now — use the email you were invited
          with.
        </p>

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

        {mode === "signup" && (
          <div className="auth-request-access">
            {showRequestAccess ? (
              <>
                <p className="auth-invite-note">
                  Not invited yet? Leave your email and Karthik will be in touch.
                </p>
                <RequestAccessForm defaultEmail={email} />
              </>
            ) : (
              <button
                type="button"
                className="auth-request-access-link"
                onClick={() => setShowRequestAccess(true)}
              >
                Not invited yet? Request access
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default AuthView;
