/**
 * Component tests for the Instance management page (#263).
 *
 * Covers the four states the page can be in -- local mode, signed-out shared
 * mode, member, admin -- plus the admin loading/empty/error branches and the
 * approve/reject actions.
 *
 * Run with: pnpm vitest run src/__tests__/instance-page.test.tsx
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import InstancePage from "@/app/instance/page";

const {
  approveJoinRequest,
  createInstanceInvite,
  getCurrentAccount,
  getInstanceInvites,
  getInstanceUsers,
  getJoinRequests,
  rejectJoinRequest,
  submitJoinRequest,
} = vi.hoisted(() => ({
  approveJoinRequest: vi.fn(),
  createInstanceInvite: vi.fn(),
  getCurrentAccount: vi.fn(),
  getInstanceInvites: vi.fn(),
  getInstanceUsers: vi.fn(),
  getJoinRequests: vi.fn(),
  rejectJoinRequest: vi.fn(),
  submitJoinRequest: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  approveJoinRequest,
  createInstanceInvite,
  getCurrentAccount,
  getInstanceInvites,
  getInstanceUsers,
  getJoinRequests,
  rejectJoinRequest,
  submitJoinRequest,
  extractErrorMessage: (_error: unknown, fallback: string) => fallback,
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <InstancePage />
    </QueryClientProvider>,
  );
}

const ADMIN = {
  mode: "shared" as const,
  user: {
    id: 1,
    username: "admin",
    display_name: "Admin",
    role: "admin" as const,
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  getInstanceUsers.mockResolvedValue([]);
  getInstanceInvites.mockResolvedValue([]);
  getJoinRequests.mockResolvedValue([]);
});

afterEach(cleanup);

describe("local mode", () => {
  it("explains that no instance is needed and never asks for setup", async () => {
    getCurrentAccount.mockResolvedValue({ mode: "local", user: null });
    renderPage();

    expect(await screen.findByText("No instance needed")).toBeInTheDocument();
    // Single-user installs must stay frictionless -- nothing on this page may
    // read as a required step.
    expect(screen.queryByText("Pending requests")).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Enable accounts/ }),
    ).toBeInTheDocument();
  });

  it("states the privacy consequence of enabling shared access", async () => {
    getCurrentAccount.mockResolvedValue({ mode: "local", user: null });
    renderPage();

    expect(
      await screen.findByText(/sharing is per-instance, not per-album/i),
    ).toBeInTheDocument();
  });
});

describe("signed-out shared mode", () => {
  beforeEach(() => {
    getCurrentAccount.mockResolvedValue({ mode: "shared", user: null });
  });

  it("offers the join form with an exposure warning", async () => {
    renderPage();

    expect(await screen.findByLabelText(/Invite token/)).toBeInTheDocument();
    expect(
      screen.getByText(/Only join a server you trust/i),
    ).toBeInTheDocument();
  });

  it("submits a join request and confirms it is awaiting approval", async () => {
    submitJoinRequest.mockResolvedValue({ join_request_id: 7 });
    renderPage();

    fireEvent.change(await screen.findByLabelText(/Invite token/), {
      target: { value: "tok-123" },
    });
    fireEvent.change(screen.getByLabelText(/^Username$/), {
      target: { value: "newbie" },
    });
    fireEvent.change(screen.getByLabelText(/^Password$/), {
      target: { value: "longenough1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Request access/ }));

    // React Query v5 appends its own context argument to every mutationFn
    // call, so assert on the payload rather than the whole argument list.
    await waitFor(() => expect(submitJoinRequest).toHaveBeenCalled());
    expect(submitJoinRequest.mock.calls[0]?.[0]).toEqual({
      invite_token: "tok-123",
      username: "newbie",
      password: "longenough1",
      display_name: undefined,
    });
    expect(await screen.findByText("Request submitted")).toBeInTheDocument();
  });

  it("surfaces a rejected invite token as an alert", async () => {
    submitJoinRequest.mockRejectedValue(new Error("bad token"));
    renderPage();

    fireEvent.change(await screen.findByLabelText(/Invite token/), {
      target: { value: "nope" },
    });
    fireEvent.change(screen.getByLabelText(/^Username$/), {
      target: { value: "newbie" },
    });
    fireEvent.change(screen.getByLabelText(/^Password$/), {
      target: { value: "longenough1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Request access/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not submit the request.",
    );
  });
});

describe("member view", () => {
  it("shows membership without any admin control", async () => {
    getCurrentAccount.mockResolvedValue({
      mode: "shared",
      user: { id: 2, username: "sam", display_name: "Sam", role: "member" },
    });
    renderPage();

    expect(await screen.findByText("You are a member")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Create invite/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Pending requests")).not.toBeInTheDocument();
    // A member must never trigger the admin-only endpoints.
    expect(getJoinRequests).not.toHaveBeenCalled();
    expect(getInstanceUsers).not.toHaveBeenCalled();
  });
});

describe("admin view", () => {
  beforeEach(() => {
    getCurrentAccount.mockResolvedValue(ADMIN);
  });

  it("warns that access covers the whole library", async () => {
    renderPage();
    expect(
      await screen.findByText(/every photo, caption, OCR result/i),
    ).toBeInTheDocument();
  });

  it("shows empty states for invites and requests", async () => {
    renderPage();

    expect(await screen.findByText("No invites yet.")).toBeInTheDocument();
    expect(
      screen.getByText("Nobody is waiting for access."),
    ).toBeInTheDocument();
  });

  it("surfaces a failed member load without breaking the page", async () => {
    getInstanceUsers.mockRejectedValue(new Error("boom"));
    renderPage();

    expect(
      await screen.findByText("Could not load members."),
    ).toBeInTheDocument();
    // The rest of the page still renders.
    expect(screen.getByText("Pending requests")).toBeInTheDocument();
  });

  it("reveals a created invite token once, with a copy-now warning", async () => {
    createInstanceInvite.mockResolvedValue({
      id: 1,
      invite_token: "secret-token",
      expires_at: "2026-09-01T00:00:00+00:00",
    });
    renderPage();

    fireEvent.click(
      await screen.findByRole("button", { name: /Create invite/ }),
    );

    expect(await screen.findByText("secret-token")).toBeInTheDocument();
    expect(
      screen.getByText(/shown once and is not recoverable/i),
    ).toBeInTheDocument();
  });

  it("lists pending requests and approves one", async () => {
    getJoinRequests.mockResolvedValue([
      {
        id: 9,
        username: "newbie",
        display_name: "New Bie",
        status: "pending",
        created_at: "2026-08-20T10:00:00+00:00",
        reviewed_at: null,
      },
    ]);
    approveJoinRequest.mockResolvedValue({ user: { id: 3 } });
    renderPage();

    expect(await screen.findByText("New Bie")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Approve/ }));

    await waitFor(() => expect(approveJoinRequest).toHaveBeenCalled());
    expect(approveJoinRequest.mock.calls[0]?.[0]).toBe(9);
  });

  it("rejects a pending request", async () => {
    getJoinRequests.mockResolvedValue([
      {
        id: 11,
        username: "spammer",
        display_name: null,
        status: "pending",
        created_at: null,
        reviewed_at: null,
      },
    ]);
    rejectJoinRequest.mockResolvedValue(undefined);
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /Reject/ }));

    await waitFor(() => expect(rejectJoinRequest).toHaveBeenCalled());
    expect(rejectJoinRequest.mock.calls[0]?.[0]).toBe(11);
  });

  it("hides already-reviewed requests from the pending list", async () => {
    getJoinRequests.mockResolvedValue([
      {
        id: 12,
        username: "approved-already",
        display_name: null,
        status: "approved",
        created_at: null,
        reviewed_at: "2026-08-19T10:00:00+00:00",
      },
    ]);
    renderPage();

    expect(
      await screen.findByText("Nobody is waiting for access."),
    ).toBeInTheDocument();
    expect(screen.queryByText("approved-already")).not.toBeInTheDocument();
  });

  it("lists members with their role", async () => {
    getInstanceUsers.mockResolvedValue([
      { id: 1, username: "admin", display_name: "Admin", role: "admin" },
      { id: 2, username: "sam", display_name: null, role: "member" },
    ]);
    renderPage();

    const members = await screen.findByRole("list", { name: /Members/ });
    expect(members).toHaveTextContent("Admin");
    // display_name is null, so the username is shown as the primary label too.
    expect(members).toHaveTextContent("sam");
    expect(members).toHaveTextContent("admin");
    expect(members).toHaveTextContent("member");
  });
});
