import { render, screen, waitFor } from "@testing-library/react";
import Home from "./Home";

// Task A regression (post-restructure hotfix): Home's "Noticed" section must
// stay curated — ONE drift card + at most HOME_MAX_INSIGHTS reflection cards,
// even when the synthesis doc carries its full "keep strongest <=7" load. The
// full set belongs to Journal. Pre-restructure Home (the Write view) rendered
// zero cards; the flood came from rendering the whole gift on Home.

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

const pick = {
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

function jsonResponse(payload, ok = true) {
  return Promise.resolve({
    ok,
    status: ok ? 200 : 500,
    json: () => Promise.resolve(payload),
  });
}

beforeEach(() => {
  // CRA jest runs with resetMocks: true — (re)apply implementations per test.
  supabase.auth.getSession.mockResolvedValue({
    data: { session: { user: { id: "user-1", email: "test@rawtxt.in" } } },
  });
  global.fetch = jest.fn((input) => {
    const url = typeof input === "string" ? input : input.url;
    if (url.includes("/intentions/drift")) {
      return jsonResponse({ threshold_days: 14, pick });
    }
    if (url.includes("/insights/synthesis")) {
      return jsonResponse({
        data: { synthesis_text: SEVEN_INSIGHT_DOC, opened: true },
      });
    }
    if (url.includes("/entries")) {
      return jsonResponse({ entries: [], total_count: 0 });
    }
    return jsonResponse({});
  });
});

afterEach(() => {
  jest.clearAllMocks();
});

test("Noticed renders the single drift pick plus at most 3 reflection cards", async () => {
  const { container } = render(<Home isActive onNavigate={() => {}} />);

  // Drift card (backend pick) renders once.
  expect(await screen.findByText("Go to the gym")).toBeInTheDocument();

  // The opened 7-insight gift must be capped, not rendered wholesale.
  await waitFor(() => {
    expect(
      container.querySelectorAll(".noticed-section .reflection-slot").length
    ).toBeGreaterThan(0);
  });

  const slots = container.querySelectorAll(".noticed-section .reflection-slot");
  expect(slots.length).toBeLessThanOrEqual(3);

  // Cap keeps the STRONGEST (first) insights of the doc.
  expect(screen.getByText("Insight 1")).toBeInTheDocument();
  expect(screen.queryByText("Insight 7")).not.toBeInTheDocument();

  // Exactly one drift po-card; total noticed po-cards = drift + capped insights.
  const noticedCards = container.querySelectorAll(".noticed-section .po-card");
  expect(noticedCards.length).toBeLessThanOrEqual(4); // 1 drift + <=3 insights
});

test("wrapped (unopened) gift is capped the same way", async () => {
  global.fetch.mockImplementation((input) => {
    const url = typeof input === "string" ? input : input.url;
    if (url.includes("/intentions/drift")) {
      return jsonResponse({ threshold_days: 14, pick: null });
    }
    if (url.includes("/insights/synthesis")) {
      return jsonResponse({
        data: { synthesis_text: SEVEN_INSIGHT_DOC, opened: false },
      });
    }
    if (url.includes("/entries")) {
      return jsonResponse({ entries: [], total_count: 0 });
    }
    return jsonResponse({});
  });

  const { container } = render(<Home isActive onNavigate={() => {}} />);

  await waitFor(() => {
    expect(
      container.querySelectorAll(".noticed-section .reflection-card-wrapped").length
    ).toBeGreaterThan(0);
  });

  expect(
    container.querySelectorAll(".noticed-section .reflection-card-wrapped").length
  ).toBeLessThanOrEqual(3);
});
