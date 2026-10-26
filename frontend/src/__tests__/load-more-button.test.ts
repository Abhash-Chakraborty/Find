import { describe, expect, it } from "vitest";
import { nextSkip } from "@/components/load-more-button";

describe("nextSkip", () => {
  const rows = (page: number[]) => page.length;

  it("skips past every row loaded so far", () => {
    expect(nextSkip([[1, 2], [3]], rows, 5)).toBe(3);
  });

  it("stops once every row is loaded", () => {
    expect(nextSkip([[1, 2], [3]], rows, 3)).toBeUndefined();
  });

  it("stops when the total shrinks below what is loaded", () => {
    expect(nextSkip([[1, 2, 3]], rows, 2)).toBeUndefined();
  });
});
