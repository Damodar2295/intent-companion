export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(
      typeof result.detail === "string"
        ? result.detail
        : "The request could not be validated. Please check your inputs.",
    );
  }
  return result as T;
}

export async function streamOuting(
  body: unknown,
  signal: AbortSignal,
  onEvent: (event: import("./types").OutingEvent) => void,
) {
  const response = await fetch("/api/outings/stream", {
    method: "POST",
    signal,
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json();
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Check destination, timezone and time window.",
    );
  }
  if (!response.body) throw new Error("Streaming is unavailable.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "",
    complete = false;
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer = (buffer + decoder.decode(value, { stream: !done })).replaceAll("\r\n", "\n");
      let index: number;
      while ((index = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, index);
        buffer = buffer.slice(index + 2);
        const text = block
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (text) {
          const event = JSON.parse(text) as import("./types").OutingEvent;
          onEvent(event);
          complete ||= Boolean(event.result);
        }
      }
      if (done) break;
    }
    if (!complete)
      throw new Error(
        "The stream ended before a result arrived. Please retry.",
      );
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

export function getGroundedOutingResponse(runId: string) {
  return api<import("./types").GroundedResponse>(`/v1/outings/${runId}/response`);
}
