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

  test("fetches default deadlines, refetches snoozed deadlines, and rolls back a failed optimistic update", async () => {
    let rejectPatchRequest;

    global.fetch.mockImplementation((input, options = {}) => {
      const url = typeof input === "string" ? input : input.url;
      const method = options.method || "GET";

      if (url.endsWith("/entries")) {
        return jsonResponse({ entries: [] });
      }

      if (url.includes("/deadlines?status=pending,snoozed")) {
        return jsonResponse({ deadlines: [pendingDeadline, snoozedDeadline] });
      }

      if (url.endsWith("/deadlines")) {
        return jsonResponse({ deadlines: [pendingDeadline] });
      }

      if (url.includes("/projects?status=active,hidden")) {
        return jsonResponse({ projects: [activeProject, hiddenProject] });
      }

      if (url.endsWith("/projects")) {
        return jsonResponse({ projects: [activeProject] });
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

    await waitFor(() => {
      expect(authHeaders).toHaveBeenCalled();
      expect(
        global.fetch.mock.calls.some(
          ([url]) => url === "https://mindgraph-production.up.railway.app/deadlines"
        )
      ).toBe(true);
    });

    userEvent.click(screen.getByLabelText(/show snoozed/i));

    expect(await screen.findByText("Send invoice")).toBeInTheDocument();

    await waitFor(() => {
      expect(
        global.fetch.mock.calls.some(
          ([url]) =>
            url ===
            "https://mindgraph-production.up.railway.app/deadlines?status=pending,snoozed"
        )
      ).toBe(true);
    });

    userEvent.click(screen.getByLabelText(/snooze finish report/i));

    await waitFor(() => {
      expect(screen.queryByText("Finish report")).not.toBeInTheDocument();
    });

    rejectPatchRequest(new Error("Failed to update deadline. Please try again."));

    expect(
      await screen.findByText("Failed to update deadline. Please try again.")
    ).toBeInTheDocument();
    expect(await screen.findByText("Finish report")).toBeInTheDocument();
  });

  test("fetches default projects, refetches hidden projects, and rolls back a failed optimistic hide", async () => {
    let rejectPatchRequest;

    global.fetch.mockImplementation((input, options = {}) => {
      const url = typeof input === "string" ? input : input.url;
      const method = options.method || "GET";

      if (url.endsWith("/entries")) {
        return jsonResponse({ entries: [] });
      }

      if (url.endsWith("/deadlines")) {
        return jsonResponse({ deadlines: [] });
      }

      if (url.includes("/projects?status=active,hidden")) {
        return jsonResponse({ projects: [activeProject, hiddenProject] });
      }

      if (url.endsWith("/projects")) {
        return jsonResponse({ projects: [activeProject] });
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

    await waitFor(() => {
      expect(
        global.fetch.mock.calls.some(
          ([url]) => url === "https://mindgraph-production.up.railway.app/projects"
        )
      ).toBe(true);
    });

    userEvent.click(screen.getByLabelText(/show hidden/i));

    expect(await screen.findByText("App.js")).toBeInTheDocument();

    await waitFor(() => {
      expect(
        global.fetch.mock.calls.some(
          ([url]) =>
            url ===
            "https://mindgraph-production.up.railway.app/projects?status=active,hidden"
        )
      ).toBe(true);
    });

    userEvent.click(screen.getByLabelText(/hide mindgraph/i));

    await waitFor(() => {
      expect(screen.queryByText("Mindgraph")).not.toBeInTheDocument();
    });

    rejectPatchRequest(new Error("Failed to update project. Please try again."));

    expect(
      await screen.findByText("Failed to update project. Please try again.")
    ).toBeInTheDocument();
    expect(await screen.findByText("Mindgraph")).toBeInTheDocument();
  });
});
