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
