import RequestAccessForm from "./RequestAccessForm";

export default function InviteOnlyView({ userEmail, onLogout }) {
  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-brand">MindGraph</div>
        <p className="auth-subtitle">MindGraph is invite-only right now.</p>
        <p className="invite-only-body">
          If you were invited, make sure you signed up with the email you
          shared{userEmail ? ` — you're signed in as ${userEmail}` : ""}.
        </p>
        <p className="invite-only-body">Not invited yet? Request access:</p>
        <RequestAccessForm defaultEmail={userEmail || ""} />
        <button className="auth-back invite-only-logout" onClick={onLogout}>
          Log out
        </button>
      </div>
    </div>
  );
}
