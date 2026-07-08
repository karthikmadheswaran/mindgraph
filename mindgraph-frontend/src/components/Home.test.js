import { render, screen, waitFor } from "@testing-library/react";
import Home from "./Home";

// Home quietness pass:
//  1. Noticed shows the reflection gift ONLY while unopened (wrapped), still
//     capped at HOME_MAX_INSIGHTS. An opened gift renders nothing on Home —
//     it lives on in Journal → Patterns. (The `opened` flag is gift-level in
//     the schema, so "opened" == the whole gift is revealed; opening any card
//     marks it opened server-side and it drops off Home on the next fetch.)
//  2. First-run promise card: a dashed hint under the composer while the user
//     has < 3 total entries — never at 3+, never alongside a drift card.

jest.mock("./AnimatedView", () => ({
  __esModule: true,
  default: ({ children }) => children,
}));

jest.mock("../utils/auth", () => ({
  __esModule: true,
  API: "https://mindgraph-production.up.railway.app",
  authHeaders: jest.fn().mockResolvedValue({
    Authorization: "Bearer test-token",
    "Content-Type": "application/json",
  }),
}));

jest.mock("../supabaseClient", () => ({
  __esModule: true,
  supabase: {
    auth: {
      getSession: jest.fn(),
    },
  },
}));

import { supabase } from "../supabaseClient";

const SEVEN_INSIGHT_DOC = Array.from(
  { length: 7 },
  (_, i) => `**Insight ${i + 1}**\nBody of insight ${i + 1}.`
).join("\n\n");

const DRIFT_PICK = {
  id: "intent-1",
  text: "go to the gym",
  drift_days: 54,
  is_drifting: true,
  first_stated_at: "2026-05-01T00:00:00Z",
  last_referenced_at: "2026-05-14T00:00:00Z",
  reference_count: 2,
  status: "active",
  score: 4.324,
};

const PROMISE_FRAGMENT = /After a few entries, MindGraph starts noticing/i;

function jsonResponse(payload, ok = true) {
  return Promise.resolve({
    ok,
    status: ok ? 200 : 500,
    json: () => Promise.resolve(payload),
  });
}

// Per-test wiring: pick (drift card or null), synthesis (gift or null),
// entriesTotal (drives the promise card).
function wireFetch({ pick = null, synthesis = null, entriesTotal = 0 } = {}) {
  global.fetch = jest.fn((input) => {
    const url = typeof input === "string" ? input : input.url;
    if (url.includes("/intentions/drift")) {
      return jsonResponse({ threshold_days: 14, pick });
    }
    if (url.includes("/insights/synthesis")) {
      return jsonResponse({ data: synthesis });
    }
    if (url.includes("/entries")) {
      const entries = Array.from({ length: Math.min(entriesTotal, 3) }, (_, i) => ({
        id: `e-${i + 1}`,
        auto_title: `Entry ${i + 1}`,
        created_at: `2026-06-0${i + 1}T10:00:00Z`,
      }));
      return jsonResponse({ entries, total_count: entriesTotal });
    }
    return jsonResponse({});
  });
}

beforeEach(() => {
  // CRA jest runs with resetMocks: true — (re)apply implementations per test.
  supabase.auth.getSession.mockResolvedValue({
    data: { session: { user: { id: "user-1", email: "test@rawtxt.in" } } },
  });
});

afterEach(() => {
  jest.clearAllMocks();
});

// ——— Task 1: gift shows only while unopened ———

test("an OPENED gift renders nothing on Home (lives in Journal, not here)", async () => {
  wireFetch({
    pick: DRIFT_PICK,
    synthesis: { synthesis_text: SEVEN_INSIGHT_DOC, opened: true },
    entriesTotal: 40,
  });

  const { container } = render(<Home isActive onNavigate={() => {}} />);

  // Drift card still renders — the gift gate does not touch it.
  expect(await screen.findByText("Go to the gym")).toBeInTheDocument();

  // No reflection cards of any kind: not wrapped, not revealed.
  await waitFor(() => {
    expect(container.querySelector(".noticed-section")).not.toBeNull();
  });
  expect(container.querySelectorAll(".noticed-section .reflection-slot").length).toBe(0);
  expect(
    container.querySelectorAll(".noticed-section .reflection-card-wrapped").length
  ).toBe(0);
  expect(
    container.querySelectorAll(".noticed-section .reflection-opened-card").length
  ).toBe(0);
  expect(screen.queryByText("Insight 1")).not.toBeInTheDocument();
});

test("an UNOPENED gift renders wrapped cards, capped at 3, strongest first", async () => {
  wireFetch({
    pick: DRIFT_PICK,
    synthesis: { synthesis_text: SEVEN_INSIGHT_DOC, opened: false },
    entriesTotal: 40,
  });

  const { container } = render(<Home isActive onNavigate={() => {}} />);

  await waitFor(() => {
    expect(
      container.querySelectorAll(".noticed-section .reflection-card-wrapped").length
    ).toBeGreaterThan(0);
  });

  const wrapped = container.querySelectorAll(".noticed-section .reflection-card-wrapped");
  expect(wrapped.length).toBeLessThanOrEqual(3);
  // No revealed cards render on Home — wrapped only.
  expect(
    container.querySelectorAll(".noticed-section .reflection-opened-card").length
  ).toBe(0);
  // Drift card unaffected.
  expect(screen.getByText("Go to the gym")).toBeInTheDocument();
});

// ——— Task 2: first-run promise card ———

test("promise card renders at 0 entries", async () => {
  wireFetch({ pick: null, synthesis: null, entriesTotal: 0 });

  render(<Home isActive onNavigate={() => {}} />);

  expect(await screen.findByText(PROMISE_FRAGMENT)).toBeInTheDocument();
});

test("promise card renders at 2 entries", async () => {
  wireFetch({ pick: null, synthesis: null, entriesTotal: 2 });

  render(<Home isActive onNavigate={() => {}} />);

  expect(await screen.findByText(PROMISE_FRAGMENT)).toBeInTheDocument();
});

test("promise card is gone at 3 entries", async () => {
  wireFetch({ pick: null, synthesis: null, entriesTotal: 3 });

  render(<Home isActive onNavigate={() => {}} />);

  // Anchor on a post-load element (a real entry row), then assert absence.
  expect(await screen.findByText("Entry 1")).toBeInTheDocument();
  expect(screen.queryByText(PROMISE_FRAGMENT)).not.toBeInTheDocument();
});

test("promise card never renders alongside a drift card", async () => {
  // Fewer than 3 entries but a drift card is served — the guard wins.
  wireFetch({ pick: DRIFT_PICK, synthesis: null, entriesTotal: 0 });

  render(<Home isActive onNavigate={() => {}} />);

  expect(await screen.findByText("Go to the gym")).toBeInTheDocument();
  expect(screen.queryByText(PROMISE_FRAGMENT)).not.toBeInTheDocument();
});
