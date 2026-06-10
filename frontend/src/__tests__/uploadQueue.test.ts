import "fake-indexeddb/auto";
import { beforeEach, describe, expect, it } from "vitest";
import { dequeue, enqueue, getQueue, updateStatus } from "@/lib/uploadQueue";

describe("uploadQueue", () => {
  beforeEach(async () => {
    const items = await getQueue();
    for (const item of items) {
      await dequeue(item.id);
    }
  });

  it("enqueues a file with draft status", async () => {
    const file = new File(["data"], "test.png", { type: "image/png" });
    const item = await enqueue(file);
    expect(item.status).toBe("draft");
    expect(item.filename).toBe("test.png");
  });

  it("getQueue returns enqueued items", async () => {
    const file = new File(["data"], "a.png", { type: "image/png" });
    await enqueue(file);
    const q = await getQueue();
    expect(q.some((i) => i.filename === "a.png")).toBe(true);
  });

  it("updateStatus changes item status", async () => {
    const file = new File(["x"], "b.png", { type: "image/png" });
    const item = await enqueue(file);
    await updateStatus(item.id, "pending");
    const q = await getQueue();
    expect(q.find((i) => i.id === item.id)?.status).toBe("pending");
  });

  it("dequeue removes an item", async () => {
    const file = new File(["x"], "c.png", { type: "image/png" });
    const item = await enqueue(file);
    await dequeue(item.id);
    const q = await getQueue();
    expect(q.find((i) => i.id === item.id)).toBeUndefined();
  });
});
