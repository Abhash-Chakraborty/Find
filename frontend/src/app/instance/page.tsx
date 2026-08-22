"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Copy,
  ShieldAlert,
  ShieldCheck,
  UserPlus,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { type FormEvent, useState } from "react";
import {
  approveJoinRequest,
  type CreatedInvite,
  createInstanceInvite,
  extractErrorMessage,
  getCurrentAccount,
  getInstanceInvites,
  getInstanceUsers,
  getJoinRequests,
  rejectJoinRequest,
  submitJoinRequest,
} from "@/lib/api";

const INPUT_CLASS =
  "mt-2 w-full rounded-xl border border-[var(--frost)] bg-[color:var(--void)] px-4 py-3 outline-none focus:border-[color:var(--blue)]";

function formatDate(value: string | null): string {
  if (!value) return "unknown";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "unknown" : parsed.toLocaleString();
}

export default function InstancePage() {
  const account = useQuery({
    queryKey: ["account"],
    queryFn: getCurrentAccount,
    retry: false,
  });

  if (account.isLoading) {
    return (
      <main className="page-surface mx-auto max-w-4xl py-10" aria-busy="true">
        Loading instance…
      </main>
    );
  }

  if (account.isError) {
    return (
      <main className="page-surface mx-auto max-w-4xl py-10">
        <h1 className="text-3xl font-semibold">Instance</h1>
        <p className="mt-4 text-sm text-[color:var(--silver)]">
          {extractErrorMessage(account.error, "Could not load this instance.")}
        </p>
      </main>
    );
  }

  // Local mode is the default and must stay frictionless: a single-user
  // install never needs an instance, so this page explains rather than
  // prompts.
  if (account.data?.mode === "local") {
    return <LocalModeNotice />;
  }

  const user = account.data?.user ?? null;

  if (!user) {
    // Shared mode, not signed in. The join flow is the one thing a stranger
    // with an invite legitimately needs from this page.
    return <JoinWithInvite />;
  }

  if (user.role !== "admin") {
    return <MemberView displayName={user.display_name ?? user.username} />;
  }

  return <AdminView />;
}

function PageHeader({ subtitle }: { subtitle: string }) {
  return (
    <header className="mb-8 border-b border-[var(--frost)] pb-5">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--blue)]">
        Instance
      </p>
      <h1 className="mt-1 text-3xl font-semibold">Shared access</h1>
      <p className="mt-2 text-sm leading-6 text-[color:var(--silver)]">
        {subtitle}
      </p>
    </header>
  );
}

function LocalModeNotice() {
  return (
    <main className="page-surface mx-auto max-w-4xl py-10">
      <PageHeader subtitle="This installation is running as a single-user library." />
      <section className="rounded-3xl border border-[var(--frost)] bg-[color:var(--surface-soft)] p-7 sm:p-9">
        <ShieldCheck className="h-7 w-7 text-[color:var(--green)]" />
        <h2 className="mt-5 text-2xl font-semibold">No instance needed</h2>
        <p className="mt-3 max-w-xl text-sm leading-6 text-[color:var(--silver)]">
          Find is local-first. Nothing here is required to use your library, and
          no account, invite, or sign-in exists until you deliberately enable
          shared access.
        </p>
        <p className="mt-3 max-w-xl text-sm leading-6 text-[color:var(--silver)]">
          Enabling accounts turns this server into a shared deployment. Anyone
          you invite can see every photo, caption, face cluster, and search
          result in this library — sharing is per-instance, not per-album.
        </p>
        <Link
          href="/auth/setup"
          className="white-pill mt-6 inline-flex px-5 py-3 text-sm font-semibold"
        >
          Enable accounts
        </Link>
      </section>
    </main>
  );
}

