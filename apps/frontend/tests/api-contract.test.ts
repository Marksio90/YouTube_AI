import assert from "node:assert/strict";
import test from "node:test";

import { apiClient, ApiClientError } from "../src/lib/api/client";

type FetchMock = typeof fetch;

function response(body: unknown, init: ResponseInit = {}): Response {
  return new Response(body === null ? null : JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

test("API contract: GET returns parsed JSON payload", async () => {
  const originalFetch = global.fetch;
  global.fetch = (async () => response({ ok: true, items: [1, 2, 3] })) as FetchMock;

  const data = await apiClient.get<{ ok: boolean; items: number[] }>("/workflows");

  assert.equal(data.ok, true);
  assert.deepEqual(data.items, [1, 2, 3]);
  global.fetch = originalFetch;
});

test("API contract: client refreshes auth once on 401 and retries request", async () => {
  const originalFetch = global.fetch;
  const calls: string[] = [];

  global.fetch = (async (input: RequestInfo | URL) => {
    const url = String(input);
    calls.push(url);

    if (url.endsWith("/workflows")) {
      const workflowsCallCount = calls.filter((c) => c.endsWith("/workflows")).length;
      if (workflowsCallCount === 1) {
        return response({ code: "UNAUTHORIZED", message: "expired", details: null }, { status: 401 });
      }
      return response({ success: true });
    }

    if (url.endsWith("/auth/refresh")) {
      return response({}, { status: 200 });
    }

    throw new Error(`Unexpected URL: ${url}`);
  }) as FetchMock;

  const data = await apiClient.get<{ success: boolean }>("/workflows");

  assert.equal(data.success, true);
  assert.deepEqual(
    calls.map((c) => c.replace("http://localhost:8000/api/v1", "")),
    ["/workflows", "/auth/refresh", "/workflows"],
  );

  global.fetch = originalFetch;
});

test("API contract: API errors throw ApiClientError", async () => {
  const originalFetch = global.fetch;
  global.fetch = (async () =>
    response({ code: "BAD_REQUEST", message: "invalid payload", details: { field: "name" } }, { status: 400 })) as FetchMock;

  await assert.rejects(
    () => apiClient.post("/topics", { name: "" }),
    (error: unknown) => {
      assert.equal(error instanceof ApiClientError, true);
      const typedError = error as ApiClientError;
      assert.equal(typedError.status, 400);
      assert.equal(typedError.error.code, "BAD_REQUEST");
      return true;
    },
  );

  global.fetch = originalFetch;
});
