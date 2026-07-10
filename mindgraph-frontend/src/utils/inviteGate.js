import { API } from "./auth";

// Global detection of the backend's invite-only gate (403 {"detail":"invite_only"}).
// Components fetch the API directly (no shared wrapper), so the one place every
// request passes through is window.fetch itself. The wrapper only *observes*
// responses — the original response is always returned untouched.

export const INVITE_ONLY_EVENT = "mindgraph:invite-only";

let installed = false;

export function installInviteGate() {
  if (installed || typeof window === "undefined") return;
  installed = true;

  const originalFetch = window.fetch.bind(window);

  window.fetch = async (...args) => {
    const response = await originalFetch(...args);

    try {
      const url =
        typeof args[0] === "string" ? args[0] : args[0]?.url || "";

      if (response.status === 403 && url.startsWith(API)) {
        const body = await response.clone().json();
        if (body?.detail === "invite_only") {
          window.dispatchEvent(new Event(INVITE_ONLY_EVENT));
        }
      }
    } catch {
      // Detection must never break the request path.
    }

    return response;
  };
}
