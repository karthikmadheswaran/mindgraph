import { render, screen, waitFor } from "@testing-library/react";
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
});
