// Starts the Python planning service (api/server.py) on port 8000: `npm run api`.
// Picks the project's virtual environment on any system:
//   Windows: .venv\Scripts\python.exe    macOS / Linux: .venv/bin/python
import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const python = process.platform === "win32" ? join(root, ".venv", "Scripts", "python.exe") : join(root, ".venv", "bin", "python");

if (!existsSync(python)) {
  console.error(`Python not found at ${python}.\nCreate the virtual environment in the project folder first (see the main README).`);
  process.exit(1);
}

const child = spawn(python, ["-m", "uvicorn", "api.server:app", "--port", "8000"], { cwd: root, stdio: "inherit" });
// On Windows the venv's python.exe is a launcher that starts the real interpreter, so end the whole tree.
const stop = () => {
  if (process.platform === "win32" && child.pid) spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  else child.kill();
};
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
child.on("exit", (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
