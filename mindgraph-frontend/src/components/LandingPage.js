import { useState, useEffect } from "react";
import "../styles/landing.css";

function LandingPage({ onGetStarted, onBrandClick }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 100);
    return () => clearTimeout(t);
  }, []);

  const features = [
    {
      icon: "\uD83C\uDFAF",
      title: "Projects & Tasks",
      desc: "Automatically tracks what you're working on",
    },
    {
      icon: "\uD83D\uDCC5",
      title: "Deadlines",
      desc: "Extracts real commitments with dates",
    },
    {
      icon: "\uD83D\uDC65",
      title: "People",
      desc: "Maps who you mention and how often",
    },
    {
      icon: "\uD83D\uDD0D",
      title: "Ask Your Journal",
      desc: "RAG-powered Q&A over your entries",
    },
    {
      icon: "\uD83E\uDDE0",
      title: "Pattern Detection",
      desc: "Finds emotional patterns and recurring themes",
    },
    {
      icon: "\u26A1",
      title: "7-Second Pipeline",
      desc: "LangGraph + Gemini for real-time processing",
    },
  ];

  const stack = [
    "LangGraph",
    "FastAPI",
    "React",
    "Supabase",
    "Gemini API",
    "pgvector",
    "Langfuse",
    "Railway",
  ];

  return (
    <div className={`landing ${visible ? "visible" : ""}`}>
      <div className="landing-inner">
        <div className="hero">
          <div className="hero-badge">AI-Powered Journal</div>
          <button
            type="button"
            className="hero-title landing-brand"
            onClick={onBrandClick}
          >
            MindGraph
          </button>
          <p className="hero-subtitle">
            One textbox. Zero friction.
            <br />
            Your AI organizes everything.
          </p>
          <p className="hero-desc">
            Write freely. MindGraph&apos;s 7-node AI pipeline extracts people,
            projects, deadlines, emotions, and patterns from your thoughts -
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
                detects deadlines, and summarizes - in under 7 seconds.
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
            {features.map((feature) => (
              <div key={feature.title} className="feature-card">
                <span className="feature-icon">{feature.icon}</span>
                <h3>{feature.title}</h3>
                <p>{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="stack-section">
          <div className="dev-divider">
            <span className="dev-divider-line" />
            <span className="dev-divider-text">For Developers</span>
            <span className="dev-divider-line" />
          </div>
          <h2 className="section-label">Built with</h2>
          <div className="stack-pills">
            {stack.map((tech) => (
              <span key={tech} className="stack-pill">
                {tech}
              </span>
            ))}
          </div>
          <a
            href="https://github.com/karthikmadheswaran/mindgraph"
            target="_blank"
            rel="noopener noreferrer"
            className="github-link"
          >
            View on GitHub -&gt;
          </a>
        </div>

        <div className="bottom-cta">
          <p>Your thoughts deserve better than a blank notes app.</p>
          <button className="hero-cta" onClick={onGetStarted}>
            Get started - free
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
