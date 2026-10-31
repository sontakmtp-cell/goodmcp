import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
// Development only: one fixed upstream, with G2's expected authority/origin.
const target = process.env.GOODMCP_API_ORIGIN || "http://127.0.0.1:18080";
const proxy = Object.fromEntries(
  ["/api", "/auth", "/.well-known", "/health"].map((path) => [
    path,
    {
      target,
      changeOrigin: true,
      configure(server: any) {
        server.on("proxyReq", (req: any) => {
          req.setHeader("Origin", new URL(target).origin);
        });
      },
    },
  ]),
);
export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", port: 4173, strictPort: true, proxy },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    exclude: ["node_modules/**", "dist/**"],
  },
});
