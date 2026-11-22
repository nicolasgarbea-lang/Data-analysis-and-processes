// Starts the planning service (Python) and the web app together: `npm start` (or `bun run start`).
// Plain Node APIs and no TypeScript-only syntax, so Node 22.18+ runs it directly, and so does Bun.
import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const run = (args: string[]) => spawn(process.execPath, args, { cwd: web, stdio: "inherit" });

const api = run([join(web, "scripts", "api.mjs")]);
const dev = run([join(web, "node_modules", "vite", "bin", "vite.js")]);

// Windows: end the whole process tree (the Python launcher starts a second process).
const kill = (p: ChildProcess) => {
  if (process.platform === "win32" && p.pid) spawnSync("taskkill", ["/pid", String(p.pid), "/T", "/F"], { stdio: "ignore" });
  else p.kill();
};

let stopping = false;
const stop = (code = 0) => {
  if (stopping) return;
  stopping = true;
  kill(api);
  kill(dev);
  process.exit(code);
};
process.on("SIGINT", () => stop(0));
process.on("SIGTERM", () => stop(0));
api.on("exit", (code) => stop(code ?? 0));
dev.on("exit", (code) => stop(code ?? 0));
