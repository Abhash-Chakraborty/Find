"use client";

import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { KeyRound, LockKeyhole, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { vaultStore } from "@/store/vaultStore";
import {
  getVaultStatus,
  recoverVault,
  setupVault,
  unlockVault,
} from "./vault-client";

export function VaultUnlock() {
  const status = useQuery({
    queryKey: ["vault-status"],
    queryFn: getVaultStatus,
    retry: false,
  });
  const [mode, setMode] = useState<"unlock" | "recover">("unlock");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [recovery, setRecovery] = useState<{
    code: string;
    token: string;
  } | null>(null);
  const initialized = status.data?.initialized ?? true;

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const password = String(data.get("password") ?? "").trim();
    const confirmation = String(data.get("confirmation") ?? "").trim();
    const recoveryCode = String(data.get("recovery") ?? "").trim();
    if (
      !password ||
      (!initialized && password !== confirmation) ||
      (mode === "recover" && !recoveryCode)
    ) {
      setError(
        !initialized && password !== confirmation
          ? "Passwords do not match."
          : "Complete all required fields.",
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (!initialized) {
        const result = await setupVault(password);
        setRecovery({
          code: result.recovery_code,
          token: result.session_token,
        });
        await status.refetch();
      } else if (mode === "recover") {
        const result = await recoverVault(recoveryCode, password);
        setRecovery({
          code: result.recovery_code,
          token: result.session_token,
        });
      } else {
        vaultStore.getState().unlock(await unlockVault(password));
      }
    } catch (caught) {
      const detail = axios.isAxiosError(caught)
        ? caught.response?.data?.detail
        : null;
      setError(
        typeof detail === "string"
          ? detail
          : "Vault could not be opened. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  if (status.isPending)
    return (
      <div className="frost-panel mx-auto h-72 w-full max-w-md animate-pulse rounded-3xl" />
    );

  if (status.isError)
    return (
      <p
        role="alert"
        className="frost-panel mx-auto w-full max-w-md rounded-3xl p-7 text-sm text-[color:var(--status-failed-text)]"
      >
        Could not determine vault status. Please retry.
      </p>
    );

  if (recovery) {
    return (
      <section className="frost-panel mx-auto w-full max-w-lg rounded-3xl p-7 text-center">
        <ShieldCheck className="mx-auto h-9 w-9" />
        <h2 className="mt-4 text-xl font-semibold">Save your recovery code</h2>
        <p className="mt-2 text-sm text-[color:var(--silver)]">
          This code is shown once. Keep it offline; Find stores only a one-way
          hash.
        </p>
        <code className="mt-5 block select-all rounded-xl border border-[var(--frost)] bg-[color:var(--void)] p-4 text-sm tracking-wider">
          {recovery.code}
        </code>
        <button
          type="button"
          onClick={() => vaultStore.getState().unlock(recovery.token)}
          className="mt-5 rounded-full bg-[color:var(--near-white)] px-5 py-2.5 text-sm font-semibold text-[color:var(--void)]"
        >
          I saved the code
        </button>
      </section>
    );
  }

  return (
    <form
      onSubmit={submit}
      className="frost-panel mx-auto flex w-full max-w-md flex-col gap-4 rounded-3xl p-7"
    >
      <span className="grid h-11 w-11 place-items-center rounded-xl bg-[color:var(--surface-hover)]">
        <LockKeyhole className="h-5 w-5" />
      </span>
      <div>
        <h2 className="text-xl font-semibold">
          {!initialized
            ? "Create your private vault"
            : mode === "recover"
              ? "Recover your vault"
              : "Unlock vault"}
        </h2>
        <p className="mt-2 text-sm leading-6 text-[color:var(--silver)]">
          {!initialized
            ? "Set a password to keep hidden photos behind a separate local lock. Image bytes remain in your private storage and are not encrypted."
            : mode === "recover"
              ? "Enter the recovery code you saved and choose a new password."
              : "Enter your vault password. It is never stored or sent outside this Find instance."}
        </p>
      </div>
      {mode === "recover" && (
        <input
          name="recovery"
          autoComplete="off"
          placeholder="Recovery code"
          className="rounded-xl border border-[var(--frost)] bg-[color:var(--surface-soft)] px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-[color:var(--blue)]"
        />
      )}
      <input
        name="password"
        type="password"
        autoComplete={
          initialized && mode === "unlock" ? "current-password" : "new-password"
        }
        placeholder={
          !initialized || mode === "recover"
            ? "New password (8+ characters)"
            : "Vault password"
        }
        className="rounded-xl border border-[var(--frost)] bg-[color:var(--surface-soft)] px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-[color:var(--blue)]"
      />
      {!initialized && (
        <input
          name="confirmation"
          type="password"
          autoComplete="new-password"
          placeholder="Confirm password"
          className="rounded-xl border border-[var(--frost)] bg-[color:var(--surface-soft)] px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-[color:var(--blue)]"
        />
      )}
      <button
        type="submit"
        disabled={busy}
        className="inline-flex items-center justify-center gap-2 rounded-full bg-[color:var(--near-white)] px-4 py-3 text-sm font-semibold text-[color:var(--void)] disabled:opacity-60"
      >
        <KeyRound className="h-4 w-4" />
        {busy
          ? "Please wait…"
          : !initialized
            ? "Create vault"
            : mode === "recover"
              ? "Reset password"
              : "Unlock vault"}
      </button>
      {initialized &&
        (mode === "recover" || status.data?.recovery_available) && (
          <button
            type="button"
            onClick={() => {
              setMode(mode === "recover" ? "unlock" : "recover");
              setError(null);
            }}
            className="text-sm text-[color:var(--silver)] underline-offset-4 hover:underline"
          >
            {mode === "recover"
              ? "Back to unlock"
              : "Forgot your vault password?"}
          </button>
        )}
      {error && (
        <p
          role="alert"
          className="text-sm text-[color:var(--status-failed-text)]"
        >
          {error}
        </p>
      )}
    </form>
  );
}
