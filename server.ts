import { spawn } from "child_process";
import path from "path";

// Process supervisor for AI Studio environment
// Launches the pure Python backend server: server.py
const serverScript = path.resolve(process.cwd(), "server.py");
const args = [serverScript, ...process.argv.slice(2)];

console.log(`🚀 Starting Telegram Moderator (Pure Python): python3 ${args.join(" ")}`);

const pyProcess = spawn("python3", args, {
  stdio: "inherit",
  env: process.env,
});

pyProcess.on("error", (err) => {
  console.error("❌ Failed to start Python process:", err);
  process.exit(1);
});

pyProcess.on("exit", (code) => {
  process.exit(code ?? 0);
});

process.on("SIGINT", () => {
  pyProcess.kill("SIGINT");
});

process.on("SIGTERM", () => {
  pyProcess.kill("SIGTERM");
});