function MemberView({ displayName }: { displayName: string }) {
  return (
    <main className="page-surface mx-auto max-w-4xl py-10">
      <PageHeader subtitle={`Signed in as ${displayName}.`} />
      <section className="rounded-3xl border border-[var(--frost)] bg-[color:var(--surface-soft)] p-7 sm:p-9">
        <Users className="h-7 w-7 text-[color:var(--blue)]" />
        <h2 className="mt-5 text-2xl font-semibold">You are a member</h2>
        <p className="mt-3 max-w-xl text-sm leading-6 text-[color:var(--silver)]">
          You have access to this shared library. Inviting people and reviewing
          join requests are administrator actions.
        </p>
        <p className="mt-3 max-w-xl text-sm leading-6 text-[color:var(--silver)]">
          Everything you upload is visible to everyone else on this instance.
        </p>
        <Link
          href="/account"
          className="frost-button mt-6 inline-flex px-4 py-2 text-sm font-medium"
        >
          Account settings
        </Link>
      </section>
    </main>
  );
}

function JoinWithInvite() {
  const [inviteToken, setInviteToken] = useState("");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");

  const join = useMutation({ mutationFn: submitJoinRequest });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    join.mutate({
      invite_token: inviteToken.trim(),
      username: username.trim(),
      password,
      display_name: displayName.trim() || undefined,
    });
  };

  if (join.isSuccess) {
    return (
      <main className="page-surface mx-auto max-w-2xl py-10">
        <PageHeader subtitle="Your request has been sent." />
        <section className="rounded-3xl border border-[var(--frost)] bg-[color:var(--surface-soft)] p-7 sm:p-9">
          <Check className="h-7 w-7 text-[color:var(--green)]" />
          <h2 className="mt-5 text-2xl font-semibold">Request submitted</h2>
          <p className="mt-3 text-sm leading-6 text-[color:var(--silver)]">
            An administrator has to approve it before you can sign in. Nothing
            is shared with you until they do.
          </p>
          <Link
            href="/auth/login"
            className="frost-button mt-6 inline-flex px-4 py-2 text-sm font-medium"
          >
            Go to sign in
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="page-surface mx-auto max-w-2xl py-10">
      <PageHeader subtitle="Join this shared library with an invite from its administrator." />

      <section className="mb-6 rounded-2xl border border-[var(--frost)] bg-[color:var(--frost-soft)] p-4">
        <div className="flex items-start gap-3">
          <ShieldAlert
            className="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--yellow)]"
            aria-hidden
          />
          <p className="text-xs leading-relaxed text-[color:var(--silver)]">
            Joining gives you access to this instance&rsquo;s entire library,
            and gives its administrator the ability to see that you have an
            account here. Only join a server you trust.
          </p>
        </div>
      </section>

      <form onSubmit={onSubmit} className="space-y-4">
        <label className="block text-sm">
          <span className="font-medium">Invite token</span>
          <input
            required
            value={inviteToken}
            onChange={(event) => setInviteToken(event.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="block text-sm">
          <span className="font-medium">Username</span>
          <input
            autoComplete="username"
            required
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="block text-sm">
          <span className="font-medium">Display name (optional)</span>
          <input
            autoComplete="name"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            className={INPUT_CLASS}
          />
        </label>
        <label className="block text-sm">
          <span className="font-medium">Password</span>
          <input
            autoComplete="new-password"
            minLength={8}
            required
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className={INPUT_CLASS}
          />
        </label>

        {join.isError && (
          <p role="alert" className="text-sm text-[color:var(--red)]">
            {extractErrorMessage(join.error, "Could not submit the request.")}
          </p>
        )}

        <button
          type="submit"
          disabled={join.isPending}
          className="white-pill px-5 py-3 text-sm font-semibold disabled:opacity-60"
        >
          {join.isPending ? "Sending…" : "Request access"}
        </button>
      </form>
    </main>
  );
}

function AdminView() {
  const queryClient = useQueryClient();
  const [createdInvite, setCreatedInvite] = useState<CreatedInvite | null>(
    null,
  );
  const [copied, setCopied] = useState(false);

  const users = useQuery({
    queryKey: ["instance-users"],
    queryFn: getInstanceUsers,
  });
  const requests = useQuery({
    queryKey: ["instance-join-requests"],
    queryFn: getJoinRequests,
  });
  const invites = useQuery({
    queryKey: ["instance-invites"],
    queryFn: getInstanceInvites,
  });

  const invalidateReviewQueries = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["instance-join-requests"] }),
      queryClient.invalidateQueries({ queryKey: ["instance-users"] }),
    ]);
  };

  const invite = useMutation({
    mutationFn: () => createInstanceInvite(),
    onSuccess: async (data) => {
      setCreatedInvite(data);
      setCopied(false);
      await queryClient.invalidateQueries({ queryKey: ["instance-invites"] });
    },
  });
  const approve = useMutation({
    mutationFn: approveJoinRequest,
    onSuccess: invalidateReviewQueries,
  });
  const reject = useMutation({
    mutationFn: rejectJoinRequest,
    onSuccess: invalidateReviewQueries,
  });

  const pending = (requests.data ?? []).filter(
    (request) => request.status === "pending",
  );
  const reviewError = approve.error ?? reject.error;

  return (
    <main className="page-surface mx-auto max-w-4xl py-10">
      <PageHeader subtitle="Invite people to this library and review who is asking for access." />

      <section className="mb-6 rounded-2xl border border-[var(--frost)] bg-[color:var(--frost-soft)] p-4">
        <div className="flex items-start gap-3">
          <ShieldAlert
            className="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--yellow)]"
            aria-hidden
          />
          <p className="text-xs leading-relaxed text-[color:var(--silver)]">
            Everyone you approve can see this instance&rsquo;s whole library —
            every photo, caption, OCR result, face cluster, and search. Access
            is per-instance, not per-album, and cannot be scoped to a subset.
          </p>
        </div>
      </section>

      {/* --- Invites --- */}
      <section
        aria-labelledby="invites-heading"
        className="mb-8 rounded-3xl border border-[var(--frost)] bg-[color:var(--surface-soft)] p-6 sm:p-7"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="invites-heading" className="text-lg font-semibold">
            Invites
          </h2>
          <button
            type="button"
            onClick={() => invite.mutate()}
            disabled={invite.isPending}
            className="white-pill inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold disabled:opacity-60"
          >
            <UserPlus className="h-4 w-4" aria-hidden />
            {invite.isPending ? "Creating…" : "Create invite"}
          </button>
        </div>

        {invite.isError && (
          <p role="alert" className="mt-3 text-sm text-[color:var(--red)]">
            {extractErrorMessage(invite.error, "Could not create an invite.")}
          </p>
        )}

        {createdInvite && (
          <div className="mt-4 rounded-xl border border-[var(--green-soft)] bg-[color:var(--green-soft)] p-4">
            <p className="text-xs font-semibold uppercase tracking-wide">
              Copy this now
            </p>
            <p className="mt-1 text-xs leading-relaxed text-[color:var(--silver)]">
              The token is shown once and is not recoverable afterwards. Send it
              over a channel you trust — anyone holding it can request access.
            </p>
            <div className="mt-3 flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded-lg border border-[var(--frost)] bg-[color:var(--void)] px-3 py-2 text-xs">
                {createdInvite.invite_token}
              </code>
              <button
                type="button"
                onClick={() => {
                  void navigator.clipboard
                    ?.writeText(createdInvite.invite_token)
                    .then(() => setCopied(true))
                    .catch(() => setCopied(false));
                }}
                className="icon-button shrink-0"
                aria-label="Copy invite token"
              >
                {copied ? (
                  <Check className="h-4 w-4" aria-hidden />
                ) : (
                  <Copy className="h-4 w-4" aria-hidden />
                )}
              </button>
            </div>
            <p className="mt-2 text-xs text-[color:var(--muted)]">
              Expires {formatDate(createdInvite.expires_at)}
            </p>
          </div>
        )}

        {invites.isLoading && (
          <p
            className="mt-4 text-sm text-[color:var(--muted)]"
            aria-busy="true"
          >
            Loading invites…
          </p>
        )}
        {invites.isError && (
          <p role="alert" className="mt-4 text-sm text-[color:var(--red)]">
            {extractErrorMessage(invites.error, "Could not load invites.")}
          </p>
        )}
        {invites.isSuccess && invites.data.length === 0 && (
          <p className="mt-4 text-sm text-[color:var(--muted)]">
            No invites yet.
          </p>
        )}
        {invites.isSuccess && invites.data.length > 0 && (
          <ul className="mt-4 space-y-2">
            {invites.data.map((item) => (
              <li
                key={item.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--frost)] px-4 py-3 text-sm"
              >
                <span>Created {formatDate(item.created_at)}</span>
                <span
                  className={`accent-badge ${item.is_used ? "status-indexed" : "status-pending"}`}
                >
                  {item.is_used ? "used" : "unused"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* --- Pending join requests --- */}
      <section
        aria-labelledby="requests-heading"
        className="mb-8 rounded-3xl border border-[var(--frost)] bg-[color:var(--surface-soft)] p-6 sm:p-7"
      >
        <h2 id="requests-heading" className="text-lg font-semibold">
          Pending requests
        </h2>

        {reviewError && (
          <p role="alert" className="mt-3 text-sm text-[color:var(--red)]">
            {extractErrorMessage(reviewError, "Could not update the request.")}
          </p>
        )}

        {requests.isLoading && (
          <p
            className="mt-4 text-sm text-[color:var(--muted)]"
            aria-busy="true"
          >
            Loading requests…
          </p>
        )}
        {requests.isError && (
          <p role="alert" className="mt-4 text-sm text-[color:var(--red)]">
            {extractErrorMessage(
              requests.error,
              "Could not load join requests.",
            )}
          </p>
        )}
        {requests.isSuccess && pending.length === 0 && (
          <p className="mt-4 text-sm text-[color:var(--muted)]">
            Nobody is waiting for access.
          </p>
        )}
        {pending.length > 0 && (
          <ul className="mt-4 space-y-2">
            {pending.map((request) => (
              <li
                key={request.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--frost)] px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {request.display_name ?? request.username}
                  </p>
                  <p className="text-xs text-[color:var(--muted)]">
                    {request.username} · requested{" "}
                    {formatDate(request.created_at)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    type="button"
                    onClick={() => approve.mutate(request.id)}
                    disabled={approve.isPending || reject.isPending}
                    className="frost-button inline-flex items-center gap-1.5 px-3 py-2 text-sm disabled:opacity-60"
                  >
                    <Check className="h-4 w-4" aria-hidden />
                    Approve
                  </button>
                  <button
                    type="button"
                    onClick={() => reject.mutate(request.id)}
                    disabled={approve.isPending || reject.isPending}
                    className="frost-button inline-flex items-center gap-1.5 px-3 py-2 text-sm disabled:opacity-60"
                  >
                    <X className="h-4 w-4" aria-hidden />
                    Reject
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* --- Members --- */}
      <section
        aria-labelledby="members-heading"
        className="rounded-3xl border border-[var(--frost)] bg-[color:var(--surface-soft)] p-6 sm:p-7"
      >
        <h2 id="members-heading" className="text-lg font-semibold">
          Members
        </h2>

        {users.isLoading && (
          <p
            className="mt-4 text-sm text-[color:var(--muted)]"
            aria-busy="true"
          >
            Loading members…
          </p>
        )}
        {users.isError && (
          <p role="alert" className="mt-4 text-sm text-[color:var(--red)]">
            {extractErrorMessage(users.error, "Could not load members.")}
          </p>
        )}
        {users.isSuccess && (
          <ul aria-labelledby="members-heading" className="mt-4 space-y-2">
            {users.data.map((member) => (
              <li
                key={member.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--frost)] px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {member.display_name ?? member.username}
                  </p>
                  <p className="text-xs text-[color:var(--muted)]">
                    {member.username}
                  </p>
                </div>
                <span
                  className={`accent-badge ${member.role === "admin" ? "status-processing" : "status-default"}`}
                >
                  {member.role}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
