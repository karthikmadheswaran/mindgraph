import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Dashboard from "./Dashboard";
import { authHeaders } from "../utils/auth";
import { daysSinceLastMention } from "../utils/dateHelpers";
import {
  clearDashboardSnapshotCache,
  getCachedDashboardSnapshot,
  prefetchDashboardSnapshot,
} from "../utils/dashboardSnapshot";

jest.mock("./AnimatedView", () => ({
  __esModule: true,
  default: ({ children }) => children,
}));

jest.mock("./KnowledgeGraph", () => ({
  __esModule: true,
  default: () => <div data-testid="knowledge-graph" />,
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

const pendingDeadline = {
  id: "deadline-1",
  description: "Finish report",
  due_date: "2026-04-10T00:00:00Z",
  status: "pending",
};

const snoozedDeadline = {
  id: "deadline-2",
  description: "Send invoice",
  due_date: "2026-04-12T00:00:00Z",
  status: "snoozed",
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

function jsonResponse(payload, ok = true) {
  return Promise.resolve({
    ok,
    status: ok ? 200 : 500,
    json: () => Promise.resolve(payload),
  });
}

function createFetchHandler({
  entries = [],
  deadlines = [pendingDeadline, snoozedDeadline],
  projects = [activeProject, hiddenProject],
  progress = { deadlines: [], projects: [] },
  onDeadlinePatch,
  onDeadlineDatePatch,
  onProjectPatch,
  onDeadlineDelete,
  onProjectDelete,
} = {}) {
  return (input, options = {}) => {
    const url = typeof input === "string" ? input : input.url;
    const method = options.method || "GET";

    if (url.endsWith("/entries")) {
      return jsonResponse({ entries });
    }

    if (url === "https://mindgraph-production.up.railway.app/deadlines?status=pending,snoozed") {
      return jsonResponse({ deadlines });
    }

    if (url === "https://mindgraph-production.up.railway.app/projects?status=active,hidden") {
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

    if (url.endsWith("/insights/patterns")) {
      return jsonResponse({ data: {} });
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

    if (url.endsWith(`/projects/${activeProject.id}`) && method === "DELETE") {
      return onProjectDelete
        ? onProjectDelete(input, options)
        : jsonResponse({ success: true, id: activeProject.id });
    }

    throw new Error(`Unhandled fetch: ${method} ${url}`);
  };
}

describe("Dashboard data and actions", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
    clearDashboardSnapshotCache();
  });

  afterEach(() => {
    clearDashboardSnapshotCache();
    jest.useRealTimers();
    jest.clearAllMocks();
  });

  test("fetches pending and snoozed deadlines once, then toggles visibility locally", async () => {
    let rejectPatchRequest;

    global.fetch.mockImplementation(
      createFetchHandler({
        onDeadlinePatch: () =>
          new Promise((_, reject) => {
            rejectPatchRequest = reject;
          }),
      })
    );

    render(<Dashboard isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Finish report")).toBeInTheDocument();
    expect(screen.queryByText("Send invoice")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(authHeaders).toHaveBeenCalled();
      expect(
        global.fetch.mock.calls.some(
          ([url]) =>
            url ===
            "https://mindgraph-production.up.railway.app/deadlines?status=pending,snoozed"
        )
      ).toBe(true);
    });

    const deadlineFetchCountBeforeToggle = global.fetch.mock.calls.filter(
      ([url]) =>
        url ===
        "https://mindgraph-production.up.railway.app/deadlines?status=pending,snoozed"
    ).length;

    userEvent.click(screen.getByLabelText(/show snoozed/i));

    expect(await screen.findByText("Send invoice")).toBeInTheDocument();
    const deadlineFetchCountAfterToggle = global.fetch.mock.calls.filter(
      ([url]) =>
        url ===
        "https://mindgraph-production.up.railway.app/deadlines?status=pending,snoozed"
    ).length;
    expect(deadlineFetchCountAfterToggle).toBe(deadlineFetchCountBeforeToggle);

    userEvent.click(screen.getByLabelText(/snooze finish report/i));

    expect(await screen.findByText("Finish report")).toBeInTheDocument();

    rejectPatchRequest(new Error("Failed to update deadline. Please try again."));

    expect(
      await screen.findByText("Failed to update deadline. Please try again.")
    ).toBeInTheDocument();
    expect(await screen.findByText("Finish report")).toBeInTheDocument();
  });

  test("fetches active and hidden projects once, toggles locally, and omits archive", async () => {
    let rejectPatchRequest;

    global.fetch.mockImplementation(
      createFetchHandler({
        onProjectPatch: () =>
          new Promise((_, reject) => {
            rejectPatchRequest = reject;
          }),
      })
    );

    render(<Dashboard isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Mindgraph")).toBeInTheDocument();
    expect(screen.queryByText("App.js")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/archive mindgraph/i)).not.toBeInTheDocument();

    await waitFor(() => {
      expect(
        global.fetch.mock.calls.some(
          ([url]) =>
            url ===
            "https://mindgraph-production.up.railway.app/projects?status=active,hidden"
        )
      ).toBe(true);
    });

    const projectFetchCountBeforeToggle = global.fetch.mock.calls.filter(
      ([url]) =>
        url ===
        "https://mindgraph-production.up.railway.app/projects?status=active,hidden"
    ).length;

    userEvent.click(screen.getByLabelText(/show hidden/i));

    expect(await screen.findByText("App.js")).toBeInTheDocument();
    const projectFetchCountAfterToggle = global.fetch.mock.calls.filter(
      ([url]) =>
        url ===
        "https://mindgraph-production.up.railway.app/projects?status=active,hidden"
    ).length;
    expect(projectFetchCountAfterToggle).toBe(projectFetchCountBeforeToggle);

    userEvent.click(screen.getByLabelText(/hide mindgraph/i));

    expect(await screen.findByText("Mindgraph")).toBeInTheDocument();
    expect(await screen.findAllByText("Hidden")).toHaveLength(2);

    rejectPatchRequest(new Error("Failed to update project. Please try again."));

    expect(
      await screen.findByText("Failed to update project. Please try again.")
    ).toBeInTheDocument();
    expect(await screen.findByText("Mindgraph")).toBeInTheDocument();
  });

  test("opens the custom picker from the deadline badge and saves through the date endpoint", async () => {
    global.fetch.mockImplementation(
      createFetchHandler({
        onDeadlineDatePatch: (_input, options) =>
          jsonResponse({
            ...pendingDeadline,
            due_date: JSON.parse(options.body).due_date,
          }),
      })
    );

    render(<Dashboard isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Finish report")).toBeInTheDocument();

    userEvent.click(screen.getByLabelText(/edit date for finish report/i));

    expect(
      await screen.findByRole("dialog", { name: /deadline date picker/i })
    ).toBeInTheDocument();

    userEvent.click(screen.getByRole("button", { name: /save deadline date/i }));

    await waitFor(() => {
      expect(
        global.fetch.mock.calls.some(([url, options]) => {
          if (
            url !==
              "https://mindgraph-production.up.railway.app/deadlines/deadline-1/date" ||
            options?.method !== "PATCH"
          ) {
            return false;
          }

          return JSON.parse(options.body).due_date === "2026-04-10";
        })
      ).toBe(true);
    });
  });

  test("marks a project as completed and removes it from the active list immediately", async () => {
    global.fetch.mockImplementation(createFetchHandler());

    render(<Dashboard isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Mindgraph")).toBeInTheDocument();

    userEvent.click(screen.getByLabelText(/complete mindgraph/i));

    expect(screen.queryByText("Mindgraph")).not.toBeInTheDocument();
    expect(
      getCachedDashboardSnapshot({ userId: TEST_USER_ID })?.progress?.projects?.[0]
        ?.name
    ).toBe("Mindgraph");

    await waitFor(() => {
      expect(
        global.fetch.mock.calls.some(([url, options]) => {
          if (
            url !==
              "https://mindgraph-production.up.railway.app/projects/project-1/status" ||
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

    render(<Dashboard isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Finish report")).toBeInTheDocument();

    userEvent.click(screen.getByLabelText(/mark finish report as done/i));

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

  test("marks a project as completed in shared progress immediately and rolls back on failure", async () => {
    let rejectPatchRequest;

    global.fetch.mockImplementation(
      createFetchHandler({
        onProjectPatch: () =>
          new Promise((_, reject) => {
            rejectPatchRequest = reject;
          }),
      })
    );

    render(<Dashboard isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Mindgraph")).toBeInTheDocument();

    userEvent.click(screen.getByLabelText(/complete mindgraph/i));

    await waitFor(() => {
      expect(screen.queryByText("Mindgraph")).not.toBeInTheDocument();
      expect(
        getCachedDashboardSnapshot({ userId: TEST_USER_ID })?.progress?.projects?.[0]
          ?.name
      ).toBe("Mindgraph");
    });

    rejectPatchRequest(new Error("Failed to update project. Please try again."));

    expect(
      await screen.findByText("Failed to update project. Please try again.")
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Mindgraph")).toBeInTheDocument();
      expect(
        getCachedDashboardSnapshot({ userId: TEST_USER_ID })?.progress?.projects
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

    render(<Dashboard isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Finish report")).toBeInTheDocument();

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

  test("fires project delete only after the 5 second undo window passes", async () => {
    jest.useFakeTimers();
    const deleteSpy = jest.fn(() =>
      jsonResponse({ success: true, id: activeProject.id })
    );

    global.fetch.mockImplementation(
      createFetchHandler({
        onProjectDelete: deleteSpy,
      })
    );

    render(<Dashboard isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Mindgraph")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/delete mindgraph/i));

    expect(deleteSpy).not.toHaveBeenCalled();

    act(() => {
      jest.advanceTimersByTime(4999);
    });
    expect(deleteSpy).not.toHaveBeenCalled();

    act(() => {
      jest.advanceTimersByTime(1);
    });

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledTimes(1);
    });
  });

  test("uses a prefetched snapshot cache without showing the loading state", async () => {
    global.fetch.mockImplementation(createFetchHandler());

    await prefetchDashboardSnapshot({ userId: TEST_USER_ID });

    render(<Dashboard isActive userId={TEST_USER_ID} />);

    expect(screen.queryByText(/loading your journal/i)).not.toBeInTheDocument();
    expect(screen.getByText("Mindgraph")).toBeInTheDocument();

    const projectFetchCount = global.fetch.mock.calls.filter(
      ([url]) =>
        url ===
        "https://mindgraph-production.up.railway.app/projects?status=active,hidden"
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
        url ===
          "https://mindgraph-production.up.railway.app/deadlines?status=pending,snoozed"
      ) {
        failDeadlineOnce = false;
        return jsonResponse({}, false);
      }

      return successfulHandler(input, options);
    });

    await expect(
      prefetchDashboardSnapshot({ userId: TEST_USER_ID })
    ).rejects.toThrow("Failed to fetch deadlines");

    render(<Dashboard isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Mindgraph")).toBeInTheDocument();
    expect(screen.queryByText(/loading your journal/i)).not.toBeInTheDocument();

    const deadlineFetchCount = global.fetch.mock.calls.filter(
      ([url]) =>
        url ===
        "https://mindgraph-production.up.railway.app/deadlines?status=pending,snoozed"
    ).length;

    expect(deadlineFetchCount).toBe(2);
  });

  test("Active Projects and the Noticed insight show the SAME days-quiet for one entity", async () => {
    // Consolidation lock: both staleness surfaces, one entity, one number, and
    // it must equal the canonical accessor. RED before Part B (card reads
    // status_changed_at -> a large number; insight reads the frozen
    // days_since_mention=32); GREEN after (both route through daysSinceLastMention).
    const lastMentioned = "2026-05-15T11:57:47Z";
    const projectWithMention = {
      id: "project-1",
      name: "Mindgraph",
      status: "active",
      mention_count: 29,
      running_summary: "Main product work",
      last_mentioned_at: lastMentioned,
      status_changed_at: "2026-04-09T13:24:00Z", // activation date — the wrong, stale source
    };
    const forgottenInsight = {
      insight_type: "forgotten_projects",
      content: JSON.stringify({
        stale: [
          {
            name: "mindgraph",
            type: "project",
            mention_count: 29,
            days_since_mention: 32, // frozen, baked-at-regen value
            last_mentioned: "2026-05-15",
            context: "",
          },
        ],
        active: [],
        stale_count: 1,
        active_count: 0,
      }),
    };

    // Self-contained handler: satisfies every snapshot URL so nothing throws
    // and the project actually renders. (The shared createFetchHandler is not
    // used here because its /deadlines mock URL predates the snapshot's
    // ",missed" variant — a pre-existing, unrelated test drift.)
    global.fetch.mockImplementation((input) => {
      const url = typeof input === "string" ? input : input.url;
      if (url.includes("/insights/patterns")) return jsonResponse({ data: {} });
      if (url.includes("/insights/tagline")) return jsonResponse({});
      if (url.endsWith("/insights")) return jsonResponse({ insights: [forgottenInsight] });
      if (url.includes("/deadlines")) return jsonResponse({ deadlines: [] });
      if (url.includes("/projects")) return jsonResponse({ projects: [projectWithMention] });
      if (url.includes("/stats/dashboard")) return jsonResponse({});
      if (url.endsWith("/progress")) return jsonResponse({ deadlines: [], projects: [] });
      if (url.endsWith("/entities")) return jsonResponse({ entities: [] });
      if (url.endsWith("/entity-relations")) return jsonResponse({ relations: [] });
      if (url.endsWith("/entries")) return jsonResponse({ entries: [] });
      return jsonResponse({});
    });

    const { container } = render(<Dashboard isActive userId={TEST_USER_ID} />);

    // Wait for the project card (surface #1) and the Noticed insight kicker
    // (surface #2, fetched async) to both render their "days quiet" numbers.
    await screen.findByText("Mindgraph");
    await waitFor(() => {
      const kicker = container.querySelector(".dthread-kicker");
      if (!kicker || !/QUIET FOR \d+ DAYS/.test(kicker.textContent)) {
        throw new Error("Noticed insight not rendered yet");
      }
    });

    const projMeta = container.querySelector(".proj-meta").textContent; // "Stalled · N days quiet"
    const kicker = container.querySelector(".dthread-kicker").textContent; // "... QUIET FOR N DAYS"
    const projN = Number(/(\d+)\s*days quiet/i.exec(projMeta)[1]);
    const insightN = Number(/QUIET FOR (\d+) DAYS/.exec(kicker)[1]);

    expect(projN).toBe(insightN);
    expect(projN).toBe(daysSinceLastMention(lastMentioned));
  });

  test("deadline action menu Delete removes the row optimistically, offers undo, and does not hard-delete during the window", async () => {
    const deleteSpy = jest.fn(() =>
      jsonResponse({ success: true, id: pendingDeadline.id })
    );

    // Self-contained, loosely-matched fetch mock. The shared createFetchHandler
    // pins /deadlines to "?status=pending,snoozed", which predates the snapshot's
    // ",missed" variant (the pre-existing test drift documented in STATE.md) and
    // would otherwise stop the row from rendering here. Match by substring so the
    // snapshot loads and the deadline appears.
    global.fetch.mockImplementation((input, options = {}) => {
      const url = typeof input === "string" ? input : input.url;
      const method = options.method || "GET";
      if (url.includes("/deadlines/") && method === "DELETE") {
        return deleteSpy(input, options);
      }
      if (url.includes("/deadlines")) return jsonResponse({ deadlines: [pendingDeadline] });
      if (url.includes("/projects")) return jsonResponse({ projects: [] });
      if (url.endsWith("/progress")) return jsonResponse({ deadlines: [], projects: [] });
      if (url.endsWith("/entities")) return jsonResponse({ entities: [] });
      if (url.endsWith("/entity-relations")) return jsonResponse({ relations: [] });
      if (url.includes("/insights/patterns")) return jsonResponse({ data: {} });
      if (url.includes("/insights/tagline")) return jsonResponse({});
      if (url.endsWith("/insights")) return jsonResponse({ insights: [] });
      if (url.includes("/stats/dashboard")) return jsonResponse({});
      if (url.endsWith("/entries")) return jsonResponse({ entries: [] });
      return jsonResponse({});
    });

    render(<Dashboard isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Finish report")).toBeInTheDocument();

    // Open the ⋯ action menu, then click the new Delete item. Reaching the
    // Delete button at all proves it lives in renderDeadlineRow's menu.
    fireEvent.click(screen.getByLabelText(/actions for finish report/i));
    fireEvent.click(screen.getByLabelText(/delete finish report/i));

    // scheduleDelete("deadline", …) ran: optimistic removal + undo toast, and
    // the destructive hard delete is deferred behind the 5s window.
    expect(screen.queryByText("Finish report")).not.toBeInTheDocument();
    expect(await screen.findByText("Deadline deleted.")).toBeInTheDocument();
    expect(deleteSpy).not.toHaveBeenCalled();

    // Undo is the only safety net (hard row delete, no deleted_at): it restores
    // the row and the DELETE never fires.
    fireEvent.click(
      screen.getByRole("button", {
        name: /undo deadline delete for finish report/i,
      })
    );

    expect(await screen.findByText("Finish report")).toBeInTheDocument();
    expect(deleteSpy).not.toHaveBeenCalled();
  });
});
