"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import { extractErrorMessage, getAuthStatus, setupAccount } from "@/lib/api";

export default function SetupPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const status = useQuery({
    queryKey: ["auth-status"],
    queryFn: getAuthStatus,
  });

  useEffect(() => {
    if (status.data?.mode === "shared") {
      router.replace("/auth/login");
    }
  }, [router, status.data?.mode]);

  const setup = useMutation({
    mutationFn: setupAccount,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["account"] }),
        queryClient.invalidateQueries({ queryKey: ["auth-status"] }),
      ]);
      router.replace("/timeline");
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (password !== confirmPassword) {
      return;
    }
    setup.mutate({
      username,
      display_name: displayName || undefined,
      password,
    });
  };

  return (
    <main className="grid min-h-dvh place-items-center bg-[color:var(--void)] px-4 py-10">
      <section className="w-full max-w-lg rounded-3xl border border-[var(--frost)] bg-[color:var(--surface-soft)] p-7 shadow-2xl backdrop-blur-xl">
        <div className="mb-6 flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-2xl bg-[color:var(--green-soft)] text-[color:var(--green)]">
            <ShieldCheck aria-hidden="true" className="h-5 w-5" />
          </span>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[color:var(--green)]">
              Private by default
            </p>
            <h1 className="text-2xl font-semibold text-[color:var(--near-white)]">
              Create administrator
            </h1>
          </div>
        </div>
        <p className="mb-6 text-sm leading-6 text-[color:var(--silver)]">
          Accounts enable a shared Find instance. Your images and AI processing
          remain on this server.
        </p>
        <form className="grid gap-4" onSubmit={submit}>
          <label className="text-sm font-medium text-[color:var(--near-white)]">
            Display name
            <input
              autoComplete="name"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              className="mt-2 w-full rounded-xl border border-[var(--frost)] bg-[color:var(--void)] px-4 py-3 outline-none focus:border-[color:var(--blue)]"
            />
          </label>
          <label className="text-sm font-medium text-[color:var(--near-white)]">
            Username
            <input
              autoComplete="username"
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="mt-2 w-full rounded-xl border border-[var(--frost)] bg-[color:var(--void)] px-4 py-3 outline-none focus:border-[color:var(--blue)]"
            />
          </label>
          <label className="text-sm font-medium text-[color:var(--near-white)]">
            Password
            <input
              autoComplete="new-password"
              minLength={8}
              required
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-2 w-full rounded-xl border border-[var(--frost)] bg-[color:var(--void)] px-4 py-3 outline-none focus:border-[color:var(--blue)]"
            />
          </label>
          <label className="text-sm font-medium text-[color:var(--near-white)]">
            Confirm password
            <input
              autoComplete="new-password"
              minLength={8}
              required
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              className="mt-2 w-full rounded-xl border border-[var(--frost)] bg-[color:var(--void)] px-4 py-3 outline-none focus:border-[color:var(--blue)]"
            />
          </label>
          {password !== confirmPassword && confirmPassword.length > 0 && (
            <p role="alert" className="text-sm text-[color:var(--red)]">
              Passwords do not match.
            </p>
          )}
          {setup.isError && (
            <p role="alert" className="text-sm text-[color:var(--red)]">
              {extractErrorMessage(
                setup.error,
                "Unable to create the account.",
              )}
            </p>
          )}
          <button
            type="submit"
            disabled={
              setup.isPending ||
              password !== confirmPassword ||
              password.length < 8
            }
            className="white-pill mt-2 flex w-full justify-center px-5 py-3 text-sm font-semibold disabled:opacity-60"
          >
            {setup.isPending ? "Creating account…" : "Create account"}
          </button>
        </form>
        <Link
          href="/timeline"
          className="mt-5 block text-center text-sm text-[color:var(--silver)] hover:text-[color:var(--near-white)]"
        >
          Keep using local mode
        </Link>
      </section>
    </main>
  );
}
