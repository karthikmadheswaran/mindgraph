import { useState, useEffect } from "react";
import "../styles/landing.css";

function LandingPage({ onGetStarted }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 100);
    return () => clearTimeout(t);
  }, []);

  return (
    <div className={`landing ${visible ? "visible" : ""}`}>
      <div className="landing-inner">
        <div className="hero">
          <div className="hero-badge">AI-Powered Journal</div>
          <h1 className="hero-title">MindGraph</h1>
          <p className="hero-subtitle">
            One textbox. Zero friction.
            <br />
            Your AI organizes everything.
          </p>
          <p className="hero-desc">
            Write freely. MindGraph&apos;s 7-node AI pipeline extracts people,
            projects, deadlines, emotions, and patterns from your thoughts —
            automatically.
          </p>
          <button className="hero-cta" onClick={onGetStarted}>
            Start journaling
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="5" y1="12" x2="19" y2="12" />
              <polyline points="12 5 19 12 12 19" />
            </svg>
          </button>
        </div>

        <div className="how-section">
          <h2 className="section-label">How it works</h2>
          <div className="how-grid">
            <div className="how-card">
              <div className="how-num">1</div>
              <h3>Write anything</h3>
              <p>
                Journal your thoughts, rants, plans, or reflections. No
                structure needed.
              </p>
            </div>
            <div className="how-card">
              <div className="how-num">2</div>
              <h3>AI processes</h3>
              <p>
                A 7-node LangGraph pipeline classifies, extracts entities,
                detects deadlines, and summarizes — in under 7 seconds.
              </p>
            </div>
            <div className="how-card">
              <div className="how-num">3</div>
              <h3>See your mind</h3>
              <p>
                Dashboard shows active projects, upcoming deadlines, people in
                your life, and behavioral patterns over time.
              </p>
            </div>
          </div>
        </div>

        <div className="features-section">
          <h2 className="section-label">What MindGraph captures</h2>
          <div className="features-grid">
            {[
              {
                icon: "🎯",
                title: "Projects & Tasks",
                desc: "Automatically tracks what you're working on",
              },
              {
                icon: "📅",
                title: "Deadlines",
                desc: "Extracts real commitments with dates",
              },
              {
                icon: "👥",
                title: "People",
                desc: "Maps who you mention and how often",
              },
              {
                icon: "🔍",
                title: "Ask Your Journal",
                desc: "RAG-powered Q&A over your entries",
              },
              {
                icon: "🧠",
                title: "Pattern Detection",
                desc: "Finds emotional patterns and recurring themes",
              },
              {
                icon: "⚡",
                title: "7-Second Pipeline",
                desc: "LangGraph + Gemini for real-time processing",
              },
            ].map((f, i) => (
              <div key={i} className="feature-card">
                <span className="feature-icon">{f.icon}</span>
                <h3>{f.title}</h3>
                <p>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="stack-section">
          <h2 className="section-label">Built with</h2>
          <div className="stack-pills">
            {[
              "LangGraph",
              "FastAPI",
              "React",
              "Supabase",
              "Gemini API",
              "pgvector",
              "Langfuse",
              "Railway",
            ].map((t) => (
              <span key={t} className="stack-pill">
                {t}
              </span>
            ))}
          </div>
        </div>

        <div className="bottom-cta">
          <p>Your thoughts deserve better than a blank notes app.</p>
          <button className="hero-cta" onClick={onGetStarted}>
            Get started — free
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="5" y1="12" x2="19" y2="12" />
              <polyline points="12 5 19 12 12 19" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

export default LandingPage;
