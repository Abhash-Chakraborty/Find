import { describe, expect, it, vi } from "vitest";

const redirect = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({ redirect }));

import HomePage from "@/app/page";

describe("root page", () => {
  it("redirects directly to the photo timeline", () => {
    HomePage();
    expect(redirect).toHaveBeenCalledWith("/timeline");
  });
});
