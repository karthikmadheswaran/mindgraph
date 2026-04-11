import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import AskView from "./AskView";
import { API, authHeaders } from "../utils/auth";

jest.mock("react-markdown", () => ({
  __esModule: true,
  default: ({ children }) => <>{children}</>,
}));

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

function jsonResponse(payload, ok = true) {
  return Promise.resolve({
    ok,
    status: ok ? 200 : 500,
    json: () => Promise.resolve(payload),
  });
}

describe("AskView", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
    window.localStorage.clear();
    authHeaders.mockResolvedValue({
      Authorization: "Bearer test-token",
      "Content-Type": "application/json",
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  test("loads stored conversation history and hides the empty state", async () => {
    global.fetch.mockResolvedValueOnce(
      jsonResponse({
        messages: [
          {
            id: "message-2",
            user_id: "user-1",
            role: "assistant",
            content: "You mentioned MindGraph and a report.",
            created_at: "2026-04-10T09:00:05Z",
            metadata: {},
            entry_id: null,
          },
          {
            id: "message-1",
            user_id: "user-1",
            role: "user",
            content: "What am I working on?",
            created_at: "2026-04-10T09:00:00Z",
            metadata: {},
            entry_id: null,
          },
        ],
        has_more: false,
      })
    );

    render(<AskView isActive />);

    expect(screen.queryByText(/welcome to mindgraph/i)).not.toBeInTheDocument();

    expect(await screen.findByText("What am I working on?")).toBeInTheDocument();
    expect(
      await screen.findByText("You mentioned MindGraph and a report.")
    ).toBeInTheDocument();
    expect(screen.queryByText(/welcome to mindgraph/i)).not.toBeInTheDocument();

    await waitFor(() => {
      expect(authHeaders).toHaveBeenCalled();
      expect(global.fetch).toHaveBeenCalledWith(`${API}/conversations/messages?limit=20`, {
        headers: {
          Authorization: "Bearer test-token",
          "Content-Type": "application/json",
        },
      });
    });
  });

  test("shows welcome state after history finishes loading with no messages", async () => {
    global.fetch.mockResolvedValueOnce(
      jsonResponse({ messages: [], has_more: false })
    );

    render(<AskView isActive />);

    expect(screen.queryByText(/welcome to mindgraph/i)).not.toBeInTheDocument();

    expect(
      await screen.findByText(/write a thought or ask a question to get started/i)
    ).toBeInTheDocument();
  });

  test("opens the memory panel from the header icon", async () => {
    global.fetch
      .mockResolvedValueOnce(jsonResponse({ messages: [], has_more: false }))
      .mockResolvedValueOnce(
        jsonResponse({
          memory: "User is refactoring MindGraph.",
          updated_at: "2026-04-11T10:00:00Z",
        })
      );

    render(<AskView isActive />);

    await screen.findByText(/write a thought or ask a question to get started/i);
    fireEvent.click(screen.getByRole("button", { name: /open memory/i }));

    expect(await screen.findByText("Memory")).toBeInTheDocument();
    expect(
      await screen.findByText("User is refactoring MindGraph.")
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(`${API}/ask/memory`, {
        headers: {
          Authorization: "Bearer test-token",
          "Content-Type": "application/json",
        },
      });
    });
  });

  test("renders completed journal cards without summary, categories, or type labels", async () => {
    global.fetch.mockResolvedValueOnce(
      jsonResponse({
        messages: [
          {
            id: "journal-1",
            user_id: "user-1",
            role: "journal_entry",
            content: "Polished the unified feed until it felt calmer.",
            created_at: "2026-04-11T09:00:00Z",
            metadata: {
              pipeline_stage: "completed",
              auto_title: "Unified Feed Polish",
              summary: "This summary should stay hidden.",
              entities: [
                { name: "MindGraph", type: "project" },
                { name: "Claude", type: "tool" },
              ],
              categories: ["design"],
            },
            entry_id: "entry-1",
          },
        ],
        has_more: false,
      })
    );

    const { container } = render(<AskView isActive />);

    expect(await screen.findByText("Unified Feed Polish")).toBeInTheDocument();
    expect(
      screen.getByText("Polished the unified feed until it felt calmer.")
    ).toBeInTheDocument();
    expect(container.querySelector(".entity-row")).toHaveTextContent("MindGraph");
    expect(screen.getByText("Claude")).toBeInTheDocument();
    expect(screen.queryByText("This summary should stay hidden.")).not.toBeInTheDocument();
    expect(screen.queryByText(/categories/i)).not.toBeInTheDocument();
    expect(screen.queryByText("project")).not.toBeInTheDocument();
    expect(screen.queryByText("tool")).not.toBeInTheDocument();
  });

  test("shows skeleton and mapped pipeline status while journal cards process", async () => {
    global.fetch.mockResolvedValueOnce(
      jsonResponse({
        messages: [
          {
            id: "journal-2",
            user_id: "user-1",
            role: "journal_entry",
            content: "Met with Priya about the graph work.",
            created_at: "2026-04-11T09:00:00Z",
            metadata: {
              pipeline_stage: "entities",
            },
            entry_id: null,
          },
        ],
        has_more: false,
      })
    );

    const { container } = render(<AskView isActive />);

    expect(
      await screen.findByText("Finding people, projects, and tools...")
    ).toBeInTheDocument();
    expect(screen.getByText("Met with Priya about the graph work.")).toBeInTheDocument();
    expect(container.querySelector(".skeleton-bar")).toBeInTheDocument();
    expect(screen.queryByText(/extracting insights/i)).not.toBeInTheDocument();
  });
});
