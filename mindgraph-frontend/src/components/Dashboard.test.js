import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Dashboard from "./Dashboard";
import { authHeaders } from "../utils/auth";

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

function jsonResponse(payload) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(payload),
  });
}

describe("Dashboard deadlines", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("fetches pending and snoozed deadlines once, then toggles visibility locally", async () => {
    let rejectPatchRequest;

    global.fetch.mockImplementation((input, options = {}) => {
      const url = typeof input === "string" ? input : input.url;
      const method = options.method || "GET";

      if (url.endsWith("/entries")) {
        return jsonResponse({ entries: [] });
      }

      if (url === "https://mindgraph-production.up.railway.app/deadlines?status=pending,snoozed") {
        return jsonResponse({ deadlines: [pendingDeadline, snoozedDeadline] });
      }

      if (url === "https://mindgraph-production.up.railway.app/projects?status=active,hidden") {
        return jsonResponse({ projects: [activeProject, hiddenProject] });
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
        return new Promise((_, reject) => {
          rejectPatchRequest = reject;
        });
      }

      throw new Error(`Unhandled fetch: ${method} ${url}`);
    });

    render(<Dashboard isActive />);

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

  test("fetches active and hidden projects once, then toggles visibility locally", async () => {
    let rejectPatchRequest;

    global.fetch.mockImplementation((input, options = {}) => {
      const url = typeof input === "string" ? input : input.url;
      const method = options.method || "GET";

      if (url.endsWith("/entries")) {
        return jsonResponse({ entries: [] });
      }

      if (url === "https://mindgraph-production.up.railway.app/deadlines?status=pending,snoozed") {
        return jsonResponse({ deadlines: [] });
      }

      if (url === "https://mindgraph-production.up.railway.app/projects?status=active,hidden") {
        return jsonResponse({ projects: [activeProject, hiddenProject] });
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

      if (url.endsWith(`/projects/${activeProject.id}/status`) && method === "PATCH") {
        return new Promise((_, reject) => {
          rejectPatchRequest = reject;
        });
      }

      throw new Error(`Unhandled fetch: ${method} ${url}`);
    });

    render(<Dashboard isActive />);

    expect(await screen.findByText("Mindgraph")).toBeInTheDocument();
    expect(screen.queryByText("App.js")).not.toBeInTheDocument();

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
});
