import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MyProgress from "./MyProgress";
import {
  clearDashboardSnapshotCache,
  getCachedDashboardSnapshot,
  prefetchDashboardSnapshot,
} from "../utils/dashboardSnapshot";

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

function createFetchHandler({ progressState, dashboardState }) {
  return (input, options = {}) => {
    const url = typeof input === "string" ? input : input.url;
    const method = options.method || "GET";

    if (url.endsWith("/entries")) {
      return jsonResponse({ entries: [] });
    }

    if (url.endsWith("/deadlines?status=pending,snoozed")) {
      return jsonResponse({ deadlines: dashboardState.current.deadlines });
    }

    if (url.endsWith("/projects?status=active,hidden")) {
      return jsonResponse({ projects: dashboardState.current.projects });
    }

    if (url.endsWith("/progress") && method === "GET") {
      return jsonResponse(progressState.current);
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

    if (url.includes("/deadlines/") && url.endsWith("/status") && method === "PATCH") {
      const status = JSON.parse(options.body).status;
      const deadlineId = url.split("/deadlines/")[1].split("/status")[0];
      const existingProgressDeadline = progressState.current.deadlines.find(
        (deadline) => deadline.id === deadlineId
      );
      const existingDashboardDeadline = dashboardState.current.deadlines.find(
        (deadline) => deadline.id === deadlineId
      );
      const sourceDeadline =
        existingProgressDeadline || existingDashboardDeadline || missedDeadline;
      const updatedDeadline = {
        ...sourceDeadline,
        status,
        status_changed_at: FIXED_NOW.toISOString(),
      };

      if (status === "pending") {
        progressState.current = {
          ...progressState.current,
          deadlines: progressState.current.deadlines.filter(
            (deadline) => deadline.id !== deadlineId
          ),
        };
        dashboardState.current = {
          ...dashboardState.current,
          deadlines: [
            ...dashboardState.current.deadlines.filter(
              (deadline) => deadline.id !== deadlineId
            ),
            updatedDeadline,
          ],
        };
      } else if (status === "done") {
        progressState.current = {
          ...progressState.current,
          deadlines: progressState.current.deadlines.some(
            (deadline) => deadline.id === deadlineId
          )
            ? progressState.current.deadlines.map((deadline) =>
                deadline.id === deadlineId ? updatedDeadline : deadline
              )
            : [...progressState.current.deadlines, updatedDeadline],
        };
        dashboardState.current = {
          ...dashboardState.current,
          deadlines: dashboardState.current.deadlines.filter(
            (deadline) => deadline.id !== deadlineId
          ),
        };
      }

      return jsonResponse(updatedDeadline);
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
      dashboardState.current = {
        ...dashboardState.current,
        deadlines: dashboardState.current.deadlines.map((deadline) =>
          deadline.id === deadlineId ? { ...deadline, due_date: dueDate } : deadline
        ),
      };

      const updatedDeadline =
        progressState.current.deadlines.find((deadline) => deadline.id === deadlineId) ||
        dashboardState.current.deadlines.find((deadline) => deadline.id === deadlineId);

      return jsonResponse(updatedDeadline);
    }

    if (url.includes("/projects/") && url.endsWith("/status") && method === "PATCH") {
      const status = JSON.parse(options.body).status;
      const projectId = url.split("/projects/")[1].split("/status")[0];
      const existingProgressProject = progressState.current.projects.find(
        (project) => project.id === projectId
      );
      const existingDashboardProject = dashboardState.current.projects.find(
        (project) => project.id === projectId
      );
      const sourceProject =
        existingProgressProject || existingDashboardProject || completedProject;
      const updatedProject = {
        ...sourceProject,
        status,
        status_changed_at: FIXED_NOW.toISOString(),
      };

      if (status === "active") {
        progressState.current = {
          ...progressState.current,
          projects: progressState.current.projects.filter(
            (project) => project.id !== projectId
          ),
        };
        dashboardState.current = {
          ...dashboardState.current,
          projects: [
            ...dashboardState.current.projects.filter(
              (project) => project.id !== projectId
            ),
            updatedProject,
          ],
        };
      }

      return jsonResponse(updatedProject);
    }

    throw new Error(`Unhandled fetch: ${method} ${url}`);
  };
}

describe("MyProgress", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(FIXED_NOW);
    global.fetch = jest.fn();
    clearDashboardSnapshotCache();
  });

  afterEach(() => {
    cleanup();
    act(() => {
      clearDashboardSnapshotCache();
    });
    jest.useRealTimers();
    jest.clearAllMocks();
  });

  test("renders grouped sections from a prefetched shared snapshot without showing the spinner", async () => {
    const progressState = {
      current: {
        deadlines: [thisWeekDone, lastWeekDone, missedDeadline],
        projects: [completedProject],
      },
    };
    const dashboardState = {
      current: {
        deadlines: [],
        projects: [],
      },
    };

    global.fetch.mockImplementation(
      createFetchHandler({ progressState, dashboardState })
    );

    await act(async () => {
      await prefetchDashboardSnapshot({ userId: TEST_USER_ID });
    });

    render(<MyProgress isActive userId={TEST_USER_ID} />);

    expect(screen.queryByText(/loading your progress/i)).not.toBeInTheDocument();
    expect(screen.getByText("Things I Got Done")).toBeInTheDocument();
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

  test("falls back to loading the shared snapshot when no prefetched progress exists", async () => {
    const progressState = {
      current: {
        deadlines: [thisWeekDone],
        projects: [],
      },
    };
    const dashboardState = {
      current: {
        deadlines: [],
        projects: [],
      },
    };

    global.fetch.mockImplementation(
      createFetchHandler({ progressState, dashboardState })
    );

    render(<MyProgress isActive userId={TEST_USER_ID} />);

    expect(screen.getByText(/loading your progress/i)).toBeInTheDocument();
    expect(await screen.findByText("Finish report")).toBeInTheDocument();
    expect(
      global.fetch.mock.calls.some(([url]) => url.endsWith("/progress"))
    ).toBe(true);
  });

  test("always renders warm section-level empty states when there is no progress yet", async () => {
    const progressState = {
      current: {
        deadlines: [],
        projects: [],
      },
    };
    const dashboardState = {
      current: {
        deadlines: [],
        projects: [],
      },
    };

    global.fetch.mockImplementation(
      createFetchHandler({ progressState, dashboardState })
    );

    await act(async () => {
      await prefetchDashboardSnapshot({ userId: TEST_USER_ID });
    });

    render(<MyProgress isActive userId={TEST_USER_ID} />);

    expect(screen.getByText("Things I Got Done")).toBeInTheDocument();
    expect(
      screen.getByText(/your first completed deadline will show up here/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/if something does, it will show up here without judgment/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/completed projects will collect here as your shipped pile grows/i)
    ).toBeInTheDocument();
  });

  test("restore and reopen move items back into the shared dashboard snapshot without refetching progress", async () => {
    const progressState = {
      current: {
        deadlines: [thisWeekDone],
        projects: [completedProject],
      },
    };
    const dashboardState = {
      current: {
        deadlines: [],
        projects: [],
      },
    };

    global.fetch.mockImplementation(
      createFetchHandler({ progressState, dashboardState })
    );

    await act(async () => {
      await prefetchDashboardSnapshot({ userId: TEST_USER_ID });
    });
    const progressFetchCountBeforeRender = global.fetch.mock.calls.filter(
      ([url, options]) =>
        url.endsWith("/progress") && (options?.method || "GET") === "GET"
    ).length;

    render(<MyProgress isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Finish report")).toBeInTheDocument();

    await act(async () => {
      userEvent.click(screen.getByRole("button", { name: /restore/i }));
    });

    await waitFor(() => {
      expect(screen.queryByText("Finish report")).not.toBeInTheDocument();
      expect(
        getCachedDashboardSnapshot({ userId: TEST_USER_ID })?.deadlines?.[0]
          ?.description
      ).toBe("Finish report");
    });

    await act(async () => {
      userEvent.click(screen.getByRole("button", { name: /reopen/i }));
    });

    await waitFor(() => {
      expect(screen.queryByText("Phoenix")).not.toBeInTheDocument();
      expect(
        getCachedDashboardSnapshot({ userId: TEST_USER_ID })?.projects?.[0]?.name
      ).toBe("Phoenix");
    });

    const progressFetchCountAfterActions = global.fetch.mock.calls.filter(
      ([url, options]) =>
        url.endsWith("/progress") && (options?.method || "GET") === "GET"
    ).length;

    expect(progressFetchCountAfterActions).toBe(progressFetchCountBeforeRender);
  });

  test("missed deadlines can be marked done through the shared snapshot", async () => {
    const progressState = {
      current: {
        deadlines: [missedDeadline],
        projects: [],
      },
    };
    const dashboardState = {
      current: {
        deadlines: [],
        projects: [],
      },
    };

    global.fetch.mockImplementation(
      createFetchHandler({ progressState, dashboardState })
    );

    await act(async () => {
      await prefetchDashboardSnapshot({ userId: TEST_USER_ID });
    });

    render(<MyProgress isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Email finance")).toBeInTheDocument();

    await act(async () => {
      userEvent.click(screen.getByRole("button", { name: /actually did it/i }));
    });

    await waitFor(() => {
      expect(
        getCachedDashboardSnapshot({ userId: TEST_USER_ID })?.progress?.deadlines?.[0]
          ?.status
      ).toBe("done");
      expect(screen.getByRole("button", { name: /restore/i })).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /actually did it/i })
      ).not.toBeInTheDocument();
    });
  });

  test("rescheduling a missed deadline moves it out of progress and into dashboard deadlines", async () => {
    const progressState = {
      current: {
        deadlines: [missedDeadline],
        projects: [],
      },
    };
    const dashboardState = {
      current: {
        deadlines: [],
        projects: [],
      },
    };

    global.fetch.mockImplementation(
      createFetchHandler({ progressState, dashboardState })
    );

    await act(async () => {
      await prefetchDashboardSnapshot({ userId: TEST_USER_ID });
    });

    render(<MyProgress isActive userId={TEST_USER_ID} />);

    expect(await screen.findByText("Email finance")).toBeInTheDocument();

    await act(async () => {
      userEvent.click(screen.getByRole("button", { name: /reschedule/i }));
    });
    expect(
      await screen.findByRole("dialog", { name: /deadline date picker/i })
    ).toBeInTheDocument();

    await act(async () => {
      userEvent.click(screen.getByRole("button", { name: /save picked date/i }));
    });

    await waitFor(() => {
      expect(screen.queryByText("Email finance")).not.toBeInTheDocument();
      expect(
        getCachedDashboardSnapshot({ userId: TEST_USER_ID })?.progress?.deadlines
      ).toHaveLength(0);
      expect(
        getCachedDashboardSnapshot({ userId: TEST_USER_ID })?.deadlines?.[0]
          ?.due_date
      ).toBe("2026-04-18");
    });
  });
});
