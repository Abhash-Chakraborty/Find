import { beforeEach, describe, expect, it } from "vitest";
import { vaultStore } from "@/store/vaultStore";

describe("vaultStore", () => {
  beforeEach(() => {
    vaultStore.getState().lock();
    localStorage.clear();
    sessionStorage.clear();
  });

  it("keeps the vault session token in memory only", () => {
    vaultStore.getState().unlock("memory-only-token");

    expect(vaultStore.getState()).toMatchObject({
      isUnlocked: true,
      sessionToken: "memory-only-token",
    });
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    expect(document.cookie).not.toContain("memory-only-token");
  });

  it("drops the session token when locked", () => {
    vaultStore.getState().unlock("temporary-token");
    vaultStore.getState().lock();

    expect(vaultStore.getState()).toMatchObject({
      isUnlocked: false,
      sessionToken: null,
    });
  });
});
