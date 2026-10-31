export type Workspace = { workspace_id: string; name: string; role: string };
export type Page<T> = { items: T[]; next_cursor: string | null };
export type Plugin = {
  installation_id: string;
  plugin_version_id: string;
  enabled: boolean;
  revision: number;
  name: string;
  manifest_version: string;
  preview: Record<string, any>;
};
export class ApiError extends Error {
  constructor(
    public status: number,
    public requestId = "",
  ) {
    super(messageFor(status));
  }
}
export function messageFor(status: number) {
  return (
    (
      {
        0: "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.",
        401: "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.",
        403: "Tài khoản chưa có quyền thực hiện thao tác này.",
        404: "Không tìm thấy dữ liệu hoặc chức năng chưa được hỗ trợ.",
        409: "Dữ liệu đã thay đổi hoặc vượt hạn mức nhập. Tải lại trạng thái trước khi thử tiếp.",
        413: "Tệp hoặc dữ liệu gửi quá lớn.",
        422: "Thông tin chưa hợp lệ. Kiểm tra các ô đã nhập.",
        429: "Đã đạt hạn mức. Chờ một lát rồi thử lại.",
      } as Record<number, string>
    )[status] || "Máy chủ đang gặp lỗi. Thử lại sau."
  );
}
export class Api {
  constructor(
    public token: string,
    public workspace: Workspace,
    private expired: () => void = () => {},
  ) {}
  async request<T = any>(
    path: string,
    init: RequestInit = {},
    scoped = true,
  ): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("Authorization", `Bearer ${this.token}`);
    if (typeof init.body === "string")
      headers.set("Content-Type", "application/json");
    let res: Response;
    try {
      res = await fetch(
        (scoped
          ? `/api/v1/workspaces/${encodeURIComponent(this.workspace.workspace_id)}`
          : "") + path,
        {
          ...init,
          headers,
          cache: "no-store",
          signal: init.signal || AbortSignal.timeout(30000),
        },
      );
    } catch {
      if (init.signal?.aborted)
        throw new Error(
          "Đã dừng gửi. Có thể tiếp tục lần tải từ trạng thái máy chủ.",
        );
      throw new ApiError(0);
    }
    if (!res.ok) {
      if (res.status === 401) this.expired();
      throw new ApiError(res.status, res.headers.get("x-request-id") || "");
    }
    return (await res.json()).data;
  }
  post<T = any>(path: string, data?: unknown) {
    return this.request<T>(path, {
      method: "POST",
      body: data === undefined ? undefined : JSON.stringify(data),
    });
  }
  async download(path: string, filename: string) {
    let res: Response;
    try {
      res = await fetch(
        `/api/v1/workspaces/${encodeURIComponent(this.workspace.workspace_id)}${path}`,
        {
          headers: { Authorization: `Bearer ${this.token}` },
          cache: "no-store",
          signal: AbortSignal.timeout(60000),
        },
      );
    } catch {
      throw new ApiError(0);
    }
    if (!res.ok) {
      if (res.status === 401) this.expired();
      throw new ApiError(res.status);
    }
    saveBlob(await res.blob(), filename);
  }
}
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const key = () => crypto.randomUUID();
