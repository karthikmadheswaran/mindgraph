import posthog from "posthog-js";

export function initPostHog() {
  posthog.init("phc_wwjKLZA9TWJYE2UrgLBiVzgHT8VxWi8MEzdTpCkSxyWe", {
    api_host: "https://us.i.posthog.com",
    defaults: "2026-01-30",
    person_profiles: "identified_only",
    autocapture: true,
    capture_pageview: true,
    session_recording: {
      maskAllInputs: true,
      maskTextSelector: ".entry-content, .journal-text, textarea",
    },
    loaded: (ph) => {
      if (window.location.hostname === "localhost") {
        ph.opt_out_capturing();
      }
    },
  });
}

export function identifyUser(userId) {
  posthog.identify(userId);
}

export function trackEvent(event, properties = {}) {
  posthog.capture(event, properties);
}

export function resetUser() {
  posthog.reset();
}
