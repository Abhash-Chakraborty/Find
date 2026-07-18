import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AccountPage from "@/app/account/page";
import LoginPage from "@/app/auth/login/page";
import SetupPage from "@/app/auth/setup/page";

const api = vi.hoisted(() => ({
  getAuthStatus: vi.fn(),
  loginAccount: vi.fn(),
  setupAccount: vi.fn(),
  getCurrentAccount: vi.fn(),
  getAccountSessions: vi.fn(),
  updateAccountProfile: vi.fn(),
  changeAccountPassword: vi.fn(),
  revokeAccountSession: vi.fn(),
  logoutAccount: vi.fn(),
  extractErrorMessage: vi.fn((_error: unknown, fallback: string) => fallback),
}));

const router = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn() }));

vi.mock("@/lib/api", () => api);
vi.mock("next/navigation", () => ({ useRouter: () => router }));

function renderPage(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

beforeEach(() => {
  for (const fn of Object.values(api)) {
    fn.mockReset();
  }
  api.extractErrorMessage.mockImplementation(
    (_error: unknown, fallback: string) => fallback,
  );
  router.replace.mockReset();
  router.push.mockReset();
});

afterEach(cleanup);

describe("account bootstrap", () => {
  it("lets a local instance continue without an account", async () => {
    api.getAuthStatus.mockResolvedValue({
      mode: "local",
      setup_available: true,
    });
    renderPage(<LoginPage />);

    expect(
      await screen.findByRole("link", { name: /continue locally/i }),
    ).toHaveAttribute("href", "/timeline");
    expect(
      screen.getByRole("link", { name: /enable accounts/i }),
    ).toHaveAttribute("href", "/auth/setup");
  });

  it("signs a shared-mode user in with a cookie-backed session", async () => {
    api.getAuthStatus.mockResolvedValue({
      mode: "shared",
      setup_available: false,
    });
    api.loginAccount.mockResolvedValue({
      user: {
        id: 1,
        username: "owner",
        display_name: "Owner",
        role: "admin",
      },
    });
    renderPage(<LoginPage />);

    fireEvent.change(await screen.findByLabelText("Username"), {
      target: { value: "owner" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() =>
      expect(api.loginAccount).toHaveBeenCalledWith(
        {
          username: "owner",
          password: "password123",
        },
        expect.anything(),
      ),
    );
    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith("/timeline"),
    );
  });

  it("does not submit setup while password confirmation differs", async () => {
    api.getAuthStatus.mockResolvedValue({
      mode: "local",
      setup_available: true,
    });
    renderPage(<SetupPage />);

    fireEvent.change(await screen.findByLabelText("Password"), {
      target: { value: "password123" },
    });
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "password456" },
    });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Passwords do not match",
    );
    expect(
      screen.getByRole("button", { name: "Create account" }),
    ).toBeDisabled();
    expect(api.setupAccount).not.toHaveBeenCalled();
  });
});

describe("account settings", () => {
  it("explains local mode without inventing a user", async () => {
    api.getCurrentAccount.mockResolvedValue({ mode: "local", user: null });
    renderPage(<AccountPage />);

    expect(
      await screen.findByRole("heading", { name: "Private local mode" }),
    ).toBeInTheDocument();
  });

  it("renders profile and server-side sessions for a shared account", async () => {
    api.getCurrentAccount.mockResolvedValue({
      mode: "shared",
      user: {
        id: 1,
        username: "owner",
        display_name: "Find Owner",
        role: "admin",
      },
    });
    api.getAccountSessions.mockResolvedValue([
      {
        id: 9,
        created_at: "2026-07-12T00:00:00Z",
        expires_at: "2026-07-13T00:00:00Z",
        current: true,
      },
    ]);
    renderPage(<AccountPage />);

    expect(
      await screen.findByRole("heading", { name: "Account settings" }),
    ).toBeInTheDocument();
    expect(screen.getByDisplayValue("Find Owner")).toBeInTheDocument();
    expect(await screen.findByText("This browser")).toBeInTheDocument();
  });
});
