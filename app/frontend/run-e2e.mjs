import { spawn } from "node:child_process";
import { resolve } from "node:path";
import { once } from "node:events";
import { unlink } from "node:fs/promises";
const root = resolve("../..");
const db = resolve(`.e2e-${Date.now()}.db`);
const python =
  process.platform === "win32"
    ? resolve(root, ".venv/Scripts/python.exe")
    : resolve(root, ".venv/bin/python");
const server = spawn(
  python,
  [
    "-m",
    "uvicorn",
    "app.backend.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "8010",
  ],
  {
    cwd: root,
    env: { ...process.env, DATABASE_PATH: db },
    stdio: "inherit",
    windowsHide: true,
  },
);
let code = 1;
try {
  let ready = false;
  for (let i = 0; i < 60; i++) {
    if (server.exitCode !== null)
      throw new Error("API exited before becoming ready");
    try {
      const r = await fetch("http://127.0.0.1:8010/api/products/1");
      if (r.ok) {
        ready = true;
        break;
      }
    } catch {}
    await new Promise((r) => setTimeout(r, 250));
  }
  if (!ready) throw new Error("API did not become ready");
  const child = spawn(
    process.execPath,
    [resolve("node_modules/@playwright/test/cli.js"), "test"],
    { stdio: "inherit", windowsHide: true },
  );
  [code] = await once(child, "exit");
} finally {
  const stopped = once(server, "exit");
  server.kill();
  await stopped;
  for (const suffix of ["", "-wal", "-shm"])
    await unlink(db + suffix).catch(() => {});
}
process.exitCode = code ?? 1;
