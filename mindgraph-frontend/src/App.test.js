import { render, screen } from "@testing-library/react";

jest.mock("./supabaseClient", () => ({
  __esModule: true,
  supabase: {
    auth: {
      getSession: () => Promise.resolve({ data: { session: null } }),
      onAuthStateChange: () => ({
        data: { subscription: { unsubscribe: jest.fn() } },
      }),
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

import App from "./App";

test("renders the landing page CTA", async () => {
  render(<App />);
  expect(await screen.findByText(/start journaling/i)).toBeInTheDocument();
  expect(screen.getByText(/one textbox\. zero friction\./i)).toBeInTheDocument();
});
