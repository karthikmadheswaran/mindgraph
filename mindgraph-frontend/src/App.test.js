import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

let authStateChangeCallback;

const mockAuthenticatedSession = {
  user: {
    id: "user-1",
    email: "hello@mindgraph.ai",
  },
};

jest.mock("./supabaseClient", () => ({
  __esModule: true,
  supabase: {
    auth: {
      getSession: jest.fn(() => Promise.resolve({ data: { session: null } })),
      onAuthStateChange: jest.fn((callback) => {
        authStateChangeCallback = callback;
        return {
          data: { subscription: { unsubscribe: jest.fn() } },
        };
      }),
      signOut: jest.fn(),
      signUp: jest.fn(),
      signInWithPassword: jest.fn(),
    },
  },
}));

jest.mock("./utils/dashboardSnapshot", () => ({
  __esModule: true,
  clearDashboardSnapshotCache: jest.fn(),
  loadDashboardSnapshot: jest.fn(() => Promise.resolve({ entries: [] })),
  prefetchDashboardSnapshot: jest.fn(() => Promise.resolve({ entries: [] })),
  updateDashboardSnapshot: jest.fn(),
}));

jest.mock("./components/LandingPage", () => ({
  __esModule: true,
  default: ({ onGetStarted }) => (
    <div>
      <button onClick={onGetStarted}>Start journaling</button>
    </div>
  ),
}));

jest.mock("./components/AuthView", () => ({
  __esModule: true,
  default: ({ onAuth }) => (
    <button onClick={() => onAuth(mockAuthenticatedSession)}>Complete auth</button>
  ),
}));

jest.mock("./components/Sidebar", () => ({
  __esModule: true,
  default: ({ onBrandClick, onViewChange }) => (
    <div data-testid="sidebar">
      <button onClick={onBrandClick}>Brand</button>
      <button onClick={() => onViewChange("write")}>Go Write</button>
      <button onClick={() => onViewChange("dashboard")}>Go Dashboard</button>
      <button onClick={() => onViewChange("ask")}>Go Ask</button>
    </div>
  ),
}));

jest.mock("./components/InputView", () => ({
  __esModule: true,
  default: ({ onEntrySubmitted }) => (
    <div data-testid="write-view">
      <button onClick={onEntrySubmitted}>Submit entry</button>
      Write view
    </div>
  ),
}));

jest.mock("./components/Dashboard", () => ({
  __esModule: true,
  default: () => <div data-testid="dashboard-view">Dashboard view</div>,
}));

jest.mock("./components/AskView", () => ({
  __esModule: true,
  default: () => <div data-testid="ask-view">Ask view</div>,
}));

import App from "./App";
import { supabase } from "./supabaseClient";
import {
  clearDashboardSnapshotCache,
  prefetchDashboardSnapshot,
} from "./utils/dashboardSnapshot";

beforeEach(() => {
  authStateChangeCallback = undefined;
  window.history.replaceState({}, "", "/");

  supabase.auth.getSession.mockResolvedValue({ data: { session: null } });
  supabase.auth.onAuthStateChange.mockImplementation((callback) => {
    authStateChangeCallback = callback;
    return {
      data: { subscription: { unsubscribe: jest.fn() } },
    };
  });
  supabase.auth.signOut.mockReset();

  clearDashboardSnapshotCache.mockClear();
  prefetchDashboardSnapshot.mockClear();
  prefetchDashboardSnapshot.mockResolvedValue({ entries: [] });
});

test("renders the landing page CTA when no session exists", async () => {
  render(<App />);

  expect(await screen.findByText(/start journaling/i)).toBeInTheDocument();
});

test("authenticated bootstrap with no hash lands on write and starts prefetch", async () => {
  supabase.auth.getSession.mockResolvedValueOnce({
    data: { session: mockAuthenticatedSession },
  });

  render(<App />);

  expect(await screen.findByTestId("write-view")).toBeInTheDocument();
  expect(window.location.hash).toBe("#write");

  await waitFor(() => {
    expect(prefetchDashboardSnapshot).toHaveBeenCalledWith({
      userId: mockAuthenticatedSession.user.id,
    });
  });
});

test("authenticated bootstrap honors a dashboard hash", async () => {
  window.history.replaceState({}, "", "/#dashboard");
  supabase.auth.getSession.mockResolvedValueOnce({
    data: { session: mockAuthenticatedSession },
  });

  render(<App />);

  expect(await screen.findByTestId("dashboard-view")).toBeInTheDocument();
  expect(window.location.hash).toBe("#dashboard");
});

test("brand click navigates back to write", async () => {
  window.history.replaceState({}, "", "/#dashboard");
  supabase.auth.getSession.mockResolvedValueOnce({
    data: { session: mockAuthenticatedSession },
  });

  render(<App />);

  expect(await screen.findByTestId("dashboard-view")).toBeInTheDocument();

  userEvent.click(screen.getByRole("button", { name: /brand/i }));

  expect(await screen.findByTestId("write-view")).toBeInTheDocument();
  expect(window.location.hash).toBe("#write");
});

test("later auth callbacks do not reset the current hash-backed view", async () => {
  supabase.auth.getSession.mockResolvedValueOnce({
    data: { session: mockAuthenticatedSession },
  });

  render(<App />);

  expect(await screen.findByTestId("write-view")).toBeInTheDocument();

  userEvent.click(screen.getByRole("button", { name: /go dashboard/i }));

  expect(await screen.findByTestId("dashboard-view")).toBeInTheDocument();
  expect(window.location.hash).toBe("#dashboard");

  await act(async () => {
    authStateChangeCallback?.("TOKEN_REFRESHED", mockAuthenticatedSession);
  });

  expect(screen.getByTestId("dashboard-view")).toBeInTheDocument();
  expect(window.location.hash).toBe("#dashboard");
});

test("hash changes update the active authenticated view", async () => {
  supabase.auth.getSession.mockResolvedValueOnce({
    data: { session: mockAuthenticatedSession },
  });

  render(<App />);

  expect(await screen.findByTestId("write-view")).toBeInTheDocument();

  await act(async () => {
    window.location.hash = "#ask";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });

  expect(await screen.findByTestId("ask-view")).toBeInTheDocument();

  await act(async () => {
    window.location.hash = "#dashboard";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });

  expect(await screen.findByTestId("dashboard-view")).toBeInTheDocument();
});
