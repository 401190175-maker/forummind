import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { parse as parseUrl } from "node:url";
import { parseInvocation } from "./contracts.js";
import { NativePiService } from "./service.js";

export function createRuntimeHttpServer(service: NativePiService): Server {
  return createServer(async (request, response) => {
    try {
      if (request.headers["x-forummind-runtime-token"] !== service.config.runtimeToken) {
        return sendError(response, 401, "unauthorized", "runtime token required");
      }
      const url = parseUrl(request.url ?? "/", true);
      const pathname = url.pathname ?? "/";
      if (request.method === "GET" && pathname === "/health") {
        return sendJson(response, 200, service.health());
      }
      if (request.method === "POST" && pathname === "/v1/provider/check") {
        await readJson(request, service.config.maxRequestBytes);
        return sendJson(response, 200, await service.checkProvider());
      }
      if (request.method === "POST" && pathname === "/v1/sessions") {
        const body = await readJson(request, service.config.maxRequestBytes);
        const source = isObject(body) && isObject(body.invocation) ? body.invocation : body;
        const session = await service.createSession(parseInvocation(source));
        return sendJson(response, 200, session);
      }
      const match = pathname.match(/^\/v1\/sessions\/([^/]+)(?:\/(prompts|steer|follow-up|abort|events))?$/);
      if (!match) {
        if (request.method === "GET" && pathname === "/health") return sendJson(response, 200, service.health());
        return sendError(response, 404, "not_found", "route not found");
      }
      const sessionId = decodeURIComponent(match[1]);
      const action = match[2];
      if (request.method === "GET" && action === "events") {
        const after = Number(url.query.after ?? 0);
        return sendJson(response, 200, { events: service.events(sessionId, Number.isFinite(after) ? after : 0) });
      }
      if (request.method === "DELETE" && !action) {
        return sendJson(response, 200, await service.dispose(sessionId));
      }
      const body = await readJson(request, service.config.maxRequestBytes);
      if (request.method === "POST" && action === "prompts") {
        const invocation = isObject(body) && isObject(body.invocation) ? parseInvocation(body.invocation) : undefined;
        return sendJson(response, 200, await service.prompt(sessionId, invocation));
      }
      if (request.method === "POST" && action === "steer") {
        return sendJson(response, 200, await service.steer(sessionId, readMessage(body)));
      }
      if (request.method === "POST" && action === "follow-up") {
        return sendJson(response, 200, await service.followUp(sessionId, readMessage(body)));
      }
      if (request.method === "POST" && action === "abort") {
        return sendJson(response, 200, await service.abort(sessionId));
      }
      return sendError(response, 404, "not_found", "route not found");
    } catch (error) {
      if (error instanceof RequestBodyTooLargeError) {
        return sendError(response, 413, "request_too_large", error.message);
      }
      const message = error instanceof Error ? error.message : String(error);
      const code = message.includes("not found") ? "not_found" : "invalid_request";
      return sendError(response, code === "not_found" ? 404 : 400, code, message);
    }
  });
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function readMessage(value: unknown): string {
  if (!isObject(value) || typeof value.message !== "string" || !value.message.trim()) throw new Error("message required");
  return value.message;
}

class RequestBodyTooLargeError extends Error {}

async function readJson(request: IncomingMessage, maxBytes: number): Promise<unknown> {
  const chunks: Buffer[] = [];
  let total = 0;
  for await (const chunk of request) {
    const value = Buffer.from(chunk);
    total += value.byteLength;
    if (total > maxBytes) throw new RequestBodyTooLargeError("request body exceeds configured limit");
    chunks.push(value);
  }
  if (chunks.length === 0) return {};
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function sendJson(response: ServerResponse, status: number, payload: unknown): void {
  const body = JSON.stringify(payload);
  response.writeHead(status, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) });
  response.end(body);
}

function sendError(response: ServerResponse, status: number, code: string, message: string): void {
  sendJson(response, status, { error: { code, message, retryable: status >= 500 } });
}
