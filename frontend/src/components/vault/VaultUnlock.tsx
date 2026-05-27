"use client";

import axios from "axios";
import { useState } from "react";
import { api } from "@/lib/api";
import { vaultStore } from "@/store/vaultStore";

export function VaultUnlock() {
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const form = event.currentTarget;
    const input = form.elements.namedItem("passphrase");
    if (!(input instanceof HTMLInputElement)) {
      return;
    }

    const passphrase = input.value.trim();
    if (!passphrase) {
      setErrorMessage("Enter a vault passphrase to continue.");
      input.focus();
      return;
    }

    setErrorMessage(null);
    setIsSubmitting(true);

    try {
      const response = await api.post<{ session_token: string }>(
        "/api/vault/unlock",
        {
          passphrase,
        },
      );
      vaultStore.getState().unlock(response.data.session_token);
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 401) {
        setErrorMessage("Incorrect vault passphrase.");
      } else {
        setErrorMessage(
          "Vault could not be unlocked right now. Please try again.",
        );
      }
    } finally {
      input.value = "";
      setIsSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="frost-panel mx-auto flex w-full max-w-md flex-col gap-4 rounded-3xl p-6"
    >
      <label
        htmlFor="vault-passphrase"
        className="text-sm font-medium text-[color:var(--near-white)]"
      >
        Vault passphrase
      </label>
      <p className="text-xs leading-5 text-[color:var(--silver)]">
        First time here? Enter a new passphrase to create your vault. After
        that, use the same passphrase every time you unlock it.
      </p>
      <input
        id="vault-passphrase"
        name="passphrase"
        type="password"
        autoComplete="current-password"
        onChange={() => {
          if (errorMessage) {
            setErrorMessage(null);
          }
        }}
        className="rounded-2xl border border-[var(--frost)] bg-[color:var(--surface-soft)] px-4 py-3 text-sm text-[color:var(--near-white)] outline-none transition focus:border-[color:var(--blue)]"
        placeholder="Enter or create vault passphrase"
      />
      <button
        type="submit"
        disabled={isSubmitting}
        className="inline-flex items-center justify-center rounded-full bg-white px-4 py-3 text-sm font-medium text-black transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-70"
      >
        {isSubmitting ? "Unlocking" : "Unlock Vault"}
      </button>
      {errorMessage && <p className="text-sm text-[#ff9bab]">{errorMessage}</p>}
    </form>
  );
}
