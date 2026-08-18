import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    // Vite's dev server rejects requests whose Host header isn't on an
    // allowlist by default (DNS-rebinding protection) — correct for a
    // server exposed directly, but this one only ever receives requests
    // that already passed through nginx + the ngrok tunnel (see
    // docker-compose.yml's ngrok service), so the Host header is whatever
    // the current tunnel's domain happens to be, not something this repo
    // can hardcode. `true` disables the check entirely rather than
    // requiring a code change every time the tunnel gets a new domain.
    allowedHosts: true,
  },
});
