import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Journal from "./Journal";
import { authHeaders } from "../utils/auth";
import {
  clearDashboardSnapshotCache,
  getCachedDashboardSnapshot,
  prefetchDashboardSnapshot,
} from "../utils/dashboardSnapshot";

// Ported from Dashboard.test.js when Today was retired and its stored surfaces
// moved into Journal. Tests of deleted surfaces (masthead/ticker/dthread), the
// dead snoozed-visibility toggle, and the never-wired project delete were
// dropped — see the Phase 2 inventory. Mock URLs use the snapshot's current
// "?status=pending,snoozed,missed" variant (the old suite pinned the stale
// ",missed"-less URL, which is why most of it was red).

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
  first_stated_at: "2026-06-01T00:00:00Z",
  last_referenced_at: "2026-06-01T00:00:00Z",
};

const intentionB = {
  id: "intent-2",
  text: "call the bank",
  is_drifting: true,
  drift_days: 20,
  reference_count: 1,
  first_stated_at: "2026-06-10T00:00:00Z",
  last_referenced_at: "2026-06-10T00:00:00Z",
};

function jsonResponse(payload, ok = true) {
  return Promise.resolve({
    ok,
    status: ok ? 200 : 500,
    json: () => Promise.resolve(payload),
  });
}

function createFetchHandler({
  deadlines = [pendingDeadline],
  projects = [activeProject, hiddenProject],
  intentions = [],
  progress = { deadlines: [], projects: [] },
  onDeadlinePatch,
  onDeadlineDatePatch,
  onProjectPatch,
  onDeadlineDelete,
  onIntentionDismiss,
} = {}) {
  return (input, options = {}) => {
    const url = typeof input === "string" ? input : input.url;
    const method = options.method || "GET";

    if (url.includes("/entries/filter-options")) {
      return jsonResponse({ mood: [], person: [], category: [] });
    }

    if (url.includes("/entries")) {
      return jsonResponse({ entries: [], total_count: 0 });
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

const openDeadlinesTab = async () => {
  fireEvent.click(await screen.findByRole("button", { name: "Deadlines" }));
};

const openProjectsTab = async () => {
  fireEvent.click(await screen.findByRole("button", { name: "Projects" }));
};

const openIntentionsTab = async () => {
  fireEvent.click(await screen.findByRole("button", { name: "Intentions" }));
};

describe("Journal data and actions", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
    clearDashboardSnapshotCache();
  });

  afterEach(() => {
    clearDashboardSnapshotCache();
    jest.useRealTimers();
    jest.clearAllMocks();
  });

  test("fetches projects once, toggles hidden visibility locally, and rolls back a failed hide", async () => {
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
    await openProjectsTab();

    expect(await screen.findByText("Mindgraph")).toBeInTheDocument();
    expect(screen.queryByText("App.js")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(authHeaders).toHaveBeenCalled();
      expect(
        global.fetch.mock.calls.some(
          ([url]) => url === `${API_BASE}/projects?status=active,hidden`
        )
      ).toBe(true);
    });

    const projectFetchCountBeforeToggle = global.fetch.mock.calls.filter(
      ([url]) => url === `${API_BASE}/projects?status=active,hidden`
    ).length;

    fireEvent.click(screen.getByRole("button", { name: /show 1 hidden/i }));

    expect(await screen.findByText("App.js")).toBeInTheDocument();
    const projectFetchCountAfterToggle = global.fetch.mock.calls.filter(
      ([url]) => url === `${API_BASE}/projects?status=active,hidden`
    ).length;
    expect(projectFetchCountAfterToggle).toBe(projectFetchCountBeforeToggle);

    fireEvent.click(screen.getByLabelText(/actions for mindgraph/i));
    fireEvent.click(screen.getByRole("button", { name: "Hide" }));

    // Optimistic: Mindgraph joins the hidden group immediately.
    expect(await screen.findAllByText("Hidden")).not.toHaveLength(0);

    rejectPatchRequest(new Error("Failed to update project. Please try again."));

    expect(
      await screen.findByText("Failed to update project. Please try again.")
    ).toBeInTheDocument();
    expect(await screen.findByText("Mindgraph")).toBeInTheDocument();
  });

  test("opens the custom picker from the deadline actions menu and saves through the date endpoint", async () => {
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
    await openDeadlinesTab();

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

  test("marks a project as completed and removes it from the active list immediately", async () => {
    global.fetch.mockImplementation(createFetchHandler());

    render(<Journal isActive userId={TEST_USER_ID} />);
    await openProjectsTab();

    expect(await screen.findByText("Mindgraph")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/actions for mindgraph/i));
    fireEvent.click(screen.getByRole("button", { name: "Mark complete" }));

    expect(screen.queryByText("Mindgraph")).not.toBeInTheDocument();
    expect(
      getCachedDashboardSnapshot({ userId: TEST_USER_ID })?.progress?.projects?.[0]
        ?.name
    ).toBe("Mindgraph");

    await waitFor(() => {
      expect(
        global.fetch.mock.calls.some(([url, options]) => {
          if (
            url !== `${API_BASE}/projects/project-1/status` ||
            options?.method !== "PATCH"
          ) {
            return false;
          }

          return JSON.parse(options.body).status === "completed";
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
    await openDeadlinesTab();

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
    await openDeadlinesTab();

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

    await openProjectsTab();
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

    await openDeadlinesTab();
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
    await openDeadlinesTab();

    expect(await screen.findByText("Finish report")).toBeInTheDocument();
    expect(screen.getByText("Send invoice")).toBeInTheDocument();

    // Delete A, then delete B WHILE A is still within its 5s window. Under the
    // old single pending-delete slot the 2nd delete was silently dropped; now
    // each gets its own pending state + toast.
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
    await openIntentionsTab();

    expect(await screen.findByText("Start working out")).toBeInTheDocument();
    expect(screen.getByText("Call the bank")).toBeInTheDocument();

    // Enter select mode, select both, bulk dismiss.
    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByLabelText(/select intention: start working out/i));
    fireEvent.click(screen.getByLabelText(/select intention: call the bank/i));
    fireEvent.click(screen.getByRole("button", { name: /dismiss 2 selected/i }));

    // Optimistic removal + one batch undo toast; nothing fired yet.
    expect(screen.queryByText("Start working out")).not.toBeInTheDocument();
    expect(screen.queryByText("Call the bank")).not.toBeInTheDocument();
    expect(await screen.findByText("Dismissed 2 intentions.")).toBeInTheDocument();
    expect(dismissSpy).not.toHaveBeenCalled();

    // Undo restores both without any POST.
    fireEvent.click(
      screen.getByRole("button", { name: /undo dismissing 2 intentions/i })
    );
    expect(await screen.findByText("Start working out")).toBeInTheDocument();
    expect(screen.getByText("Call the bank")).toBeInTheDocument();
    expect(dismissSpy).not.toHaveBeenCalled();

    // Dismiss again and let the window elapse: both POSTs fire.
    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByLabelText(/select intention: start working out/i));
    fireEvent.click(screen.getByLabelText(/select intention: call the bank/i));
    fireEvent.click(screen.getByRole("button", { name: /dismiss 2 selected/i }));

    await act(async () => {
      jest.advanceTimersByTime(5000);
    });

    await waitFor(() => expect(dismissSpy).toHaveBeenCalledTimes(2));
  });
});
