import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Journal from "./Journal";
import { authHeaders } from "../utils/auth";
import {
  clearDashboardSnapshotCache,
  getCachedDashboardSnapshot,
  prefetchDashboardSnapshot,
} from "../utils/dashboardSnapshot";

// Journal v2: ONE scrollable life view — On your plate → Patterns → Intentions
// → Entries. No sub-tabs, infinite scroll as the single pagination mechanism,
// filters collapsed behind one "Filter" control, empty sections collapse.
// Behavior tests (delete undo / multi-delete / bulk dismiss / snapshot cache)
// are carried over from the tabbed Journal — same actions, same guarantees.

jest.mock("./AnimatedView", () => ({
  __esModule: true,
  default: ({ children }) => children,
}));

jest.mock("../utils/auth", () => ({
  __esModule: true,
  API: "https://mindgraph-production.up.railway.app",
  authHeaders: jest.fn(),
}));

const TEST_USER_ID = "user-1";
const API_BASE = "https://mindgraph-production.up.railway.app";

const pendingDeadline = {
  id: "deadline-1",
  description: "Finish report",
  due_date: "2026-04-10T00:00:00Z",
  status: "pending",
};

const activeProject = {
  id: "project-1",
  name: "Mindgraph",
  status: "active",
  mention_count: 7,
  running_summary: "Main product work",
};

const hiddenProject = {
  id: "project-2",
  name: "App.js",
  status: "hidden",
  mention_count: 2,
  running_summary: "A junk inferred project",
};

const intentionA = {
  id: "intent-1",
  text: "start working out",
  is_drifting: true,
  drift_days: 30,
  reference_count: 1,
  status: "active",
  first_stated_at: "2026-06-01T00:00:00Z",
  last_referenced_at: "2026-06-01T00:00:00Z",
};

const intentionB = {
  id: "intent-2",
  text: "call the bank",
  is_drifting: true,
  drift_days: 20,
  reference_count: 1,
  status: "active",
  first_stated_at: "2026-06-10T00:00:00Z",
  last_referenced_at: "2026-06-10T00:00:00Z",
};

const TWO_INSIGHT_DOC = "**Insight 1**\nBody one.\n\n**Insight 2**\nBody two.";

function jsonResponse(payload, ok = true) {
  return Promise.resolve({
    ok,
    status: ok ? 200 : 500,
    json: () => Promise.resolve(payload),
  });
}

function makeEntries(count, offset = 0) {
  return Array.from({ length: count }, (_, i) => ({
    id: `e-${offset + i + 1}`,
    auto_title: `Entry ${offset + i + 1}`,
    raw_text: `Body of entry ${offset + i + 1}`,
    created_at: `2026-06-${String(30 - ((offset + i) % 28)).padStart(2, "0")}T10:00:00Z`,
    status: "completed",
  }));
}

