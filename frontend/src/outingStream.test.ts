import { afterEach, describe, expect, it, vi } from "vitest";
import { streamOuting } from "./api";
afterEach(() => vi.unstubAllGlobals());
describe("POST SSE transport", () => {
  it("parses split UTF-8 chunks and multiple events", async () => {
    const encoder = new TextEncoder();
    const bytes = encoder.encode(
      'data: {"sequence":1,"message":"Café","result":null}\r\n\r\ndata: {"sequence":2,"result":{"status":"PARTIAL"}}\r\n\r\n',
    );
    const body = new ReadableStream({
      start(c) {
        for (let i = 0; i < bytes.length; i += 1)
          c.enqueue(bytes.slice(i, i + 1));
        c.close();
      },
    });
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response(body, {
          headers: { "Content-Type": "text/event-stream" },
        }),
      );
    vi.stubGlobal("fetch", fetcher);
    const listener = vi.fn();
    await streamOuting(
      { text: "dining" },
      new AbortController().signal,
      listener,
    );
    expect(listener.mock.calls[0][0].message).toBe("Café");
    expect(listener).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls[0][1].method).toBe("POST");
  });
  it("rejects a stream ending without a final result", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response('data: {"sequence":1}\n\n')),
    );
    await expect(
      streamOuting({}, new AbortController().signal, vi.fn()),
    ).rejects.toThrow("before a result");
  });
});
