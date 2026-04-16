import { useEffect } from "react";

// Renders the rawtxt landing page inside a full-viewport iframe so the
// URL stays clean (https://rawtxt.in/ instead of .../rawtxt-landing.html).
// Links inside the iframe use target="_top" to navigate the parent window.
// Props passed by App.js (onGetStarted, onBrandClick) are intentionally
// unused — the static HTML handles its own CTAs.
function LandingPage() {
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  return (
    <iframe
      src="/landing/"
      title="rawtxt.in"
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        border: "none",
      }}
    />
  );
}

export default LandingPage;
