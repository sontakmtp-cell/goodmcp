import { it, expect, vi, describe } from "vitest";
import { File as NodeFile } from "node:buffer";
import { Api, ApiError } from "../api";
import { checksum, sendZip, type Upload } from "../upload";
import { loadSession, webRequest, revoke } from "../auth";
const workspace = { workspace_id: "ws-a", name: "Fixture", role: "owner" };
describe("HTTP boundary", () => {
  it.each([401, 403, 404, 409, 413, 422, 429, 500, 503])(
    "handles HTTP %s without exposing credentials",
    async (status) => {
      const expired = vi.fn(),
        fetch = vi
          .fn()
          .mockResolvedValue(
            new Response("{}", {
              status,
              headers: { "x-request-id": "request-test" },
            }),
          );
      vi.stubGlobal("fetch", fetch);
      const api = new Api("private-test-token", workspace, expired);
      await expect(api.request("/plugins")).rejects.toMatchObject({
        status,
        requestId: "request-test",
      });
      expect(expired).toHaveBeenCalledTimes(status === 401 ? 1 : 0);
      expect(fetch.mock.calls[0][0]).toBe("/api/v1/workspaces/ws-a/plugins");
      expect(
        new Headers(fetch.mock.calls[0][1].headers).get("Authorization"),
      ).toBeNull();
      expect(fetch.mock.calls[0][1].credentials).toBe("same-origin");
    },
  );
  it("normalizes network errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("private stack")),
    );
    await expect(
      new Api("t", workspace).request("/plugins"),
    ).rejects.toMatchObject({ status: 0 });
  });
});
describe("ZIP transfer protocol", () => {
  const file = () => new NodeFile(["abcdef"], "plugin.zip") as unknown as File;
  const status = async (): Promise<Upload> => ({
    id: "upload-id",
    bytes: 6,
    sha256: await checksum(file()),
    part_size: 2,
    expected_parts: 3,
    received_parts: [0],
    state: "uploading",
    plugin_version_id: null,
    preview: null,
    error_code: null,
  });
  it("resumes using server received_parts, hashes each binary chunk and completes last", async () => {
    let u = await status();
    const calls: any[] = [];
    const fake = {
      request: vi.fn(async (path: string, init: any) => {
        calls.push({ path, init });
        if (init?.method === "PUT") {
          const part = Number(path.split("/").at(-1));
          u = { ...u, received_parts: [...u.received_parts, part] };
          expect(init.headers["X-Content-SHA256"]).toBe(
            await checksum(init.body),
          );
        }
        return u;
      }),
      post: vi.fn(async (path: string) => {
        calls.push({ path });
        return { ...u, state: "queued" };
      }),
    } as unknown as Api;
    const updates = vi.fn();
    await sendZip(
      fake,
      file(),
      "upload-id",
      updates,
      new AbortController().signal,
    );
    expect(calls.map((x) => x.path)).toEqual([
      "/uploads/upload-id",
      "/uploads/upload-id/parts/1",
      "/uploads/upload-id/parts/2",
      "/uploads/upload-id/complete",
    ]);
    expect(updates.mock.calls.at(-1)![0].state).toBe("queued");
  });
  it("rejects different ZIP before transmitting a part", async () => {
    const u = await status();
    const request = vi.fn().mockResolvedValue({ ...u, sha256: "0".repeat(64) });
    await expect(
      sendZip(
        { request } as unknown as Api,
        file(),
        "upload-id",
        () => {},
        new AbortController().signal,
      ),
    ).rejects.toThrow("không khớp");
    expect(request).toHaveBeenCalledTimes(1);
  });
  it("uses deterministic idempotency key if create response is lost", async () => {
    const posts: any[] = [];
    const fake = {
      post: vi.fn(async (p: string, data: any) => {
        posts.push(data);
        throw new ApiError(0);
      }),
    } as unknown as Api;
    for (let i = 0; i < 2; i++)
      await expect(
        sendZip(fake, file(), "", () => {}, new AbortController().signal),
      ).rejects.toThrow();
    expect(posts[0].idempotency_key).toEqual(posts[1].idempotency_key);
  });
  it("does not send chunks or complete after stop", async () => {
    const u = await status(),
      controller = new AbortController();
    const fake = {
      request: vi.fn().mockResolvedValue(u),
      post: vi.fn(),
    } as unknown as Api;
    await sendZip(
      fake,
      file(),
      "upload-id",
      () => controller.abort(),
      controller.signal,
    );
    expect(fake.request).toHaveBeenCalledTimes(1);
    expect(fake.post).not.toHaveBeenCalled();
  });
  it("does not re-send completed/scanning upload", async () => {
    const u = await status();
    const fake = {
      request: vi.fn().mockResolvedValue({ ...u, state: "scanning" }),
      post: vi.fn(),
    } as unknown as Api;
    const result = await sendZip(
      fake,
      file(),
      "upload-id",
      () => {},
      new AbortController().signal,
    );
    expect(result?.state).toBe("scanning");
    expect(fake.request).toHaveBeenCalledTimes(1);
    expect(fake.post).not.toHaveBeenCalled();
  });
  it("rejects non ZIP before network", async () => {
    const request = vi.fn();
    await expect(
      sendZip(
        { request } as unknown as Api,
        new NodeFile(["abc"], "file.txt") as unknown as File,
        "",
        () => {},
        new AbortController().signal,
      ),
    ).rejects.toThrow("Chọn tệp ZIP");
    expect(request).not.toHaveBeenCalled();
  });
});
describe("server web sessions", () => {
  it("restores the session from an HttpOnly cookie without browser token storage", async () => {
    const data = {user:{id:"u",email:"test@example.com",platform_admin:false,email_verified:true},csrf:"csrf-value",workspace_id:"ws-a",workspaces:[{id:"ws-a",name:"A",role:"member"}],google_enabled:true};
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({data})));
    vi.stubGlobal("fetch",fetch);
    await expect(loadSession()).resolves.toEqual(data);
    expect(fetch.mock.calls[0][0]).toBe("/auth/web/session");
    expect(fetch.mock.calls[0][1].credentials).toBe("same-origin");
    expect(new Headers(fetch.mock.calls[0][1].headers).has("Authorization")).toBe(false);
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
  it("sends CSRF on JSON and binary API writes without granting MCP access", async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({data:{}}))));
    vi.stubGlobal("fetch",fetch);
    const api = new Api("csrf-value", workspace);
    await api.post("/projects", {name:"Project"});
    await api.request("/uploads/a/parts/0", {method:"PUT",body:new Blob(["zip"])});
    for (const [,init] of fetch.mock.calls) {
      const headers = new Headers(init.headers);
      expect(headers.get("X-CSRF-Token")).toBe("csrf-value");
      expect(headers.has("Authorization")).toBe(false);
    }
  });
  it("protects workspace mutations and global logout with the session CSRF", async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({data:{}}))));
    vi.stubGlobal("fetch",fetch);
    await webRequest("/select-workspace","csrf",{method:"POST",body:JSON.stringify({workspace_id:"ws-b"})});
    await revoke({csrf:"csrf"}, true);
    expect(fetch.mock.calls[1][0]).toBe("/auth/web/logout");
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({all_devices:true});
    for (const [,init] of fetch.mock.calls) expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf");
  });
  it("does not report logout success when the server rejects the request", async () => {
    vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response("{}",{status:403})));
    await expect(revoke({csrf:"invalid"})).rejects.toMatchObject({status:403});
  });
});
