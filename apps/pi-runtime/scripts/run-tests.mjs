import { readdir } from "node:fs/promises";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

const requested = process.argv.slice(2).filter((name) => name !== "--");
const testNames = requested.length > 0
  ? requested.map((name) => name.replace(/^test[\\/]/, "").replace(/\.ts$/, ".js"))
  : (await readdir(resolve("dist/test")))
      .filter((name) => name.endsWith(".test.js"));
const testFiles = testNames.map((name) => resolve("dist/test", name));
const result = spawnSync(process.execPath, ["--test", ...testFiles], { stdio: "inherit" });
process.exit(result.status ?? 1);