function createFetchHandler({
  deadlines = [pendingDeadline],
  projects = [activeProject, hiddenProject],
  intentions = [],
  synthesis = null,
  entriesTotal = 0,
  entriesPageSize = 10,
  progress = { deadlines: [], projects: [] },
  attentionMix = { categories: [], weeks: [], tagged_entries: 0 },
  gravity = { window_days: 30, total_entries: 0, prior_total_entries: 0, entities: [] },
  onDeadlinePatch,
  onDeadlineDatePatch,
  onProjectPatch,
  onDeadlineDelete,
  onIntentionDismiss,
} = {}) {
  return (input, options = {}) => {
    const url = typeof input === "string" ? input : input.url;
    const method = options.method || "GET";

    if (url.includes("/patterns/attention-mix")) {
      return jsonResponse(attentionMix);
    }

    if (url.includes("/patterns/gravity")) {
      return jsonResponse(gravity);
    }

    if (url.includes("/entries/filter-options")) {
      return jsonResponse({ mood: [], person: [], category: [] });
    }

    if (url.includes("/entries")) {
      const pageMatch = /[?&]page=(\d+)/.exec(url);
      const page = pageMatch ? Number(pageMatch[1]) : 1;
      const start = (page - 1) * entriesPageSize;
      const count = Math.max(0, Math.min(entriesPageSize, entriesTotal - start));
      return jsonResponse({
        entries: makeEntries(count, start),
        total_count: entriesTotal,
      });
    }

    if (url === `${API_BASE}/deadlines?status=pending,snoozed,missed`) {
      return jsonResponse({ deadlines });
    }

    if (url === `${API_BASE}/projects?status=active,hidden`) {
      return jsonResponse({ projects });
    }

    if (url.endsWith("/progress")) {
      return jsonResponse({ progress, ...progress });
    }

    if (url.endsWith("/entities")) {
      return jsonResponse({ entities: [] });
    }

    if (url.endsWith("/entity-relations")) {
      return jsonResponse({ relations: [] });
    }

    if (url.includes("/insights/patterns")) {
      return jsonResponse({ data: {} });
    }

    if (url.includes("/insights/tagline")) {
      return jsonResponse({});
    }

    if (url.includes("/insights/synthesis")) {
      return jsonResponse({ data: synthesis });
    }

    if (url.includes("/stats/dashboard")) {
      return jsonResponse({});
    }

    if (url.includes("/intentions/drift")) {
      return jsonResponse({ intentions });
    }

    if (url.includes("/intentions/") && url.endsWith("/dismiss") && method === "POST") {
      return onIntentionDismiss
        ? onIntentionDismiss(input, options)
        : jsonResponse({ success: true });
    }

    if (url.endsWith(`/deadlines/${pendingDeadline.id}/status`) && method === "PATCH") {
      return onDeadlinePatch
        ? onDeadlinePatch(input, options)
        : jsonResponse({ ...pendingDeadline, status: JSON.parse(options.body).status });
    }

    if (url.endsWith(`/deadlines/${pendingDeadline.id}/date`) && method === "PATCH") {
      return onDeadlineDatePatch
        ? onDeadlineDatePatch(input, options)
        : jsonResponse({ ...pendingDeadline, due_date: "2026-04-10" });
    }

    if (url.endsWith(`/deadlines/${pendingDeadline.id}`) && method === "DELETE") {
      return onDeadlineDelete
        ? onDeadlineDelete(input, options)
        : jsonResponse({ success: true, id: pendingDeadline.id });
    }

    if (url.includes("/projects/") && url.endsWith("/status") && method === "PATCH") {
      return onProjectPatch
        ? onProjectPatch(input, options)
        : jsonResponse({ ...activeProject, status: JSON.parse(options.body).status });
    }

    throw new Error(`Unhandled fetch: ${method} ${url}`);
  };
}

// jsdom has no IntersectionObserver — capture instances so tests can fire
// the sentinel intersection by hand.
let ioInstances;

function intersectSentinel() {
  ioInstances.forEach((io) => io.cb([{ isIntersecting: true }]));
}

const sectionHeaders = (container) =>
  Array.from(container.querySelectorAll(".journal-view h2")).map((h) =>
    h.textContent.trim()
  );

