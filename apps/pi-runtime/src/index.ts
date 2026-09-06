import { loadConfig } from "./config.js";
import { createRuntimeHttpServer } from "./http-server.js";
import { NativePiService } from "./service.js";

const config = loadConfig();
const service = new NativePiService({ config });
const server = createRuntimeHttpServer(service);

server.listen(config.port, config.host, () => {
  process.stdout.write(`ForumMind Pi Runtime listening on ${config.host}:${config.port}\n`);
});

const shutdown = async () => {
  await service.close().catch(() => undefined);
  server.close();
};
process.once("SIGTERM", () => void shutdown());
process.once("SIGINT", () => void shutdown());
