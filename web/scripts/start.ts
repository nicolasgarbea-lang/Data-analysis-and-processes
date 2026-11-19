// Starts the planning service (Python) and the web app together: `bun run start`.
const api = Bun.spawn(["bun", "run", "api"], { stdout: "inherit", stderr: "inherit" });
const web = Bun.spawn(["bun", "run", "dev"], { stdout: "inherit", stderr: "inherit" });
const stop = () => {
  api.kill();
  web.kill();
  process.exit(0);
};
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
await Promise.race([api.exited, web.exited]);
stop();