describe("Journal single-page life view", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
    authHeaders.mockResolvedValue({
      Authorization: "Bearer test-token",
      "Content-Type": "application/json",
    });
    ioInstances = [];
    global.IntersectionObserver = class {
      constructor(cb) {
        this.cb = cb;
        ioInstances.push(this);
      }
      observe() {}
      unobserve() {}
      disconnect() {}
    };
    clearDashboardSnapshotCache();
  });

  afterEach(() => {
    clearDashboardSnapshotCache();
    jest.useRealTimers();
    jest.clearAllMocks();
  });

  test("renders the four sections in order with no tab bar", async () => {
    global.fetch.mockImplementation(
      createFetchHandler({
        intentions: [intentionA],
        synthesis: { synthesis_text: TWO_INSIGHT_DOC, opened: true },
        entriesTotal: 3,
      })
    );

    const { container } = render(<Journal isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Finish report")).toBeInTheDocument();
    await screen.findByText("Start working out");
    await screen.findByText("Insight 1");
    await screen.findByText("Entry 1");

    const headers = sectionHeaders(container);
    const order = [
      headers.findIndex((h) => /^On your plate/i.test(h)),
      headers.findIndex((h) => /^Patterns/i.test(h)),
      headers.findIndex((h) => /^Intentions/i.test(h)),
      headers.findIndex((h) => /^Entries/i.test(h)),
    ];
    expect(order.every((i) => i !== -1)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);

    // No sub-tab navigation anywhere.
    expect(container.querySelector(".journal-tabs")).toBeNull();
  });

  // ——— Patterns v1 (founder-gated; docs/designs/graph-v2-patterns.md) ———

  const FOUNDER_USER_ID = "e7bcef72-a66c-4ebe-9c5e-0a98b5f696d8";

  const founderAttentionMix = {
    categories: ["work", "personal", "health", "finance", "family", "hobby", "travel", "education", "other"],
    weeks: [
      { week_start: "2026-07-06", counts: { work: 3, health: 1 } },
      { week_start: "2026-07-13", counts: { work: 2, personal: 2 } },
    ],
    tagged_entries: 8,
  };

  const founderGravity = {
    window_days: 30,
    total_entries: 12,
    prior_total_entries: 9,
    entities: [
      {
        entity_id: "ent-1",
        name: "Rahul",
        entity_type: "person",
        entry_count: 5,
        share: 0.38,
        prior_share: 0.12,
      },
    ],
  };

  test("Patterns v1 is invisible to non-founder accounts — no render, no fetch", async () => {
    global.fetch.mockImplementation(
      createFetchHandler({
        intentions: [intentionA],
        synthesis: { synthesis_text: TWO_INSIGHT_DOC, opened: true },
      })
    );

    render(<Journal isActive userId={TEST_USER_ID} />);

    await screen.findByText("Start working out");
    await screen.findByText("Insight 1");

    expect(screen.queryByText(/Where has my attention been going/i)).toBeNull();
    expect(screen.queryByText(/taking up the most space/i)).toBeNull();
    expect(screen.queryByText(/gone quiet\?/i)).toBeNull();

    const patternsCalls = global.fetch.mock.calls.filter(([input]) =>
      String(typeof input === "string" ? input : input.url).includes("/patterns/")
    );
    expect(patternsCalls).toHaveLength(0);
  });

  test("founder sees the three question-framed Patterns components", async () => {
    global.fetch.mockImplementation(
      createFetchHandler({
        intentions: [intentionA],
        synthesis: null,
        attentionMix: founderAttentionMix,
        gravity: founderGravity,
      })
    );

    render(<Journal isActive userId={FOUNDER_USER_ID} />);

    expect(
      await screen.findByText(/Where has my attention been going/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/taking up the most space/i)).toBeInTheDocument();
    expect(screen.getByText(/gone quiet\?/i)).toBeInTheDocument();

    // Gravity strip: entity + share + trend as data.
    expect(await screen.findByText("Rahul")).toBeInTheDocument();
    expect(screen.getByText(/in 38% of your entries/i)).toBeInTheDocument();
    expect(screen.getByText(/up from 12%/i)).toBeInTheDocument();

    // Drift ledger reuses the drift read path (intention appears in the ledger
    // as well as the Intentions section below).
    const ledgerRows = await screen.findAllByText("Start working out");
    expect(ledgerRows.length).toBeGreaterThanOrEqual(2);
  });

  test("founder Patterns shows quiet sparse states below the data floors", async () => {
    global.fetch.mockImplementation(
      createFetchHandler({
        intentions: [],
        synthesis: null,
        attentionMix: { categories: [], weeks: [], tagged_entries: 2 },
        gravity: { window_days: 30, total_entries: 0, prior_total_entries: 0, entities: [] },
      })
    );

    render(<Journal isActive userId={FOUNDER_USER_ID} />);

    expect(
      await screen.findByText(/Too few entries to see a shape yet/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/No people or projects have taken up space/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/the ledger is quiet/i)).toBeInTheDocument();
  });

  test("empty sections collapse — headers do not render over nothing", async () => {
    global.fetch.mockImplementation(
      createFetchHandler({
        deadlines: [],
        projects: [],
        intentions: [],
        synthesis: null,
        entriesTotal: 0,
      })
    );

    const { container } = render(<Journal isActive userId={TEST_USER_ID} />);

    // Wait for the snapshot + entries to settle (empty state visible).
    await screen.findByText(/nothing here yet/i);

    const headers = sectionHeaders(container);
    expect(headers.some((h) => /^On your plate/i.test(h))).toBe(false);
    expect(headers.some((h) => /^Patterns/i.test(h))).toBe(false);
    expect(headers.some((h) => /^Intentions/i.test(h))).toBe(false);
    expect(headers.some((h) => /^Entries/i.test(h))).toBe(false);
  });

  test("entries paginate by infinite scroll ONLY — no page numbers, no load-more button", async () => {
    global.fetch.mockImplementation(createFetchHandler({ entriesTotal: 25 }));

    const { container } = render(<Journal isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Entry 1")).toBeInTheDocument();
    expect(screen.getByText("Entry 10")).toBeInTheDocument();
    expect(screen.queryByText("Entry 11")).not.toBeInTheDocument();

    // Single mechanism: neither the page-number strip nor the manual button.
    expect(container.querySelector(".entries-pagination")).toBeNull();
    expect(container.querySelector(".entries-page-num")).toBeNull();
    expect(container.querySelector(".entries-load-more")).toBeNull();
    expect(container.querySelector(".entries-sentinel")).not.toBeNull();

    await act(async () => {
      intersectSentinel();
    });

    expect(await screen.findByText("Entry 11")).toBeInTheDocument();
    expect(screen.getByText("Entry 1")).toBeInTheDocument(); // appended, not replaced
  });

  test("filter chips are collapsed behind one Filter control", async () => {
    global.fetch.mockImplementation(createFetchHandler({ entriesTotal: 3 }));

    const { container } = render(<Journal isActive userId={TEST_USER_ID} />);
    expect(await screen.findByText("Entry 1")).toBeInTheDocument();

    // Collapsed by default: no chip row, just the toggle.
    expect(container.querySelector(".entries-filter-row")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /^filter$/i }));
    expect(container.querySelector(".entries-filter-row")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Mood" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^filter$/i }));
    expect(container.querySelector(".entries-filter-row")).toBeNull();
  });

  test("overflow expander reveals hidden projects and keeps toggling local", async () => {
    let rejectPatchRequest;

    global.fetch.mockImplementation(
      createFetchHandler({
        onProjectPatch: () =>
          new Promise((_, reject) => {
            rejectPatchRequest = reject;
          }),
      })
    );

    render(<Journal isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Mindgraph")).toBeInTheDocument();
    expect(screen.queryByText("App.js")).not.toBeInTheDocument();

    const projectFetchCountBefore = global.fetch.mock.calls.filter(
      ([url]) => url === `${API_BASE}/projects?status=active,hidden`
    ).length;

    // The quiet expander carries the overflow (here: 1 hidden project).
    fireEvent.click(screen.getByRole("button", { name: /1 hidden/i }));

    expect(await screen.findByText("App.js")).toBeInTheDocument();
    const projectFetchCountAfter = global.fetch.mock.calls.filter(
      ([url]) => url === `${API_BASE}/projects?status=active,hidden`
    ).length;
    expect(projectFetchCountAfter).toBe(projectFetchCountBefore);

    // Row actions survive on compact rows; failed hide rolls back with a toast.
    fireEvent.click(screen.getByLabelText(/actions for mindgraph/i));
    fireEvent.click(screen.getByRole("button", { name: "Hide" }));

    // The PATCH fires after an async authHeaders() hop — wait for the handler.
    await waitFor(() => expect(rejectPatchRequest).toBeDefined());
    rejectPatchRequest(new Error("Failed to update project. Please try again."));

    expect(
      await screen.findByText("Failed to update project. Please try again.")
    ).toBeInTheDocument();
    expect(await screen.findByText("Mindgraph")).toBeInTheDocument();
  });

  test("opens the picker from the compact deadline row and saves through the date endpoint", async () => {
    global.fetch.mockImplementation(
      createFetchHandler({
        onDeadlineDatePatch: (_input, options) =>
          jsonResponse({
            ...pendingDeadline,
            due_date: JSON.parse(options.body).due_date,
          }),
      })
    );

    render(<Journal isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Finish report")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/actions for finish report/i));
    fireEvent.click(screen.getByRole("button", { name: "Change date" }));

    expect(
      await screen.findByRole("dialog", { name: /deadline date picker/i })
    ).toBeInTheDocument();

    userEvent.click(screen.getByRole("button", { name: /save deadline date/i }));

    await waitFor(() => {
      expect(
        global.fetch.mock.calls.some(([url, options]) => {
          if (
            url !== `${API_BASE}/deadlines/deadline-1/date` ||
            options?.method !== "PATCH"
          ) {
            return false;
          }

          return Boolean(JSON.parse(options.body).due_date);
        })
      ).toBe(true);
    });
  });

  test("marks a deadline as done in shared progress immediately and rolls back on failure", async () => {
    let rejectPatchRequest;

    global.fetch.mockImplementation(
      createFetchHandler({
        onDeadlinePatch: () =>
          new Promise((_, reject) => {
            rejectPatchRequest = reject;
          }),
      })
    );

    render(<Journal isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Finish report")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/mark done: finish report/i));

    await waitFor(() => {
      expect(screen.queryByText("Finish report")).not.toBeInTheDocument();
      expect(
        getCachedDashboardSnapshot({ userId: TEST_USER_ID })?.progress?.deadlines?.[0]
          ?.description
      ).toBe("Finish report");
    });

    rejectPatchRequest(new Error("Failed to update deadline. Please try again."));

    expect(
      await screen.findByText("Failed to update deadline. Please try again.")
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Finish report")).toBeInTheDocument();
      expect(
        getCachedDashboardSnapshot({ userId: TEST_USER_ID })?.progress?.deadlines
      ).toHaveLength(0);
    });
  });

  test("keeps deadline delete pending for 5 seconds and supports undo before the API call", async () => {
    jest.useFakeTimers();
    const deleteSpy = jest.fn(() =>
      jsonResponse({ success: true, id: pendingDeadline.id })
    );

    global.fetch.mockImplementation(
      createFetchHandler({
        onDeadlineDelete: deleteSpy,
      })
    );

    render(<Journal isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Finish report")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/actions for finish report/i));
    fireEvent.click(screen.getByLabelText(/delete finish report/i));

    expect(screen.queryByText("Finish report")).not.toBeInTheDocument();
    expect(await screen.findByText("Deadline deleted.")).toBeInTheDocument();
    expect(deleteSpy).not.toHaveBeenCalled();

    act(() => {
      jest.advanceTimersByTime(4000);
    });

    expect(deleteSpy).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole("button", {
        name: /undo deadline delete for finish report/i,
      })
    );

    expect(await screen.findByText("Finish report")).toBeInTheDocument();
    expect(deleteSpy).not.toHaveBeenCalled();
  });

  test("uses a prefetched snapshot cache without showing the loading state", async () => {
    global.fetch.mockImplementation(createFetchHandler());

    await prefetchDashboardSnapshot({ userId: TEST_USER_ID });

    render(<Journal isActive userId={TEST_USER_ID} />);

    expect(screen.queryByText(/loading your journal/i)).not.toBeInTheDocument();
    expect(screen.getByText("Mindgraph")).toBeInTheDocument();

    const projectFetchCount = global.fetch.mock.calls.filter(
      ([url]) => url === `${API_BASE}/projects?status=active,hidden`
    ).length;

    expect(projectFetchCount).toBe(1);
  });

  test("falls back to a fresh mount fetch after a failed prefetch", async () => {
    const successfulHandler = createFetchHandler();
    let failDeadlineOnce = true;

    global.fetch.mockImplementation((input, options = {}) => {
      const url = typeof input === "string" ? input : input.url;

      if (
        failDeadlineOnce &&
        url === `${API_BASE}/deadlines?status=pending,snoozed,missed`
      ) {
        failDeadlineOnce = false;
        return jsonResponse({}, false);
      }

      return successfulHandler(input, options);
    });

    await expect(
      prefetchDashboardSnapshot({ userId: TEST_USER_ID })
    ).rejects.toThrow("Failed to fetch deadlines");

    render(<Journal isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Finish report")).toBeInTheDocument();
    expect(screen.queryByText(/loading your journal/i)).not.toBeInTheDocument();

    const deadlineFetchCount = global.fetch.mock.calls.filter(
      ([url]) => url === `${API_BASE}/deadlines?status=pending,snoozed,missed`
    ).length;

    expect(deadlineFetchCount).toBe(2);
  });

  test("multi-delete: deleting A then B within 5s removes both, each independently undoable, and fires the correct DELETE id", async () => {
    jest.useFakeTimers();
    const deleteA = jest.fn(() => jsonResponse({ success: true, id: "d-A" }));
    const deleteB = jest.fn(() => jsonResponse({ success: true, id: "d-B" }));
    const A = { id: "d-A", description: "Finish report", due_date: "2030-04-10T00:00:00Z", status: "pending" };
    const B = { id: "d-B", description: "Send invoice", due_date: "2030-04-12T00:00:00Z", status: "pending" };

    const baseHandler = createFetchHandler({ deadlines: [A, B] });
    global.fetch.mockImplementation((input, options = {}) => {
      const url = typeof input === "string" ? input : input.url;
      const method = options.method || "GET";
      if (url.includes("/deadlines/d-A") && method === "DELETE") return deleteA();
      if (url.includes("/deadlines/d-B") && method === "DELETE") return deleteB();
      return baseHandler(input, options);
    });

    render(<Journal isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Finish report")).toBeInTheDocument();
    expect(screen.getByText("Send invoice")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/actions for finish report/i));
    fireEvent.click(screen.getByLabelText(/delete finish report/i));
    fireEvent.click(screen.getByLabelText(/actions for send invoice/i));
    fireEvent.click(screen.getByLabelText(/delete send invoice/i));

    expect(screen.queryByText("Finish report")).not.toBeInTheDocument();
    expect(screen.queryByText("Send invoice")).not.toBeInTheDocument();
    expect(deleteA).not.toHaveBeenCalled();
    expect(deleteB).not.toHaveBeenCalled();

    expect(
      screen.getByRole("button", { name: /undo deadline delete for finish report/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /undo deadline delete for send invoice/i })
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /undo deadline delete for finish report/i })
    );
    expect(await screen.findByText("Finish report")).toBeInTheDocument();
    expect(screen.queryByText("Send invoice")).not.toBeInTheDocument();

    await act(async () => {
      jest.advanceTimersByTime(5000);
    });
    await waitFor(() => expect(deleteB).toHaveBeenCalledTimes(1));
    expect(deleteA).not.toHaveBeenCalled();
  });

  test("bulk dismiss: selected intentions are removed behind one undo window and only fire on expiry", async () => {
    jest.useFakeTimers();
    const dismissSpy = jest.fn(() => jsonResponse({ success: true }));

    global.fetch.mockImplementation(
      createFetchHandler({
        intentions: [intentionA, intentionB],
        onIntentionDismiss: dismissSpy,
      })
    );

    render(<Journal isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Start working out")).toBeInTheDocument();
    expect(screen.getByText("Call the bank")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByLabelText(/select intention: start working out/i));
    fireEvent.click(screen.getByLabelText(/select intention: call the bank/i));
    fireEvent.click(screen.getByRole("button", { name: /dismiss 2 selected/i }));

    expect(screen.queryByText("Start working out")).not.toBeInTheDocument();
    expect(screen.queryByText("Call the bank")).not.toBeInTheDocument();
    expect(await screen.findByText("Dismissed 2 intentions.")).toBeInTheDocument();
    expect(dismissSpy).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole("button", { name: /undo dismissing 2 intentions/i })
    );
    expect(await screen.findByText("Start working out")).toBeInTheDocument();
    expect(screen.getByText("Call the bank")).toBeInTheDocument();
    expect(dismissSpy).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByLabelText(/select intention: start working out/i));
    fireEvent.click(screen.getByLabelText(/select intention: call the bank/i));
    fireEvent.click(screen.getByRole("button", { name: /dismiss 2 selected/i }));

    await act(async () => {
      jest.advanceTimersByTime(5000);
    });

    await waitFor(() => expect(dismissSpy).toHaveBeenCalledTimes(2));
  });

  test("intentions render as raw rows — no drift card framing in Journal", async () => {
    global.fetch.mockImplementation(
      createFetchHandler({ intentions: [intentionA] })
    );

    const { container } = render(<Journal isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Start working out")).toBeInTheDocument();

    // The witness-card apparatus (Drifting pill, po-card) stays Home-only.
    const intentSection = container.querySelector(".journal-intentions");
    expect(intentSection).not.toBeNull();
    expect(intentSection.querySelector(".po-card")).toBeNull();
    expect(screen.queryByText("Drifting")).not.toBeInTheDocument();

    // Raw row still carries the data: days quiet + status + actions.
    expect(intentSection.textContent).toMatch(/30 days quiet/i);
    expect(intentSection.textContent).toMatch(/active/i);
    expect(screen.getByRole("button", { name: /did this/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^dismiss$/i })).toBeInTheDocument();
  });
});
