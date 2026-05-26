import { create } from "zustand";

interface VaultState {
  isUnlocked: boolean;
  // WARNING: Never persist this value. Memory only. Do not add to localStorage/sessionStorage/cookies.
  sessionToken: string | null;
  unlock: (token: string) => void;
  lock: () => void;
}

export const vaultStore = create<VaultState>((set) => ({
  isUnlocked: false,
  sessionToken: null,
  unlock: (token) => {
    set({
      isUnlocked: true,
      sessionToken: token,
    });
  },
  lock: () => {
    set({
      isUnlocked: false,
      sessionToken: null,
    });
  },
}));
