import { describe, it, expect, vi } from "vitest";
import {
  render,
  screen,
  waitFor,
  fireEvent,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { Api, ApiError, type Plugin } from "../api";
import { App, Portal, Catalog } from "../App";
import { Admin } from "../Admin";
import { PluginDetail, JobPanel } from "../Plugins";
import { SchemaForm } from "../SchemaForm";
import { ConfirmButton, Plain } from "../ui";
vi.mock("../Sharks", () => ({ Sharks: () => <canvas aria-hidden="true" /> }));
const workspace = {
  workspace_id: "10000000-0000-4000-8000-000000000001",
  name: "Test workspace",
  role: "owner",
};
const plugin: Plugin = {
  installation_id: "10000000-0000-4000-8000-000000000003",
  plugin_version_id: "10000000-0000-4000-8000-000000000004",
  enabled: true,
  revision: 7,
  name: "Fixture plugin",
  manifest_version: "1.0",
  preview: {},
};
const api = () => new Api("test-only-not-a-real-token", workspace);
const portalProps = {
  api: null,
  credential: null,
  onLogin: vi.fn(),
  onForget: vi.fn(),
  onAdmin: vi.fn(),
};
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify({ data }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
describe("portal privacy and interaction", () => {
  it("does not fetch private catalog before authentication or offer signup", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    render(<Portal {...portalProps} />);
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getByText("Plugin của bạn luôn riêng tư")).toBeVisible();
    expect(screen.queryByText("Đăng ký")).toBeNull();
    expect(screen.getByLabelText("Đường dẫn MCP")).toHaveValue(
      "https://mcp.example.invalid/mcp",
    );
  });
  it("opens host-specific guide using keyboard and marks selection", async () => {
    const u = userEvent.setup();
    render(<Portal {...portalProps} />);
    const host = screen.getByRole("button", { name: "Claude" });
    host.focus();
    await u.keyboard("{Enter}");
    expect(host).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByRole("heading", { name: "Kết nối với Claude" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: /Đóng hướng dẫn Claude/ }),
    ).toBeVisible();
    expect(screen.getByText(/Chưa nghiệm thu kết nối Claude/)).toBeVisible();
  });
  it("reports clipboard success only after write succeeds", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    render(<Portal {...portalProps} />);
    fireEvent.click(screen.getByRole("button", { name: "Sao chép" }));
    expect(await screen.findByText("Đã sao chép đường dẫn.")).toBeVisible();
    expect(writeText).toHaveBeenCalledWith("https://mcp.example.invalid/mcp");
  });
  it("reports clipboard rejection with manual alternative", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockRejectedValue(new Error("permission")) },
      configurable: true,
    });
    render(<Portal {...portalProps} />);
    fireEvent.click(screen.getByRole("button", { name: "Sao chép" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "sao chép đường dẫn thủ công",
    );
    expect(screen.queryByText("Đã sao chép đường dẫn.")).toBeNull();
  });
  it("shows only enabled plugins in a workspace and pages server cursor", async () => {
    const f = vi
      .fn()
      .mockResolvedValueOnce(
        response({
          items: [
            plugin,
            {
              ...plugin,
              installation_id: "disabled",
              enabled: false,
              name: "Hidden disabled",
            },
          ],
          next_cursor: "next-id",
        }),
      )
      .mockResolvedValueOnce(response({ items: [], next_cursor: null }));
    vi.stubGlobal("fetch", f);
    render(
      <Catalog api={api()} canAdmin={false} onAdmin={() => {}} />,
    );
    expect(await screen.findByText("Fixture plugin")).toBeVisible();
    expect(screen.queryByText("Hidden disabled")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Trang tiếp" }));
    await waitFor(() => expect(f).toHaveBeenCalledTimes(2));
    expect(f.mock.calls[1][0]).toContain("cursor=next-id");
    expect(await screen.findByText(/Chưa có plugin đang bật/)).toBeVisible();
  });
  it("shows page number and admin CTA in empty catalog for admins", async () => {
    const f = vi
      .fn()
      .mockResolvedValue(response({ items: [], next_cursor: null }));
    vi.stubGlobal("fetch", f);
    const onAdmin = vi.fn();
    render(<Catalog api={api()} canAdmin={true} onAdmin={onAdmin} />);
    expect(await screen.findByText(/Chưa có plugin đang bật/)).toBeVisible();
    expect(screen.getByText("Trang 1")).toBeVisible();
    const cta = screen.getByRole("button", { name: /Mở trang quản trị/ });
    fireEvent.click(cta);
    expect(onAdmin).toHaveBeenCalled();
  });
  it("does not leak raw server error messages into the interface", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ error: { message: "postgres://secret" } }),
            { status: 500 },
          ),
        ),
    );
    render(
      <Catalog api={api()} canAdmin={false} onAdmin={() => {}} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Máy chủ đang gặp lỗi",
    );
    expect(document.body).not.toHaveTextContent("postgres://secret");
  });
  it("shows loading before the first real response", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
    render(
      <Catalog api={api()} canAdmin={false} onAdmin={() => {}} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Đang tải");
    expect(document.querySelector("[aria-busy=true]")).toBeTruthy();
  });
});
describe("admin boundaries and real API mappings", () => {
  it("submits schema fields to the selected binding and displays a real-shaped runtime error", async () => {
    const binding = {
      id: "binding-fixture",
      mcp_name: "finance_cit_estimate",
      input_schema: {
        type: "object",
        properties: { revenue: { type: "number" }, cost: { type: "number" } },
        required: ["revenue", "cost"],
      },
    };
    const f = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/bindings")) return response([binding]);
      if (url.endsWith("/invocations"))
        return response({ id: plugin.installation_id, state: "queued" });
      if (url.includes("/jobs/"))
        return response({
          id: plugin.installation_id,
          state: "failed",
          error: { code: "runtime_unavailable" },
        });
      return response({ items: [], next_cursor: null });
    });
    vi.stubGlobal("fetch", f);
    render(<PluginDetail api={api()} plugin={plugin} onBack={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Công cụ Python" }));
    await waitFor(() =>
      expect(
        screen.getByRole("option", { name: "Thuế thu nhập doanh nghiệp" }),
      ).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: binding.id },
    });
    fireEvent.change(screen.getByLabelText("Doanh thu (VND)"), {
      target: { value: "1000" },
    });
    fireEvent.change(screen.getByLabelText("Chi phí (VND)"), {
      target: { value: "600" },
    });
    fireEvent.submit(
      screen.getByRole("button", { name: "Chạy bằng Python" }).closest("form")!,
    );
    expect(
      await screen.findByText(/Môi trường Python chưa sẵn sàng/),
    ).toBeVisible();
    const call = f.mock.calls.find(([url]) => url.endsWith("/invocations"))!;
    expect(JSON.parse(call[1]!.body as string)).toMatchObject({
      binding_id: binding.id,
      arguments: { revenue: 1000, cost: 600 },
    });
    expect(screen.queryByText("Kết quả từ máy chủ")).toBeNull();
  });
  it("removes private catalog after a live-shaped 401 response", async () => {
    sessionStorage.setItem(
      "goodmcp:oauth",
      JSON.stringify({
        state: "state",
        verifier: "verifier",
        client_id: "client",
        redirect_uri: location.origin + "/oauth/callback",
        created: Date.now(),
        admin: false,
      }),
    );
    history.replaceState(
      null,
      "",
      "/oauth/callback?state=state&iss=http%3A%2F%2F127.0.0.1%3A18080%2Fauth&code=test-code",
    );
    const f = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ access_token: "fixture-only" })),
      )
      .mockResolvedValueOnce(response([workspace]))
      .mockResolvedValueOnce(response({ items: [plugin], next_cursor: "next" }))
      .mockResolvedValueOnce(response(null, 401));
    vi.stubGlobal("fetch", f);
    render(<App />);
    expect(await screen.findByText("Fixture plugin")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Trang tiếp" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("hết hạn");
    expect(screen.queryByText("Fixture plugin")).toBeNull();
    expect(screen.getByText("Plugin của bạn luôn riêng tư")).toBeVisible();
  });
  it.each(["member", "viewer"])("blocks %s before any API fetch", (role) => {
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    render(
      <Admin
        api={new Api("test", { ...workspace, role })}
        credential={null}
        onLogin={() => {}}
        onForget={() => {}}
        onPortal={() => {}}
      />,
    );
    expect(screen.getByText("Chưa có quyền quản trị")).toBeVisible();
    expect(f).not.toHaveBeenCalled();
  });
  it("offers login for unauthenticated admin without private data", () => {
    render(
      <Admin
        api={null}
        credential={null}
        onLogin={() => {}}
        onForget={() => {}}
        onPortal={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: "Đăng nhập" })).toBeVisible();
    expect(screen.queryByRole("navigation", { name: "Quản trị" })).toBeNull();
  });
  it("has exactly five groups and no invented system metrics", async () => {
    render(
      <Admin
        api={api()}
        credential={null}
        onLogin={() => {}}
        onForget={() => {}}
        onPortal={() => {}}
      />,
    );
    expect(
      within(screen.getByRole("navigation", { name: "Quản trị" })).getAllByRole(
        "button",
      ),
    ).toHaveLength(5);
    fireEvent.click(screen.getByRole("button", { name: "Hệ thống" }));
    expect(
      screen.getByText(/backend chưa cung cấp API xem logs/),
    ).toBeVisible();
    expect(screen.getByText("Chưa kiểm tra")).toBeVisible();
  });
  it("sends backend revision and selected version on confirmed rollback", async () => {
    const f = vi
      .fn()
      .mockResolvedValueOnce(
        response({
          items: [{ id: "old", manifest_version: "0.9", project_pins: 1 }],
          next_cursor: null,
        }),
      )
      .mockResolvedValueOnce(
        response({ plugin_version_id: "old", enabled: true, revision: 8 }),
      )
      .mockResolvedValue(response({ items: [], next_cursor: null }));
    vi.stubGlobal("fetch", f);
    render(<PluginDetail api={api()} plugin={plugin} onBack={() => {}} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Dùng bản này" }),
    );
    expect(f).toHaveBeenCalledTimes(1);
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "Xác nhận",
      }),
    );
    await waitFor(() =>
      expect(f.mock.calls.some(([, i]) => i?.method === "PUT")).toBe(true),
    );
    const call = f.mock.calls.find(([, i]) => i?.method === "PUT")!;
    expect(JSON.parse(call[1].body)).toEqual({
      version_id: "old",
      enabled: true,
      expected_revision: 7,
    });
  });
  it("keeps conflict error visible and does not claim a successful version switch", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          response({
            items: [{ id: "old", manifest_version: "0.9", project_pins: 1 }],
            next_cursor: null,
          }),
        )
        .mockResolvedValue(response(null, 409)),
    );
    render(<PluginDetail api={api()} plugin={plugin} onBack={() => {}} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Dùng bản này" }),
    );
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "Xác nhận",
      }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Dữ liệu đã thay đổi",
    );
    expect(screen.getByText(/Revision 7/)).toBeVisible();
  });
  it("renders plugin HTML as inert text", () => {
    const { container } = render(
      <Plain value={"<script>bad()</script><img src=x onerror=bad()>"} />,
    );
    expect(container.querySelector("script,img")).toBeNull();
    expect(screen.getByText(/<script>/)).toBeVisible();
  });
  it("renders terminal job results without running formulas", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response({
          id: plugin.installation_id,
          state: "succeeded",
          result: { amount: 314159 },
          error: null,
        }),
      ),
    );
    render(<JobPanel api={api()} initialId={plugin.installation_id} />);
    expect(await screen.findByText("Kết quả từ máy chủ")).toBeVisible();
    expect(screen.getByText(/314159/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Hủy công việc" })).toBeNull();
  });
  it("shows cancellation request as pending until server confirms terminal state", async () => {
    const f = vi
      .fn()
      .mockResolvedValueOnce(
        response({ id: plugin.installation_id, state: "running" }),
      )
      .mockResolvedValueOnce(
        response({
          id: plugin.installation_id,
          state: "running",
          cancel_requested: true,
        }),
      )
      .mockResolvedValue(
        response({
          id: plugin.installation_id,
          state: "running",
          cancel_requested: true,
        }),
      );
    vi.stubGlobal("fetch", f);
    render(<JobPanel api={api()} initialId={plugin.installation_id} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Hủy công việc" }),
    );
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "Xác nhận",
      }),
    );
    expect(await screen.findByText(/Đã yêu cầu hủy/)).toBeVisible();
    expect(screen.queryByText("Đã hủy")).toBeNull();
  });
});
describe("schema form and confirmation", () => {
  it("converts typed input according to backend schema, supports nullable and enums", async () => {
    const submit = vi.fn();
    const u = userEvent.setup();
    render(
      <SchemaForm
        busy={false}
        schema={{
          properties: {
            revenue: { type: "number", minimum: 0 },
            year: {
              anyOf: [{ type: "integer", minimum: 1 }, { type: "null" }],
            },
            category: { type: "string", enum: ["raw_material"] },
          },
          required: ["revenue", "category"],
        }}
        onSubmit={submit}
      />,
    );
    await u.type(screen.getByLabelText("Doanh thu (VND)"), "500");
    await u.selectOptions(screen.getByLabelText("Nhóm hàng"), "raw_material");
    fireEvent.submit(
      screen.getByRole("button", { name: "Chạy bằng Python" }).closest("form")!,
    );
    expect(submit).toHaveBeenCalledWith({
      revenue: 500,
      category: "raw_material",
    });
  });
  it("refuses unsupported schemas instead of guessing executable JSON", () => {
    render(
      <SchemaForm
        busy={false}
        schema={{ properties: { arbitrary: { type: "object" } } }}
        onSubmit={() => {}}
      />,
    );
    expect(
      screen.getByText(/kiểu dữ liệu chưa được giao diện hỗ trợ/),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Chạy bằng Python" }),
    ).toBeNull();
  });
  it("does not perform destructive action when confirmation is cancelled", async () => {
    const action = vi.fn();
    render(
      <ConfirmButton title="Xác nhận hủy?" detail="Kiểm tra" onConfirm={action}>
        Hủy
      </ConfirmButton>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Hủy" }));
    fireEvent.click(screen.getByRole("button", { name: "Giữ nguyên" }));
    expect(action).not.toHaveBeenCalled();
  });
});
describe("automatic accessibility DOM checks", () => {
  it.each(["portal", "admin"])(
    "has no axe violations for %s (layout/contrast verified in browser separately)",
    async (kind) => {
      const result = render(
        kind === "portal" ? (
          <Portal {...portalProps} />
        ) : (
          <Admin
            api={api()}
            credential={null}
            onLogin={() => {}}
            onForget={() => {}}
            onPortal={() => {}}
          />
        ),
      );
      const audit = await axe.run(result.container, {
        rules: {
          "color-contrast": { enabled: false },
          region: { enabled: false },
        },
      });
      expect(audit.violations.map((x) => x.id)).toEqual([]);
    },
  );
});
