import { sha256 } from "@noble/hashes/sha2.js";
import { Api } from "./api";
export type Upload = {
  id: string;
  bytes: number;
  sha256: string;
  part_size: number;
  expected_parts: number;
  received_parts: number[];
  state: string;
  plugin_version_id: string | null;
  preview: any;
  error_code: string | null;
};
export async function checksum(
  file: Blob,
  progress?: (fraction: number) => void,
) {
  const hash = sha256.create();
  for (let offset = 0; offset < file.size; offset += 8 * 1024 * 1024) {
    hash.update(
      new Uint8Array(
        await file.slice(offset, offset + 8 * 1024 * 1024).arrayBuffer(),
      ),
    );
    progress?.(Math.min(1, (offset + 8 * 1024 * 1024) / file.size));
  }
  return hash
    .digest()
    .reduce((s, b) => s + b.toString(16).padStart(2, "0"), "");
}
export async function sendZip(
  api: Api,
  file: File,
  resumeId: string,
  onStatus: (u: Upload) => void,
  signal: AbortSignal,
  onHash?: (n: number) => void,
  createKey?: string,
) {
  if (
    !file.name.toLowerCase().endsWith(".zip") ||
    !file.size ||
    file.size > 1024 ** 3
  )
    throw new Error("Chọn tệp ZIP từ 1 byte đến 1 GiB.");
  const hash = await checksum(file, onHash);
  if (signal.aborted) return;
  const u: Upload = resumeId
    ? await api.request(`/uploads/${encodeURIComponent(resumeId)}`)
    : await api.post("/uploads", {
        bytes: file.size,
        sha256: hash,
        idempotency_key: createKey || `zip-${hash}`,
      });
  if (u.bytes !== file.size || u.sha256 !== hash)
    throw new Error("Tệp không khớp lần tải trước. Chọn lại đúng tệp ZIP.");
  onStatus(u);
  if (u.state !== "uploading") return u;
  let current = u;
  for (let part = 0; part < u.expected_parts; part++) {
    if (signal.aborted) return current;
    if (u.received_parts.includes(part)) continue;
    const chunk = file.slice(
      part * u.part_size,
      Math.min(file.size, (part + 1) * u.part_size),
    );
    current = await api.request(`/uploads/${u.id}/parts/${part}`, {
      method: "PUT",
      body: chunk,
      headers: { "X-Content-SHA256": await checksum(chunk) },
      signal,
    });
    onStatus(current);
  }
  if (signal.aborted) return current;
  current = await api.post(`/uploads/${u.id}/complete`);
  onStatus(current);
  return current;
}
