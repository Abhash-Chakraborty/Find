import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
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

beforeEach(() => {
  navigation.pathname = "/timeline";
  navigation.push.mockReset();
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
    render(
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
    render(
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
    render(
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
    render(
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
    render(
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

    render(
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

  it("keeps the release-managed sidebar version visible", () => {
    render(
      <AppShell>
        <div>Content</div>
      </AppShell>,
    );

    // scripts/bump_version.py rewrites this string on release and CI fails if
    // it drifts, so it is asserted rather than fetched.
    expect(screen.getByText(/^v\d+\.\d+\.\d+$/)).toBeInTheDocument();
  });
});
