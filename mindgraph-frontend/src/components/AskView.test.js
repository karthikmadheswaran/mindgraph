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
          { role: "user", content: "What am I working on?", created_at: "2026-04-10T09:00:00Z" },
          { role: "assistant", content: "You mentioned MindGraph and a report.", created_at: "2026-04-10T09:00:05Z" },
        ],
      })
    );

    render(<AskView isActive />);

    expect(screen.queryByText(/try asking something like:/i)).not.toBeInTheDocument();

    expect(await screen.findByText("What am I working on?")).toBeInTheDocument();
    expect(
      await screen.findByText("You mentioned MindGraph and a report.")
    ).toBeInTheDocument();
    expect(screen.queryByText(/try asking something like:/i)).not.toBeInTheDocument();

    await waitFor(() => {
      expect(authHeaders).toHaveBeenCalled();
      expect(global.fetch).toHaveBeenCalledWith(`${API}/ask/history`, {
        headers: {
          Authorization: "Bearer test-token",
          "Content-Type": "application/json",
        },
      });
    });
  });

  test("shows suggestions after history finishes loading with no messages", async () => {
    global.fetch.mockResolvedValueOnce(jsonResponse({ messages: [] }));

    render(<AskView isActive />);

    expect(screen.queryByText(/try asking something like:/i)).not.toBeInTheDocument();

    expect(await screen.findByText(/try asking something like:/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /what have i been working on lately\?/i })
    ).toBeInTheDocument();
  });
});
