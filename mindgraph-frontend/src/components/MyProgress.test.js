import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MyProgress from "./MyProgress";
import { loadDashboardSnapshot } from "../utils/dashboardSnapshot";

jest.mock("./AnimatedView", () => ({
  __esModule: true,
  default: ({ children }) => children,
}));

jest.mock("./DateTimePicker", () => ({
  __esModule: true,
  default: ({ onSave, onCancel }) => (
    <div role="dialog" aria-label="Deadline date picker">
      <button onClick={() => onSave("2026-04-18")}>Save picked date</button>
      <button onClick={onCancel}>Cancel picked date</button>
    </div>
  ),
}));

jest.mock("../utils/auth", () => ({
  __esModule: true,
  API: "https://mindgraph-production.up.railway.app",
  authHeaders: jest.fn().mockResolvedValue({
    Authorization: "Bearer test-token",
    "Content-Type": "application/json",
  }),
}));

jest.mock("../utils/dashboardSnapshot", () => ({
  __esModule: true,
  loadDashboardSnapshot: jest.fn(() => Promise.resolve({})),
}));

const TEST_USER_ID = "user-1";
const FIXED_NOW = new Date("2026-04-09T12:00:00Z");

const thisWeekDone = {
  id: "deadline-done-this-week",
  description: "Finish report",
  due_date: "2026-04-08",
  status: "done",
  status_changed_at: "2026-04-08T09:30:00Z",
};

const lastWeekDone = {
  id: "deadline-done-last-week",
  description: "Send update",
  due_date: "2026-04-01",
  status: "done",
  status_changed_at: "2026-04-01T11:00:00Z",
};

const missedDeadline = {
  id: "deadline-missed",
  description: "Email finance",
  due_date: "2026-03-20",
  status: "missed",
  status_changed_at: "2026-03-21T10:00:00Z",
};

const completedProject = {
  id: "project-completed",
  name: "Phoenix",
  mention_count: 4,
  first_mentioned_at: "2026-02-02T08:00:00Z",
  status: "completed",
  status_changed_at: "2026-04-07T18:00:00Z",
};

function jsonResponse(payload, ok = true) {
  return Promise.resolve({
    ok,
    status: ok ? 200 : 500,
    json: () => Promise.resolve(payload),
  });
}

function createProgressHandler(progressState) {
  return (input, options = {}) => {
    const url = typeof input === "string" ? input : input.url;
    const method = options.method || "GET";

    if (url.endsWith("/progress") && method === "GET") {
      return jsonResponse(progressState.current);
    }

    if (url.includes("/deadlines/") && url.endsWith("/status") && method === "PATCH") {
      const status = JSON.parse(options.body).status;
      const deadlineId = url.split("/deadlines/")[1].split("/status")[0];
      const existingDeadline = progressState.current.deadlines.find(
        (deadline) => deadline.id === deadlineId
      );

      if (status === "pending") {
        progressState.current = {
          ...progressState.current,
          deadlines: progressState.current.deadlines.filter(
            (deadline) => deadline.id !== deadlineId
          ),
        };
      } else if (status === "done") {
        progressState.current = {
          ...progressState.current,
          deadlines: progressState.current.deadlines.map((deadline) =>
            deadline.id === deadlineId
              ? {
                  ...deadline,
                  status: "done",
                  status_changed_at: FIXED_NOW.toISOString(),
                }
              : deadline
          ),
        };
      }

      return jsonResponse({
        ...existingDeadline,
        status,
        status_changed_at: FIXED_NOW.toISOString(),
      });
    }

    if (url.includes("/deadlines/") && url.endsWith("/date") && method === "PATCH") {
      const dueDate = JSON.parse(options.body).due_date;
      const deadlineId = url.split("/deadlines/")[1].split("/date")[0];
      progressState.current = {
        ...progressState.current,
        deadlines: progressState.current.deadlines.map((deadline) =>
          deadline.id === deadlineId ? { ...deadline, due_date: dueDate } : deadline
        ),
      };

      return jsonResponse({
        ...progressState.current.deadlines.find((deadline) => deadline.id === deadlineId),
      });
    }

    if (url.includes("/projects/") && url.endsWith("/status") && method === "PATCH") {
      const status = JSON.parse(options.body).status;
      const projectId = url.split("/projects/")[1].split("/status")[0];
      const existingProject = progressState.current.projects.find(
        (project) => project.id === projectId
      );

      if (status === "active") {
        progressState.current = {
          ...progressState.current,
          projects: progressState.current.projects.filter(
            (project) => project.id !== projectId
          ),
        };
      }

      return jsonResponse({
        ...existingProject,
        status,
        status_changed_at: FIXED_NOW.toISOString(),
      });
    }

    throw new Error(`Unhandled fetch: ${method} ${url}`);
  };
}

