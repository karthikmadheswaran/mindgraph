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
  loadDashboardSnapshot: jest.fn(() =>
    Promise.resolve({ entries: [], progress: { deadlines: [], projects: [] } })
  ),
  prefetchDashboardSnapshot: jest.fn(() =>
    Promise.resolve({ entries: [], progress: { deadlines: [], projects: [] } })
  ),
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
  default: ({ onAuth, onBack }) => (
    <div>
      <button onClick={() => onAuth(mockAuthenticatedSession)}>Complete auth</button>
      <button onClick={onBack}>Back from auth</button>
    </div>
  ),
}));

jest.mock("./components/Sidebar", () => ({
  __esModule: true,
  default: ({ onBrandClick, onLogout, onViewChange }) => (
    <div data-testid="sidebar">
      <button onClick={onBrandClick}>Brand</button>
      <button onClick={() => onViewChange("dashboard")}>Go Dashboard</button>
      <button onClick={() => onViewChange("graph")}>Go Graph</button>
      <button onClick={() => onViewChange("ask")}>Go Ask</button>
      <button onClick={onLogout}>Log out</button>
    </div>
  ),
}));

jest.mock("./components/Dashboard", () => ({
  __esModule: true,
  default: () => <div data-testid="dashboard-view">Dashboard view</div>,
}));

jest.mock("./components/MyProgress", () => ({
  __esModule: true,
  default: () => <div data-testid="progress-view">Progress view</div>,
}));

jest.mock("./components/AskView", () => ({
  __esModule: true,
  default: () => <div data-testid="ask-view">Ask view</div>,
}));

jest.mock("./components/KnowledgeGraphView", () => ({
  __esModule: true,
  default: () => <div data-testid="graph-view">Graph view</div>,
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
  prefetchDashboardSnapshot.mockResolvedValue({
    entries: [],
    progress: { deadlines: [], projects: [] },
  });
});

test("renders the landing page CTA when no session exists", async () => {
  render(<App />);

  expect(await screen.findByText(/start journaling/i)).toBeInTheDocument();
});

test("auth intent query renders the auth screen when no session exists", async () => {
  window.history.replaceState({}, "", "/?view=auth");

  render(<App />);

  expect(
    await screen.findByRole("button", { name: /complete auth/i })
  ).toBeInTheDocument();
});

test("auth intent survives a stale passive session invalidation", async () => {
  window.history.replaceState({}, "", "/?view=auth");
  supabase.auth.getSession.mockResolvedValueOnce({
    data: { session: mockAuthenticatedSession },
  });

  render(<App />);

  expect(await screen.findByTestId("ask-view")).toBeInTheDocument();

  await act(async () => {
    authStateChangeCallback?.("SIGNED_OUT", null);
  });

  expect(
    await screen.findByRole("button", { name: /complete auth/i })
  ).toBeInTheDocument();
  expect(window.location.search).toBe("?view=auth");
  expect(window.location.hash).toBe("");
});

test("auth intent with a valid existing session enters the app", async () => {
  window.history.replaceState({}, "", "/?view=auth");
  supabase.auth.getSession.mockResolvedValueOnce({
    data: { session: mockAuthenticatedSession },
  });

  render(<App />);

  expect(await screen.findByTestId("ask-view")).toBeInTheDocument();
});

test("manual logout clears auth intent and returns to landing", async () => {
  window.history.replaceState({}, "", "/?view=auth");
  supabase.auth.getSession.mockResolvedValueOnce({
    data: { session: mockAuthenticatedSession },
  });

  render(<App />);

  expect(await screen.findByTestId("ask-view")).toBeInTheDocument();

  userEvent.click(screen.getByRole("button", { name: /log out/i }));

  await waitFor(() => {
    expect(supabase.auth.signOut).toHaveBeenCalled();
  });

  await act(async () => {
    authStateChangeCallback?.("SIGNED_OUT", null);
  });

  expect(await screen.findByText(/start journaling/i)).toBeInTheDocument();
  expect(window.location.search).toBe("");
  expect(window.location.hash).toBe("");
});

test("backing out of auth clears the auth intent query", async () => {
  window.history.replaceState({}, "", "/?view=auth");

  render(<App />);

  expect(
    await screen.findByRole("button", { name: /complete auth/i })
  ).toBeInTheDocument();

  userEvent.click(screen.getByRole("button", { name: /back from auth/i }));

  expect(await screen.findByText(/start journaling/i)).toBeInTheDocument();
  expect(window.location.search).toBe("");
});

test("completing auth clears the auth intent query", async () => {
  window.history.replaceState({}, "", "/?view=auth");

  render(<App />);

  userEvent.click(await screen.findByRole("button", { name: /complete auth/i }));

  expect(await screen.findByTestId("ask-view")).toBeInTheDocument();
  expect(window.location.search).toBe("");
  expect(window.location.hash).toBe("#ask");
});

test("authenticated bootstrap with no hash lands on ask and starts prefetch", async () => {
  supabase.auth.getSession.mockResolvedValueOnce({
    data: { session: mockAuthenticatedSession },
  });

  render(<App />);

  expect(await screen.findByTestId("ask-view")).toBeInTheDocument();
  expect(window.location.hash).toBe("#ask");

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

test("brand click navigates back to ask", async () => {
  window.history.replaceState({}, "", "/#dashboard");
  supabase.auth.getSession.mockResolvedValueOnce({
    data: { session: mockAuthenticatedSession },
  });

  render(<App />);

  expect(await screen.findByTestId("dashboard-view")).toBeInTheDocument();

  userEvent.click(screen.getByRole("button", { name: /brand/i }));

  expect(await screen.findByTestId("ask-view")).toBeInTheDocument();
  expect(window.location.hash).toBe("#ask");
});

test("later auth callbacks do not reset the current hash-backed view", async () => {
  supabase.auth.getSession.mockResolvedValueOnce({
    data: { session: mockAuthenticatedSession },
  });

  render(<App />);

  expect(await screen.findByTestId("ask-view")).toBeInTheDocument();

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

  expect(await screen.findByTestId("ask-view")).toBeInTheDocument();

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

test("slash-prefixed progress hash resolves to the progress view", async () => {
  window.history.replaceState({}, "", "/#/progress");
  supabase.auth.getSession.mockResolvedValueOnce({
    data: { session: mockAuthenticatedSession },
  });

  render(<App />);

  expect(await screen.findByTestId("progress-view")).toBeInTheDocument();
  expect(window.location.hash).toBe("#/progress");
});

test("legacy write hash resolves back to ask", async () => {
  window.history.replaceState({}, "", "/#write");
  supabase.auth.getSession.mockResolvedValueOnce({
    data: { session: mockAuthenticatedSession },
  });

  render(<App />);

  expect(await screen.findByTestId("ask-view")).toBeInTheDocument();
  expect(window.location.hash).toBe("#ask");
});

test("sidebar navigation can move into the graph view", async () => {
  supabase.auth.getSession.mockResolvedValueOnce({
    data: { session: mockAuthenticatedSession },
  });

  render(<App />);

  expect(await screen.findByTestId("ask-view")).toBeInTheDocument();

  userEvent.click(screen.getByRole("button", { name: /go graph/i }));

  expect(await screen.findByTestId("graph-view")).toBeInTheDocument();
  expect(window.location.hash).toBe("#graph");
});
