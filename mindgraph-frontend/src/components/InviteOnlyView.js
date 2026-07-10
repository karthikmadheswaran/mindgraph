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
        <button className="auth-submit" onClick={onLogout}>
          Log out
        </button>
      </div>
    </div>
  );
}
