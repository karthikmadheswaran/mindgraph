import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Dashboard from "./Dashboard";
import { authHeaders } from "../utils/auth";
import {
  clearDashboardSnapshotCache,
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
    json: () => Promise.resolve(payload),
  });
}

function createFetchHandler({
  entries = [],
  deadlines = [pendingDeadline, snoozedDeadline],
  projects = [activeProject, hiddenProject],
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
});
