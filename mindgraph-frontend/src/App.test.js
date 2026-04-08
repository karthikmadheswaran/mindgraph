import { render, screen } from "@testing-library/react";

jest.mock("./supabaseClient", () => ({
  __esModule: true,
  supabase: {
    auth: {
      getSession: jest.fn(() => Promise.resolve({ data: { session: null } })),
      onAuthStateChange: jest.fn(() => ({
        data: { subscription: { unsubscribe: jest.fn() } },
      })),
      signOut: jest.fn(),
      signUp: jest.fn(),
      signInWithPassword: jest.fn(),
    },
  },
}));

jest.mock("react-markdown", () => ({
  __esModule: true,
  default: ({ children }) => children,
}));

jest.mock("./components/Sidebar", () => ({
  __esModule: true,
  default: () => <div data-testid="sidebar" />,
}));

import App from "./App";
import { supabase } from "./supabaseClient";

beforeEach(() => {
  supabase.auth.getSession.mockResolvedValue({ data: { session: null } });
  supabase.auth.onAuthStateChange.mockReturnValue({
    data: { subscription: { unsubscribe: jest.fn() } },
  });
  supabase.auth.signOut.mockReset();
});

test("renders the landing page CTA", async () => {
  render(<App />);
  expect(await screen.findByText(/start journaling/i)).toBeInTheDocument();
  expect(screen.getByText(/one textbox\. zero friction\./i)).toBeInTheDocument();
});

test("opens on the write view for an authenticated session", async () => {
  supabase.auth.getSession.mockResolvedValueOnce({
    data: {
      session: {
        user: { email: "hello@mindgraph.ai" },
      },
    },
  });

  render(<App />);

  expect(await screen.findByPlaceholderText(/what's on your mind\?/i)).toBeInTheDocument();
  expect(screen.queryByText(/loading your journal/i)).not.toBeInTheDocument();
});
