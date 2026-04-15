import { useEffect } from "react";

// The legacy React landing has been replaced by the static rawtxt HTML
// landing served from `public/rawtxt-landing.html`. This component is kept
// only as a client-side redirect so the existing App.js state machine
// (view === "landing") still has something to mount. Props passed by App.js
// (onGetStarted, onBrandClick) are intentionally unused here.
function LandingPage() {
  useEffect(() => {
    window.location.replace("/rawtxt-landing.html");
  }, []);
  return null;
}

export default LandingPage;
