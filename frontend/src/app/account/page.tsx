"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, LogOut, Shield, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import {
  changeAccountPassword,
  extractErrorMessage,
  getAccountSessions,
  getCurrentAccount,
  logoutAccount,
  revokeAccountSession,
  updateAccountProfile,
} from "@/lib/api";

export default function AccountPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const account = useQuery({
    queryKey: ["account"],
    queryFn: getCurrentAccount,
    retry: false,
  });
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");

  useEffect(() => {
    if (account.data?.user) {
      setUsername(account.data.user.username);
      setDisplayName(account.data.user.display_name ?? "");
    }
  }, [account.data?.user]);

  const sessions = useQuery({
    queryKey: ["account-sessions"],
    queryFn: getAccountSessions,
    enabled: account.data?.mode === "shared",
  });
  const profile = useMutation({
    mutationFn: updateAccountProfile,
    onSuccess: ({ user }) =>
      queryClient.setQueryData(["account"], {
        mode: "shared",
        user,
      }),
  });
  const password = useMutation({
    mutationFn: changeAccountPassword,
    onSuccess: async () => {
      setCurrentPassword("");
      setNewPassword("");
      await queryClient.invalidateQueries({ queryKey: ["account-sessions"] });
    },
  });
  const revoke = useMutation({
    mutationFn: revokeAccountSession,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["account-sessions"] });
    },
  });
  const logout = useMutation({
    mutationFn: logoutAccount,
    onSuccess: () => {
      queryClient.clear();
      router.replace("/auth/login");
    },
  });

  if (account.isLoading) {
    return (
      <main className="page-surface" aria-busy="true">
        Loading account…
      </main>
    );
  }

  if (account.isError) {
    return (
      <main className="page-surface mx-auto max-w-xl py-16 text-center">
        <h1 className="text-2xl font-semibold">Sign in required</h1>
        <p className="mt-3 text-[color:var(--silver)]">
          This shared instance needs an authenticated account.
        </p>
        <Link
          href="/auth/login"
          className="white-pill mt-6 px-5 py-3 text-sm font-semibold"
        >
          Go to sign in
        </Link>
      </main>
    );
  }

  if (account.data?.mode === "local" || !account.data?.user) {
    return (
      <main className="page-surface mx-auto max-w-3xl py-12">
        <div className="rounded-3xl border border-[var(--frost)] bg-[color:var(--surface-soft)] p-8">
          <Shield className="h-8 w-8 text-[color:var(--green)]" />
          <h1 className="mt-5 text-3xl font-semibold">Private local mode</h1>
          <p className="mt-3 max-w-xl text-sm leading-6 text-[color:var(--silver)]">
            This installation has no accounts. It stays single-user and local
            until you explicitly create an administrator.
          </p>
          <Link
            href="/auth/setup"
            className="white-pill mt-6 px-5 py-3 text-sm font-semibold"
          >
            Enable accounts
          </Link>
        </div>
      </main>
    );
  }

  const user = account.data.user;
  return (
    <main className="page-surface mx-auto max-w-4xl py-10">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--blue)]">
            {user.role}
          </p>
          <h1 className="text-3xl font-semibold">Account settings</h1>
        </div>
        <button
          type="button"
          onClick={() => logout.mutate()}
          className="frost-button px-4 py-2 text-sm font-medium"
        >
          <LogOut className="h-4 w-4" /> Sign out
        </button>
      </header>

      <div className="grid gap-6">
        <section className="rounded-3xl border border-[var(--frost)] bg-[color:var(--surface-soft)] p-6">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <UserRound className="h-5 w-5" /> Profile
          </h2>
          <form
            className="mt-5 grid gap-4 md:grid-cols-2"
            onSubmit={(event: FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              profile.mutate({ username, display_name: displayName });
            }}
          >
            <label className="text-sm font-medium">
              Display name
              <input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                className="mt-2 w-full rounded-xl border border-[var(--frost)] bg-[color:var(--void)] px-4 py-3"
              />
            </label>
            <label className="text-sm font-medium">
              Username
              <input
                required
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                className="mt-2 w-full rounded-xl border border-[var(--frost)] bg-[color:var(--void)] px-4 py-3"
              />
            </label>
            <div className="md:col-span-2 flex items-center gap-3">
              <button
                type="submit"
                className="white-pill px-5 py-2.5 text-sm font-semibold"
              >
                {profile.isPending ? "Saving…" : "Save profile"}
              </button>
              {profile.isSuccess && (
                <span
                  role="status"
                  className="text-sm text-[color:var(--green)]"
                >
                  Saved
                </span>
              )}
              {profile.isError && (
                <span role="alert" className="text-sm text-[color:var(--red)]">
                  {extractErrorMessage(
                    profile.error,
                    "Could not save profile.",
                  )}
                </span>
              )}
            </div>
          </form>
        </section>

        <section className="rounded-3xl border border-[var(--frost)] bg-[color:var(--surface-soft)] p-6">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <KeyRound className="h-5 w-5" /> Password
          </h2>
          <form
            className="mt-5 grid gap-4 md:grid-cols-2"
            onSubmit={(event: FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              password.mutate({
                current_password: currentPassword,
                new_password: newPassword,
              });
            }}
          >
            <label className="text-sm font-medium">
              Current password
              <input
                autoComplete="current-password"
                required
                type="password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                className="mt-2 w-full rounded-xl border border-[var(--frost)] bg-[color:var(--void)] px-4 py-3"
              />
            </label>
            <label className="text-sm font-medium">
              New password
              <input
                autoComplete="new-password"
                minLength={8}
                required
                type="password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                className="mt-2 w-full rounded-xl border border-[var(--frost)] bg-[color:var(--void)] px-4 py-3"
              />
            </label>
            <div className="md:col-span-2 flex flex-wrap items-center gap-3">
              <button
                type="submit"
                className="frost-button px-5 py-2.5 text-sm font-medium"
              >
                {password.isPending ? "Changing…" : "Change password"}
              </button>
              <span className="text-xs text-[color:var(--silver)]">
                Changing it signs out every other session.
              </span>
              {password.isSuccess && (
                <span
                  role="status"
                  className="text-sm text-[color:var(--green)]"
                >
                  Password changed
                </span>
              )}
              {password.isError && (
                <span role="alert" className="text-sm text-[color:var(--red)]">
                  {extractErrorMessage(
                    password.error,
                    "Could not change password.",
                  )}
                </span>
              )}
            </div>
          </form>
        </section>

        <section className="rounded-3xl border border-[var(--frost)] bg-[color:var(--surface-soft)] p-6">
          <h2 className="text-lg font-semibold">Active sessions</h2>
          <div className="mt-4 divide-y divide-[var(--frost)]">
            {sessions.data?.map((session) => (
              <div
                key={session.id}
                className="flex items-center justify-between gap-4 py-4"
              >
                <div>
                  <p className="text-sm font-medium">
                    {session.current ? "This browser" : "Signed-in session"}
                  </p>
                  <p className="mt-1 text-xs text-[color:var(--silver)]">
                    Expires {new Date(session.expires_at).toLocaleString()}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => revoke.mutate(session.id)}
                  className="frost-button px-3 py-2 text-xs font-medium"
                >
                  Revoke
                </button>
              </div>
            ))}
            {sessions.data?.length === 0 && (
              <p className="py-4 text-sm text-[color:var(--silver)]">
                No active sessions.
              </p>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
