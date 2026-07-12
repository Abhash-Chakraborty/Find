"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, LockKeyhole } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { extractErrorMessage, getAuthStatus, loginAccount } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const status = useQuery({
    queryKey: ["auth-status"],
    queryFn: getAuthStatus,
  });
  const login = useMutation({
    mutationFn: loginAccount,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["account"] });
      router.replace("/timeline");
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    login.mutate({ username, password });
  };

  return (
    <main className="grid min-h-dvh place-items-center bg-[color:var(--void)] px-4 py-10">
      <section className="w-full max-w-md rounded-3xl border border-[var(--frost)] bg-[color:var(--surface-soft)] p-7 shadow-2xl backdrop-blur-xl">
        <div className="mb-7 flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-2xl bg-[color:var(--blue-soft)] text-[color:var(--blue)]">
            <LockKeyhole aria-hidden="true" className="h-5 w-5" />
          </span>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[color:var(--blue)]">
              Find
            </p>
            <h1 className="text-2xl font-semibold text-[color:var(--near-white)]">
              Sign in
            </h1>
          </div>
        </div>

        {status.data?.mode === "local" ? (
          <div className="space-y-4">
            <p className="text-sm leading-6 text-[color:var(--silver)]">
              This instance is in private local mode, so no sign-in is required.
              You can keep it local or create the first administrator account.
            </p>
            <Link
              href="/timeline"
              className="white-pill flex w-full justify-center px-5 py-3 text-sm font-semibold"
            >
              Continue locally <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/auth/setup"
              className="frost-button flex w-full justify-center px-5 py-3 text-sm font-medium"
            >
              Enable accounts
            </Link>
          </div>
        ) : (
          <form className="space-y-4" onSubmit={submit}>
            <label className="block text-sm font-medium text-[color:var(--near-white)]">
              Username
              <input
                autoComplete="username"
                required
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                className="mt-2 w-full rounded-xl border border-[var(--frost)] bg-[color:var(--void)] px-4 py-3 text-[color:var(--near-white)] outline-none focus:border-[color:var(--blue)]"
              />
            </label>
            <label className="block text-sm font-medium text-[color:var(--near-white)]">
              Password
              <input
                autoComplete="current-password"
                required
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-2 w-full rounded-xl border border-[var(--frost)] bg-[color:var(--void)] px-4 py-3 text-[color:var(--near-white)] outline-none focus:border-[color:var(--blue)]"
              />
            </label>
            {login.isError && (
              <p role="alert" className="text-sm text-[color:var(--red)]">
                {extractErrorMessage(login.error, "Unable to sign in.")}
              </p>
            )}
            <button
              type="submit"
              disabled={login.isPending}
              className="white-pill flex w-full justify-center px-5 py-3 text-sm font-semibold disabled:opacity-60"
            >
              {login.isPending ? "Signing in…" : "Sign in"}
            </button>
          </form>
        )}
      </section>
    </main>
  );
}
