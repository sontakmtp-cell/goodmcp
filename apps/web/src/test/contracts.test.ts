import { it, expect, vi, describe } from "vitest";
import { File as NodeFile } from "node:buffer";
import { Api, ApiError } from "../api";
import { checksum, sendZip, type Upload } from "../upload";
import { completeSignIn, revoke } from "../auth";
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
      ).toBe("Bearer private-test-token");
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
describe("OAuth callback", () => {
  it("does not report revoke success if backend still accepts access", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(new Response("{}"))
        .mockResolvedValueOnce(new Response("{}")),
    );
    await expect(
      revoke({ access_token: "fixture", client_id: "client", admin: true }),
    ).rejects.toThrow("chưa xác nhận thu hồi");
  });
  it("reports revoke success only after protected API returns 401", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(new Response("{}"))
        .mockResolvedValueOnce(new Response("{}", { status: 401 })),
    );
    await expect(
      revoke({ access_token: "fixture", client_id: "client", admin: true }),
    ).resolves.toBeUndefined();
  });
  it.each(["state", "issuer", "timeout", "denied"])(
    "rejects %s and clears pending verifier before token exchange",
    async (kind) => {
      const f = vi.fn();
      vi.stubGlobal("fetch", f);
      sessionStorage.setItem(
        "goodmcp:oauth",
        JSON.stringify({
          state: "s",
          verifier: "v",
          client_id: "id",
          created: kind === "timeout" ? 0 : Date.now(),
        }),
      );
      history.replaceState(
        null,
        "",
        "/oauth/callback?" +
          new URLSearchParams({
            state: kind === "state" ? "evil" : "s",
            iss:
              kind === "issuer"
                ? "https://evil.invalid"
                : "http://127.0.0.1:18080/auth",
            code: "one-time",
            ...(kind === "denied" ? { error: "access_denied" } : {}),
          }),
      );
      await expect(completeSignIn()).rejects.toThrow();
      expect(f).not.toHaveBeenCalled();
      expect(sessionStorage.getItem("goodmcp:oauth")).toBeNull();
      expect(location.search).toBe("");
    },
  );
  it("uses PKCE form and never persists returned tokens", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({
              access_token: "private-token",
              refresh_token: "private-refresh",
            }),
          ),
        ),
    );
    sessionStorage.setItem(
      "goodmcp:oauth",
      JSON.stringify({
        state: "s",
        verifier: "private-verifier",
        client_id: "id",
        redirect_uri: location.origin + "/oauth/callback",
        created: Date.now(),
        admin: true,
      }),
    );
    history.replaceState(
      null,
      "",
      "/oauth/callback?state=s&iss=http%3A%2F%2F127.0.0.1%3A18080%2Fauth&code=one-time",
    );
    const c = await completeSignIn();
    expect(c.access_token).toBe("private-token");
    expect(c.admin).toBe(true);
    expect(sessionStorage.length).toBe(0);
    expect(localStorage.length).toBe(0);
    const call = vi.mocked(fetch).mock.calls[0];
    expect((call[1]!.body as URLSearchParams).get("code_verifier")).toBe(
      "private-verifier",
    );
  });
});
