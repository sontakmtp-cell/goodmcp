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
  within,
} from "@testing-library/react";
import { createHash, randomBytes } from "node:crypto";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { Api, type Plugin, type Workspace } from "../api";
import { Admin } from "../Admin";
import { Portal } from "../App";
import { PluginDetail } from "../Plugins";

// Only the decorative canvas is omitted: jsdom has no real canvas/layout engine.
vi.mock("../Sharks", () => ({ Sharks: () => <canvas aria-hidden="true" /> }));

const root = resolve(process.cwd(), "../..");
const ORIGIN = "http://127.0.0.1:4173";
const ISSUER = "http://127.0.0.1:18080/auth";
const scopes = "hub:read hub:write tools:run projects:read projects:write";
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
    const registration = await auth("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_name: "G6 live React acceptance",
        redirect_uris: [ORIGIN + "/oauth/callback"],
        scope: scopes,
      }),
    });
    if (registration.status !== 201)
      throw new Error(`Local G2 registration failed (${registration.status}).`);
    const clientId = (await registration.json()).client_id;
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
    const verifier = randomBytes(32).toString("base64url"),
      state = randomBytes(24).toString("base64url");
    const authorize = await auth(
      "/auth/authorize?" +
        new URLSearchParams({
          client_id: clientId,
          redirect_uri: ORIGIN + "/oauth/callback",
          response_type: "code",
          scope: scopes,
          state,
          resource: ISSUER.replace(/\/auth$/, "") + "/mcp",
          code_challenge_method: "S256",
          code_challenge: createHash("sha256")
            .update(verifier)
            .digest("base64url"),
        }),
    );
    const consentText = await authorize.text();
    const options = [
      ...consentText.matchAll(/<option value="([^"]+)">([^<]+)<\/option>/g),
    ];
    const workspace = options.find(
      (m) => !m[2].includes("G2 revoked fixture"),
    )?.[1];
    if (!workspace)
      throw new Error("Local account has no acceptance workspace.");
    const consent = await auth(
      "/auth/authorize",
      form({
        csrf: csrf(consentText),
        workspace_id: workspace,
        consent: "allow",
      }),
    );
    if (consent.status !== 302)
      throw new Error(`Local G2 consent failed (${consent.status}).`);
    const callback = new URL(consent.headers.get("location")!);
    if (
      callback.searchParams.get("state") !== state ||
      callback.searchParams.get("iss") !== ISSUER
    )
      throw new Error("Local OAuth state/issuer mismatch.");
    const exchanged = await auth(
      "/auth/token",
      form({
        grant_type: "authorization_code",
        client_id: clientId,
        redirect_uri: ORIGIN + "/oauth/callback",
        resource: ISSUER.replace(/\/auth$/, "") + "/mcp",
        code: callback.searchParams.get("code")!,
        code_verifier: verifier,
      }),
    );
    if (exchanged.status !== 200)
      throw new Error(`Local G2 exchange failed (${exchanged.status}).`);
    const token = (await exchanged.json()).access_token;
    try {
      vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) =>
        nativeFetch(
          typeof input === "string" ? new URL(input, ORIGIN) : input,
          init,
        ),
      );
      const probe = new Api(token, { workspace_id: "", name: "", role: "" });
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
      const api = new Api(token, verified);
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
      const credential = {
        access_token: token,
        client_id: clientId,
        admin: true,
      };
      function Session() {
        const [active, setActive] = useState(true);
        return active ? (
          <Admin
            api={api}
            credential={credential}
            onLogin={() => {}}
            onForget={() => setActive(false)}
            onPortal={() => {}}
          />
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
      fireEvent.click(
        screen.getByRole("button", { name: "Người dùng & Kết nối" }),
      );
      fireEvent.click(
        screen.getByRole("button", { name: "Thu hồi phiên web" }),
      );
      fireEvent.click(
        within(screen.getByRole("dialog")).getByRole("button", {
          name: "Xác nhận",
        }),
      );
      await waitFor(
        () =>
          expect(
            screen.getByText("Plugin của bạn luôn riêng tư"),
          ).toBeVisible(),
        { timeout: 10000 },
      );
      const after = await nativeFetch(
        ORIGIN +
          "/api/v1/me/workspaces?live_revoke=" +
          randomBytes(8).toString("hex"),
        { headers: { Authorization: "Bearer " + token }, cache: "no-store" },
      );
      expect(after.status).toBe(401);
      const evidence = root + "/Docs/reports/assets/g6-completion";
      await mkdir(evidence, { recursive: true });
      await writeFile(
        evidence + "/live-ui-flow.json",
        JSON.stringify(
          {
            passed: true,
            layer:
              "real React DOM in jsdom with actual local OAuth/API/Python; not a real-browser capture",
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
      await auth("/auth/revoke", form({ client_id: clientId, token }));
    }
  },
  45000,
);
