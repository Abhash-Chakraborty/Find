import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/app-shell";

const navigation = vi.hoisted(() => ({
  pathname: "/timeline",
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useRouter: () => ({ push: navigation.push }),
}));

const api = vi.hoisted(() => ({
  getAppConfig: vi.fn(),
}));

// Partial mock: the shell also mounts UniversalSearch, which pulls other
// exports off this module, so only getAppConfig is replaced.
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getAppConfig: api.getAppConfig,
}));

function renderShell(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

beforeEach(() => {
  navigation.pathname = "/timeline";
  navigation.push.mockReset();
  api.getAppConfig.mockReset();
  api.getAppConfig.mockResolvedValue({
    app_version: "9.9.9",
    ml_mode: "mock",
    configured_ml_mode: "mock",
    accel_mode: "cpu",
    ai_enabled: true,
    map_enabled: false,
    build_profile: "mock",
    supported_ml_modes: ["disabled", "mock"],
  });
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  document.documentElement.classList.remove("light", "dark");
  delete document.documentElement.dataset.theme;
  document.documentElement.style.colorScheme = "";
  document.body.style.overflow = "";
});

describe("AppShell", () => {
  it("renders the private route groups and top-bar actions", () => {
    renderShell(
      <AppShell>
        <div>Timeline content</div>
      </AppShell>,
    );

    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByText("Timeline content")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "FIND. Photos" })).toHaveAttribute(
      "href",
      "/timeline",
    );
    expect(screen.getByRole("link", { name: "Photos" })).toHaveAttribute(
      "aria-current",
      "page",
    );

    for (const label of [
      "Search",
      "Map",
      "People",
      "Albums",
      "Favorites",
      "Duplicates",
      "Clusters",
      "Archive",
      "Vault",
      "Trash",
      "Activity",
      "Settings",
    ]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }

    expect(screen.getByRole("link", { name: "Upload" })).toHaveAttribute(
      "href",
      "/upload",
    );
    expect(screen.getByRole("link", { name: "Account" })).toHaveAttribute(
      "href",
      "/account",
    );
    expect(
      screen.getByRole("textbox", { name: "Search everything" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText(/switch to .* mode/i),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Collapse sidebar" }),
    ).toBeInTheDocument();
  });

  it.each([
    "/public/shared/key",
    "/auth/login",
    "/auth/setup",
  ])("does not expose private chrome on %s", (pathname) => {
    navigation.pathname = pathname;
    renderShell(
      <AppShell>
        <div>Shell-free content</div>
      </AppShell>,
    );

    expect(screen.getByText("Shell-free content")).toBeInTheDocument();
    expect(screen.queryByRole("banner")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("navigation", { name: "Main navigation" }),
    ).not.toBeInTheDocument();
  });

  it("opens an accessible mobile drawer and closes it with Escape", () => {
    renderShell(
      <AppShell>
        <div>Content</div>
      </AppShell>,
    );

    const trigger = screen.getByRole("button", {
      name: "Open navigation menu",
    });
    fireEvent.click(trigger);

    const drawer = screen.getByRole("dialog", { name: "Navigation menu" });
    expect(drawer).toHaveAttribute("aria-hidden", "false");
    expect(
      within(drawer).getByRole("link", { name: "Photos" }),
    ).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(drawer).toHaveAttribute("aria-hidden", "true");
  });

  it("locks page scroll, traps focus, and restores the menu trigger", () => {
    renderShell(
      <AppShell>
        <div>Content</div>
      </AppShell>,
    );

    const trigger = screen.getByRole("button", {
      name: "Open navigation menu",
    });
    fireEvent.click(trigger);

    const drawer = screen.getByRole("dialog", { name: "Navigation menu" });
    const focusable = Array.from(
      drawer.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    );
    const first = focusable.at(0);
    const last = focusable.at(-1);

    expect(document.body.style.overflow).toBe("hidden");
    expect(first).toHaveFocus();

    last?.focus();
    fireEvent.keyDown(window, { key: "Tab" });
    expect(first).toHaveFocus();

    first?.focus();
    fireEvent.keyDown(window, { key: "Tab", shiftKey: true });
    expect(last).toHaveFocus();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(document.body.style.overflow).toBe("");
    expect(trigger).toHaveFocus();
  });

  it("opens Search from the global keyboard shortcut", () => {
    renderShell(
      <AppShell>
        <div>Content</div>
      </AppShell>,
    );

    fireEvent.keyDown(window, { key: "/" });
    expect(navigation.push).toHaveBeenCalledWith("/search");
  });

  // #346 asked for the drawer keyboard path to be exercised in both themes.
  // The theme is a class on <html> that swaps CSS custom properties, so the
  // same assertions must hold under either one.
  it.each([
    "light",
    "dark",
  ])("keeps the drawer keyboard contract in %s mode", (theme) => {
    document.documentElement.classList.add(theme);
    document.documentElement.dataset.theme = theme;

    renderShell(
      <AppShell>
        <div>Content</div>
      </AppShell>,
    );

    const trigger = screen.getByRole("button", {
      name: "Open navigation menu",
    });
    fireEvent.click(trigger);

    const drawer = screen.getByRole("dialog", { name: "Navigation menu" });
    expect(drawer).toHaveAttribute("aria-modal", "true");
    expect(drawer).toHaveAttribute("aria-hidden", "false");
    expect(document.body.style.overflow).toBe("hidden");

    const focusable = Array.from(
      drawer.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    );
    expect(focusable.at(0)).toHaveFocus();

    // Background chrome is inert while the drawer owns the viewport.
    expect(screen.getByRole("banner", { hidden: true })).toHaveAttribute(
      "aria-hidden",
      "true",
    );

    fireEvent.keyDown(window, { key: "Escape" });
    expect(drawer).toHaveAttribute("aria-hidden", "true");
    expect(document.body.style.overflow).toBe("");
    expect(trigger).toHaveFocus();
  });

  it("shows the backend-reported version in the sidebar footer", async () => {
    renderShell(
      <AppShell>
        <div>Content</div>
      </AppShell>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("sidebar-app-version")).toHaveTextContent(
        "v9.9.9",
      ),
    );
  });

  it("leaves the sidebar version blank when the config request fails", async () => {
    api.getAppConfig.mockRejectedValue(new Error("offline"));
    renderShell(
      <AppShell>
        <div>Content</div>
      </AppShell>,
    );

    // Wait for the request to actually settle before asserting the absence,
    // otherwise this passes on the pre-fetch render and proves nothing.
    await waitFor(() => expect(api.getAppConfig).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.getByTestId("sidebar-app-version")).toHaveTextContent(""),
    );
    expect(screen.getByTestId("sidebar-app-version").textContent).toBe("");
  });
});