describe("MyProgress", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(FIXED_NOW);
    global.fetch = jest.fn();
    loadDashboardSnapshot.mockClear();
  });

  afterEach(() => {
    jest.useRealTimers();
    jest.clearAllMocks();
  });

  test("renders grouped progress sections from the progress endpoint", async () => {
    const progressState = {
      current: {
        deadlines: [thisWeekDone, lastWeekDone, missedDeadline],
        projects: [completedProject],
      },
    };

    global.fetch.mockImplementation(createProgressHandler(progressState));

    render(<MyProgress isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Things I Got Done")).toBeInTheDocument();
    expect(screen.getByText("Ones That Slipped")).toBeInTheDocument();
    expect(screen.getByText("Projects I Finished")).toBeInTheDocument();
    expect(screen.getByText("Finish report")).toBeInTheDocument();
    expect(screen.getByText("Send update")).toBeInTheDocument();
    expect(screen.getByText("Email finance")).toBeInTheDocument();
    expect(screen.getByText("Phoenix")).toBeInTheDocument();
    expect(screen.getAllByText("This Week").length).toBeGreaterThan(0);
    expect(screen.getByText("Last Week")).toBeInTheDocument();
    expect(screen.getAllByText("Earlier").length).toBeGreaterThan(0);
  });

  test("shows the page-level empty state when there is no progress yet", async () => {
    const progressState = {
      current: {
        deadlines: [],
        projects: [],
      },
    };

    global.fetch.mockImplementation(createProgressHandler(progressState));

    render(<MyProgress isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Nothing here yet.")).toBeInTheDocument();
    expect(
      screen.getByText(/Complete your first deadline or finish a project/i)
    ).toBeInTheDocument();
  });

  test("restore and reopen actions move items back out of progress and refresh the dashboard cache", async () => {
    const progressState = {
      current: {
        deadlines: [thisWeekDone],
        projects: [completedProject],
      },
    };

    global.fetch.mockImplementation(createProgressHandler(progressState));

    render(<MyProgress isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Finish report")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /restore/i }));

    await waitFor(() => {
      expect(screen.queryByText("Finish report")).not.toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole("button", { name: /reopen/i }));

    await waitFor(() => {
      expect(screen.queryByText("Phoenix")).not.toBeInTheDocument();
    });

    expect(loadDashboardSnapshot).toHaveBeenCalledTimes(2);
    expect(loadDashboardSnapshot).toHaveBeenCalledWith({
      force: true,
      userId: TEST_USER_ID,
    });
  });

  test("missed deadlines can be marked done and move into the done section", async () => {
    const progressState = {
      current: {
        deadlines: [missedDeadline],
        projects: [],
      },
    };

    global.fetch.mockImplementation(createProgressHandler(progressState));

    render(<MyProgress isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Email finance")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /actually did it/i }));

    await waitFor(() => {
      expect(screen.getByText("Things I Got Done")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /restore/i })).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /actually did it/i })
      ).not.toBeInTheDocument();
    });
  });

  test("rescheduling a missed deadline saves the new date and returns it to pending", async () => {
    const progressState = {
      current: {
        deadlines: [missedDeadline],
        projects: [],
      },
    };

    global.fetch.mockImplementation(createProgressHandler(progressState));

    render(<MyProgress isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Email finance")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /reschedule/i }));
    expect(
      await screen.findByRole("dialog", { name: /deadline date picker/i })
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /save picked date/i }));

    await waitFor(() => {
      expect(screen.queryByText("Email finance")).not.toBeInTheDocument();
    });

    expect(
      global.fetch.mock.calls.some(([url, options]) => {
        if (
          url !==
            "https://mindgraph-production.up.railway.app/deadlines/deadline-missed/date" ||
          options?.method !== "PATCH"
        ) {
          return false;
        }

        return JSON.parse(options.body).due_date === "2026-04-18";
      })
    ).toBe(true);

    expect(
      global.fetch.mock.calls.some(([url, options]) => {
        if (
          url !==
            "https://mindgraph-production.up.railway.app/deadlines/deadline-missed/status" ||
          options?.method !== "PATCH"
        ) {
          return false;
        }

        return JSON.parse(options.body).status === "pending";
      })
    ).toBe(true);
  });
});
