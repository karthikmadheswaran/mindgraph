import { getRuntimeConfig } from "../runtimeConfig";

// Patterns v1 gate (docs/designs/graph-v2-patterns.md): the section renders
// only when the runtime env flag is on OR the signed-in account is the
// founder. Default OFF — trial users must see zero difference anywhere.
// Mirrors the backend gate in app/services/patterns_service.py, which 404s
// the /patterns/* routes for everyone else.
export const FOUNDER_USER_ID = "e7bcef72-a66c-4ebe-9c5e-0a98b5f696d8";

export function isPatternsEnabled(userId) {
  const flag = String(
    getRuntimeConfig("REACT_APP_PATTERNS_ENABLED") || ""
  ).toLowerCase();
  if (["1", "true", "yes", "on"].includes(flag)) return true;
  return Boolean(userId) && userId === FOUNDER_USER_ID;
}
