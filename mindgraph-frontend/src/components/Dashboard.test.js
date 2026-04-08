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
});
