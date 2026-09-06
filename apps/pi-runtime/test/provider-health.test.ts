import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { loadConfig } from "../src/config.js";
import { createRuntimeHttpServer } from "../src/http-server.js";
import { NativePiService } from "../src/service.js";
import { SessionRegistry } from "../src/session-registry.js";

function service(overrides: Record<string, string> = {}): NativePiService {
  const config = loadConfig({
    PI_RUNTIME_TOKEN: "runtime-secret",
    PI_PROVIDER: "openai-compatible",
    PI_MODEL: "research-model",
    PI_API_KEY: "provider-secret",
    PI_BASE_URL: "http://127.0.0.1:1",
    PI_SESSION_ROOT: `${process.cwd()}/.runtime/provider-health-sessions`,
    PI_PROMPT_TIMEOUT_MS: "100",
    ...overrides,
  });
  const registry = new SessionRegistry({ storage: "memory" });
  return new NativePiService({ config, registry });
}

async function listenProvider(handler: (request: IncomingMessage, response: ServerResponse) => void): Promise<Server> {
  const server = createServer(async (request, response) => {
    handler(request, response);
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  return server;
}

function port(server: Server): number {
  return (server.address() as { port: number }).port;
}

async function close(server: Server): Promise<void> {
  await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
}

test("runtime health exposes provider readiness without the API key", () => {
  const health = service().health() as Record<string, unknown>;

  assert.equal(health.configured, true);
  assert.equal(health.provider, "openai-compatible");
  assert.equal(health.model, "research-model");
  assert.equal(typeof health.reachable, "boolean");
  assert.equal(typeof health.latency_ms, "number");
  assert.equal(typeof health.error_code, "string");
  assert.equal("apiKey" in health, false);
  assert.equal(JSON.stringify(health).includes("provider-secret"), false);
});

test("provider check maps an unreachable provider to a secret-free result", async () => {
  const runtime = service();
  const server = createRuntimeHttpServer(runtime);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const address = server.address() as { port: number };
    const response = await fetch(`http://127.0.0.1:${address.port}/v1/provider/check`, {
      method: "POST",
      headers: { "X-ForumMind-Runtime-Token": "runtime-secret" },
      body: "{}",
    });

    assert.equal(response.status, 200);
    const body = await response.json() as Record<string, unknown>;
    assert.equal(body.reachable, false);
    assert.equal(typeof body.error_code, "string");
    assert.equal(JSON.stringify(body).includes("provider-secret"), false);
  } finally {
    await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
});

test("unconfigured provider is reported without probing the network", async () => {
  const runtime = service({ PI_MODEL: "", PI_API_KEY: "", PI_BASE_URL: "" });
  const health = await runtime.checkProvider();

  assert.equal(health.configured, false);
  assert.equal(health.reachable, false);
  assert.equal(health.error_code, "provider_unconfigured");
});

test("provider check rejects a malformed completion response", async () => {
  const provider = await listenProvider((_request, response) => {
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end(JSON.stringify({ unexpected: true }));
  });
  try {
    const runtime = service({ PI_BASE_URL: `http://127.0.0.1:${port(provider)}` });
    const health = await runtime.checkProvider();

    assert.equal(health.reachable, false);
    assert.equal(health.error_code, "provider_protocol");
  } finally {
    await close(provider);
  }
});

test("provider check maps a timeout to a stable error code", async () => {
  const provider = await listenProvider((_request, _response) => undefined);
  try {
    const runtime = service({
      PI_BASE_URL: `http://127.0.0.1:${port(provider)}`,
      PI_PROMPT_TIMEOUT_MS: "10",
    });
    const health = await runtime.checkProvider();

    assert.equal(health.reachable, false);
    assert.equal(health.error_code, "provider_timeout");
  } finally {
    await close(provider);
  }
});

test("provider check requires the runtime token", async () => {
  const runtime = service();
  const server = createRuntimeHttpServer(runtime);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const response = await fetch(`http://127.0.0.1:${port(server)}/v1/provider/check`, {
      method: "POST",
      body: "{}",
    });
    assert.equal(response.status, 401);
  } finally {
    await close(server);
  }
});
