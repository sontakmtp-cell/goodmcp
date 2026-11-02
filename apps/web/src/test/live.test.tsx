/** Opt-in integration: real React UI in jsdom → real G2/G4 local APIs → Python.
 * Run with GOODMCP_LIVE=1. No API/data mocks, and no credential is written to disk.
 * This is a DOM integration test, not a claim of a new real-browser screenshot.
 */
import { useState } from "react";
import { it, expect, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { randomBytes } from "node:crypto";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { Api, type Plugin, type Workspace } from "../api";
import { Account } from "../Workspace";
import { type WebSession } from "../auth";
import { Portal } from "../App";
import { PluginDetail } from "../Plugins";

// Only the decorative canvas is omitted: jsdom has no real canvas/layout engine.
vi.mock("../Sharks", () => ({ Sharks: () => <canvas aria-hidden="true" /> }));

const root = resolve(process.cwd(), "../..");
const ORIGIN = "http://127.0.0.1:4173";
const live = process.env.GOODMCP_LIVE === "1" ? it : it.skip;

live(
  "real schema form completes in original Python and real revoke removes the private session",
  async () => {
    const nativeFetch = globalThis.fetch;
    const cookies = new Map<string, string>();
    async function auth(path: string, init: RequestInit = {}) {
      const headers = new Headers(init.headers);
      if (cookies.size)
        headers.set(
          "Cookie",
          [...cookies].map(([k, v]) => `${k}=${v}`).join("; "),
        );
      const r = await nativeFetch(ORIGIN + path, {
        ...init,
        headers,
        redirect: "manual",
      });
      for (const cookie of r.headers.getSetCookie()) {
        const pair = cookie.split(";", 1)[0],
          split = pair.indexOf("=");
        cookies.set(pair.slice(0, split), pair.slice(split + 1));
      }
      return r;
    }
    const csrf = (text: string) => {
      const match = text.match(/name="csrf"[^>]*value="([^"\s]+)"/);
      if (!match)
        throw new Error("Local G2 did not provide the expected CSRF form.");
      return match[1];
    };
    const form = (values: Record<string, string>): RequestInit => ({
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(values),
    });
    const login = await auth("/auth/login");
    const password = (
      await readFile(root + "/.local/secrets/owner_password", "utf8")
    ).trim();
    const signed = await auth(
      "/auth/login",
      form({
        email: "owner@local.invalid",
        password,
        csrf: csrf(await login.text()),
      }),
    );
    if (signed.status !== 303)
      throw new Error(`Local G2 login failed (${signed.status}).`);
    const sessionResponse = await auth("/auth/web/session");
    if (sessionResponse.status !== 200) throw new Error(`Web session failed (${sessionResponse.status})`);
    const web: WebSession = (await sessionResponse.json()).data;
    const workspace = web.workspace_id;
    if (!workspace) throw new Error("Local owner has no workspace.");
    try {
      vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) =>
        auth(typeof input === "string" ? input : String(input), init),
      );
      const probe = new Api(web.csrf, { workspace_id: "", name: "", role: "" });
      const workspaces = await probe.request<Workspace[]>(
        "/api/v1/me/workspaces",
        {},
        false,
      );
      const verified = workspaces.find((w) => w.workspace_id === workspace);
      if (!verified || verified.role !== "owner")
        throw new Error(
          "G2 did not verify the expected local owner workspace.",
        );
      const api = new Api(web.csrf, verified);
      const plugins = await api.request<{ items: Plugin[] }>(
        "/plugins?limit=100",
      );
      const plugin = plugins.items.find(
        (p) => p.enabled && p.name === "vietnam-finance-tax-expert",
      );
      if (!plugin)
        throw new Error("The approved Finance plugin is not enabled locally.");
      const ui = render(
        <PluginDetail api={api} plugin={plugin} onBack={() => {}} />,
      );
      fireEvent.click(screen.getByRole("button", { name: "Công cụ Python" }));
      await screen.findByRole("option", { name: "Thuế thu nhập doanh nghiệp" });
      const binding = (
        await api.request<any[]>(
          `/installations/${plugin.installation_id}/bindings`,
        )
      ).find((b) => b.mcp_name === "finance_cit_estimate");
      if (!binding) throw new Error("The approved CIT binding is missing.");
      fireEvent.change(screen.getByRole("combobox"), {
        target: { value: binding.id },
      });
      fireEvent.change(
        screen.getByRole("spinbutton", { name: "Doanh thu (VND)" }),
        { target: { value: "1000" } },
      );
      fireEvent.change(
        screen.getByRole("spinbutton", { name: "Chi phí (VND)" }),
        { target: { value: "600" } },
      );
      fireEvent.submit(
        screen
          .getByRole("button", { name: "Chạy bằng Python" })
          .closest("form")!,
      );
      await screen.findByText("Kết quả từ máy chủ", {}, { timeout: 20000 });
      const result = JSON.parse(
        ui.container.querySelector(".plain")!.textContent!,
      );
      const release = JSON.parse(
        await readFile(root + "/.local/g4/active/release.json", "utf8"),
      );
      expect(result.provenance.original_python).toBe(true);
      expect(result.provenance.image_digest).toBe(release.image_digest);
      expect(result.provenance.release_digest).toBe(release.release_digest);
      expect(result.data.cit_with_incentive_VND).toBe(80);
      cleanup();
      function Session() {
        const [active, setActive] = useState(true);
        return active ? (
          <Account session={web} reload={async () => {}} onForget={() => setActive(false)} />
        ) : (
          <Portal
            api={null}
            credential={null}
            onLogin={() => {}}
            onForget={() => {}}
            onAdmin={() => {}}
          />
        );
      }
      render(<Session />);
      fireEvent.click(screen.getByRole("button", {name: "Đăng xuất thiết bị này"}));
      await waitFor(
        () =>
          expect(
            screen.getByText("Plugin của bạn luôn riêng tư"),
          ).toBeVisible(),
        { timeout: 10000 },
      );
      const after = await auth("/api/v1/me/workspaces?live_logout=" + randomBytes(8).toString("hex"));
      expect(after.status).toBe(401);
      const evidence = root + "/Docs/reports/evidence/G9";
      await mkdir(evidence, { recursive: true });
      await writeFile(
        evidence + "/live-ui-flow.json",
        JSON.stringify(
          {
            passed: true,
            layer:
              "real React DOM in jsdom with actual local cookie session/API/Python; not a real-browser capture",
            calculation: {
              input: { revenue: 1000, cost: 600, rate: 20 },
              result: result.data,
              provenance: result.provenance,
            },
            revoke: {
              protected_api_status: after.status,
              private_ui_removed: true,
            },
            api_mocks: false,
          },
          null,
          2,
        ),
      );
    } finally {
      cleanup();
      await auth("/auth/web/logout", {method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":web.csrf},body:JSON.stringify({all_devices:false})});
    }
  },
  45000,
);
