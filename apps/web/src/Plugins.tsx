import { useEffect, useRef, useState } from "react";
import { ArrowLeft, UploadSimple } from "@phosphor-icons/react";
import { Api, key, type Plugin, type Page } from "./api";
import { sendZip, type Upload } from "./upload";
import {
  DataState,
  useData,
  useAction,
  ConfirmButton,
  Plain,
  Status,
  empty,
} from "./ui";
import { SchemaForm } from "./SchemaForm";
const idPattern =
  "[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}";
export function UploadPanel({
  api,
  onInstalled,
}: {
  api: Api;
  onInstalled: () => void;
}) {
  const storageKey = "goodmcp:upload:" + api.workspace.workspace_id;
  const [resumeId, setResumeId] = useState(() => {
      try {
        return JSON.parse(localStorage.getItem(storageKey) || "{}").id || "";
      } catch {
        return "";
      }
    }),
    [file, setFile] = useState<File | null>(null),
    [upload, setUpload] = useState<Upload | null>(null),
    [hashing, setHashing] = useState(0),
    [attemptKey, setAttemptKey] = useState(() => {
      try {
        return (
          JSON.parse(localStorage.getItem(storageKey) || "{}").key || key()
        );
      } catch {
        return key();
      }
    });
  const action = useAction(),
    abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);
  const record = (u: Upload) => {
    setUpload(u);
    setResumeId(u.id);
    localStorage.setItem(
      storageKey,
      JSON.stringify({
        id: u.id,
        key: attemptKey,
        name: file?.name,
        bytes: u.bytes,
        sha256: u.sha256,
      }),
    );
  };
  const refresh = () =>
    action.run(async () => {
      if (!resumeId) return;
      record(await api.request(`/uploads/${encodeURIComponent(resumeId)}`));
    }, "Đã đọc trạng thái từ máy chủ.");
  const progress = upload
    ? Math.round((upload.received_parts.length / upload.expected_parts) * 100)
    : 0;
  return (
    <section className="panel upload-panel">
      <h2>
        <UploadSimple />
        Nhập plugin từ ZIP
      </h2>
      <p>Gói nguồn được giữ riêng tư. Kiểm tra nội dung trước khi bật.</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          action.run(async () => {
            if (!file) throw new Error("Chọn tệp ZIP để bắt đầu.");
            abort.current = new AbortController();
            localStorage.setItem(
              storageKey,
              JSON.stringify({ id: resumeId, key: attemptKey }),
            );
            await sendZip(
              api,
              file,
              resumeId,
              record,
              abort.current.signal,
              setHashing,
              attemptKey,
            );
          });
        }}
      >
        <label>
          Tệp ZIP (tối đa 1 GiB)
          <input
            type="file"
            accept=".zip,application/zip"
            disabled={action.busy}
            required
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </label>
        {resumeId && (
          <p className="hint">
            Có lần tải cần kiểm tra. Chọn lại cùng tệp để tiếp tục. Mã:{" "}
            <code>{resumeId}</code>
          </p>
        )}
        <div className="actions">
          <button className="primary" disabled={action.busy}>
            {resumeId ? "Tiếp tục tải ZIP" : "Tải lên & kiểm tra"}
          </button>
          {action.busy && (
            <button type="button" onClick={() => abort.current?.abort()}>
              Dừng gửi (giữ resume)
            </button>
          )}
          {resumeId && (
            <>
              <button type="button" disabled={action.busy} onClick={refresh}>
                Đọc trạng thái
              </button>
              <button
                type="button"
                disabled={action.busy}
                onClick={() => {
                  setResumeId("");
                  setUpload(null);
                  setAttemptKey(key());
                  localStorage.removeItem(storageKey);
                }}
              >
                Bắt đầu lần mới
              </button>
            </>
          )}
        </div>
      </form>
      {action.busy && !upload && (
        <p role="status">Đang kiểm tra tệp: {Math.round(hashing * 100)}%</p>
      )}
      {upload && (
        <>
          <div className="progress-label">
            <Status value={upload.state} />
            <span>{progress}% đã được máy chủ nhận</span>
          </div>
          <progress max={100} value={progress} aria-label="Tiến độ tải ZIP" />
          <p className="hint">
            Mã lần tải: <code>{upload.id}</code>
          </p>
          {upload.error_code && (
            <p role="alert">Gói chưa nhập được: {upload.error_code}</p>
          )}
          {upload.state === "ready" && upload.preview?.name && (
            <section aria-label="Kết quả kiểm tra gói">
              <h3>
                {upload.preview.name} · {upload.preview.manifest_version}
              </h3>
              <p>
                {upload.preview.files} tệp · {upload.preview.roles} vai trò ·
                Giấy phép {upload.preview.license}
              </p>
              <p>
                {upload.preview.python_files
                  ? `${upload.preview.python_files} tệp Python chỉ được lưu làm nguồn; cần runtime được duyệt trước khi chạy.`
                  : "Gói tài liệu, chưa có công cụ Python."}
              </p>
              {upload.preview.warning_count > 0 && (
                <p>
                  Có {upload.preview.warning_count} cảnh báo. Xem thông tin gói
                  trước khi bật.
                </p>
              )}
              <details>
                <summary>Thông tin kỹ thuật của gói</summary>
                <Plain value={upload.preview} />
              </details>
            </section>
          )}
          {upload.state === "ready" && upload.plugin_version_id && (
            <div className="install-preview">
              <p>
                Kiểm tra gói, giấy phép và công cụ chưa hỗ trợ trước khi bật.
                Máy chủ kiểm tra phiên bản hiện tại trước khi cập nhật.
              </p>
              <ConfirmButton
                disabled={action.busy}
                title="Bật phiên bản đã nhập?"
                detail="Phiên bản này sẽ phục vụ kết nối MCP trong vùng dữ liệu. Dự án đã ghim giữ nguyên phiên bản cũ."
                onConfirm={async () => {
                  let cursor: string | null = null;
                  let existing: Plugin | undefined;
                  do {
                    const page: Page<Plugin> = await api.request<Page<Plugin>>(
                      "/plugins?limit=100" +
                        (cursor ? "&cursor=" + encodeURIComponent(cursor) : ""),
                    );
                    existing = page.items.find(
                      (p) => p.name === upload.preview?.name,
                    );
                    cursor = existing ? null : page.next_cursor;
                  } while (cursor);
                  await api.request("/installation", {
                    method: "PUT",
                    body: JSON.stringify({
                      version_id: upload.plugin_version_id,
                      enabled: true,
                      expected_revision: existing?.revision || 0,
                    }),
                  });
                  onInstalled();
                }}
              >
                Bật phiên bản
              </ConfirmButton>
            </div>
          )}
          {["uploading", "queued"].includes(upload.state) && (
            <ConfirmButton
              title="Hủy lần nhập?"
              detail="Các phần đã nhận sẽ không dùng để tiếp tục lần nhập này."
              danger
              onConfirm={async () =>
                record(await api.post(`/uploads/${upload.id}/cancel`))
              }
            >
              Hủy lần nhập
            </ConfirmButton>
          )}
        </>
      )}
      {action.feedback}
      <p className="hint">
        Sau khi gửi đủ, nhấn “Đọc trạng thái” để xem kết quả quét. Không tự kích
        hoạt mã Python từ ZIP.
      </p>
    </section>
  );
}
export function PluginDetail({
  api,
  plugin,
  onBack,
}: {
  api: Api;
  plugin: Plugin;
  onBack: () => void;
}) {
  const [current, setCurrent] = useState(plugin),
    [tab, setTab] = useState("versions"),
    [cursor, setCursor] = useState("");
  const state = useData(
    () =>
      api.request<Page<any>>(
        `/installations/${plugin.installation_id}/versions?limit=20` +
          (cursor ? "&cursor=" + encodeURIComponent(cursor) : ""),
      ),
    [api, plugin.installation_id, cursor],
  );
  const action = useAction();
  const install = async (version_id: string, enabled: boolean) => {
    const updated = await api.request("/installation", {
      method: "PUT",
      body: JSON.stringify({
        version_id,
        enabled,
        expected_revision: current.revision,
      }),
    });
    setCurrent({
      ...current,
      plugin_version_id: updated.plugin_version_id,
      revision: updated.revision,
      enabled: updated.enabled,
    });
    state.reload();
  };
  return (
    <>
      <button onClick={onBack}>
        <ArrowLeft />
        Danh sách plugin
      </button>
      <section className="panel">
        <div className="section-toolbar">
          <div>
            <h2>{current.name}</h2>
            <p>
              Revision {current.revision} ·{" "}
              <span className="badge">
                {current.enabled ? "Đang bật" : "Đã tắt"}
              </span>
            </p>
          </div>
          <ConfirmButton
            title={current.enabled ? "Tắt plugin?" : "Bật plugin?"}
            detail="Thay đổi khả năng truy cập plugin qua kết nối AI. Phiên bản ghim của dự án không đổi."
            danger={current.enabled}
            onConfirm={() =>
              install(current.plugin_version_id, !current.enabled)
            }
          >
            {current.enabled ? "Tắt plugin" : "Bật plugin"}
          </ConfirmButton>
        </div>
        <p className="hint">
          Chỉ công cụ Python đã được duyệt mới chạy được. Bật plugin không đồng
          nghĩa cấp quyền chạy mã mới.
        </p>
        <nav className="detail-tabs" aria-label="Chi tiết plugin">
          {[
            ["versions", "Phiên bản"],
            ["documents", "Tài liệu"],
            ["tools", "Công cụ Python"],
          ].map(([k, label]) => (
            <button
              key={k}
              aria-pressed={tab === k}
              className={tab === k ? "selected" : ""}
              onClick={() => setTab(k)}
            >
              {label}
            </button>
          ))}
        </nav>
      </section>
      {tab === "versions" ? (
        <section className="panel">
          <h2>Phiên bản</h2>
          <p>
            Đang phục vụ: <code>{current.plugin_version_id}</code>
          </p>
          <DataState state={state}>
            {state.data?.items.map((v) => (
              <article className="version-row" key={v.id}>
                <div>
                  <h3>{v.manifest_version}</h3>
                  <p>
                    {v.project_pins} dự án ghim ·{" "}
                    {v.id === current.plugin_version_id
                      ? "Bản đang chọn"
                      : "Bản lưu"}
                  </p>
                  <details>
                    <summary>Thông tin kiểm tra</summary>
                    <code className="hash">SHA-256 {v.source_sha256}</code>
                  </details>
                </div>
                <div className="actions">
                  <button
                    disabled={action.busy}
                    onClick={() =>
                      action.run(
                        () =>
                          api.download(
                            `/versions/${v.id}/export`,
                            `${current.name}-${v.manifest_version}.zip`,
                          ),
                        "Đã tải ZIP nguồn.",
                      )
                    }
                  >
                    Tải ZIP gốc
                  </button>
                  {v.id !== current.plugin_version_id && (
                    <ConfirmButton
                      title="Chuyển phiên bản?"
                      detail="Kết nối MCP sẽ dùng bản đã chọn. Dự án đang có giữ bản ghim cũ. Runtime Python có thể chưa được duyệt cho bản này."
                      onConfirm={() => install(v.id, current.enabled)}
                    >
                      Dùng bản này
                    </ConfirmButton>
                  )}
                </div>
              </article>
            ))}
            {!state.data?.items.length && empty("Chưa có phiên bản.")}
            <div className="actions">
              {cursor && <button onClick={() => setCursor("")}>Về đầu</button>}
              {state.data?.next_cursor && (
                <button onClick={() => setCursor(state.data!.next_cursor!)}>
                  Trang tiếp
                </button>
              )}
            </div>
          </DataState>
          {action.feedback}
          <p className="hint">
            Nếu gặp xung đột revision, quay về danh sách và mở lại chi tiết
            trước khi đổi phiên bản.
          </p>
        </section>
      ) : !current.enabled ? (
        <section className="panel">
          Bật plugin trước khi đọc tài liệu hoặc dùng công cụ.
        </section>
      ) : tab === "documents" ? (
        <Documents api={api} installation={current.installation_id} />
      ) : (
        <Tools api={api} installation={current.installation_id} />
      )}
    </>
  );
}
function Documents({ api, installation }: { api: Api; installation: string }) {
  const [query, setQuery] = useState(""),
    [keywords, setKeywords] = useState(""),
    [cursor, setCursor] = useState(""),
    [document, setDocument] = useState<any>(null);
  const base = `/installations/${installation}/documents`;
  const state = useData(
    () =>
      keywords
        ? api.post<Page<any>>(base + "/search", {
            keywords: keywords
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean),
            match: "all",
            cursor: cursor || null,
            limit: 10,
          })
        : api.request<Page<any>>(
            base +
              "?limit=20" +
              (cursor ? "&cursor=" + encodeURIComponent(cursor) : ""),
          ),
    [api, installation, keywords, cursor],
  );
  const action = useAction();
  return (
    <section className="panel">
      <h2>Tài liệu</h2>
      <form
        className="search-form"
        onSubmit={(e) => {
          e.preventDefault();
          setKeywords(query);
          setCursor("");
          setDocument(null);
        }}
      >
        <label>
          Từ khóa (tối đa 5, ngăn bằng dấu phẩy)
          <input
            maxLength={504}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <button>Tìm từ khóa</button>
        <button
          type="button"
          onClick={() => {
            setQuery("");
            setKeywords("");
            setCursor("");
            setDocument(null);
          }}
        >
          Tất cả
        </button>
      </form>
      <DataState state={state}>
        {state.data?.items.length ? (
          <ul className="resource-list">
            {state.data.items.map((d) => (
              <li key={d.resource_id}>
                <button
                  disabled={action.busy}
                  onClick={() =>
                    action.run(async () =>
                      setDocument(
                        await api.request(base + "/" + d.resource_id),
                      ),
                    )
                  }
                >
                  {d.logical_path}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          empty(
            "Không có tài liệu phù hợp. PDF chưa trích chữ có thể chỉ giữ bản nguồn.",
          )
        )}
        <div className="actions">
          {cursor && <button onClick={() => setCursor("")}>Về đầu</button>}
          {state.data?.next_cursor && (
            <button onClick={() => setCursor(state.data!.next_cursor!)}>
              Trang tiếp
            </button>
          )}
        </div>
      </DataState>
      {document && (
        <>
          <h3>{document.logical_path}</h3>
          {document.unavailable_reason ? (
            <p>Chưa đọc được chữ: {document.unavailable_reason}</p>
          ) : (
            <Plain value={document.content} />
          )}
          <p className="hint">
            Nguồn SHA-256: <code>{document.source_sha256}</code>
          </p>
          {document.next_offset != null && (
            <button
              disabled={action.busy}
              onClick={() =>
                action.run(async () =>
                  setDocument(
                    await api.request(
                      base +
                        "/" +
                        document.resource_id +
                        "?offset=" +
                        document.next_offset,
                    ),
                  ),
                )
              }
            >
              Đọc tiếp
            </button>
          )}
        </>
      )}
      {action.feedback}
    </section>
  );
}
export function JobPanel({
  api,
  initialId = "",
}: {
  api: Api;
  initialId?: string;
}) {
  const [id, setId] = useState(initialId),
    [tracked, setTracked] = useState(initialId),
    [poll, setPoll] = useState(0);
  const state = useData(
    () =>
      tracked
        ? api.request<any>("/jobs/" + encodeURIComponent(tracked))
        : Promise.resolve(null),
    [api, tracked, poll],
  );
  useEffect(() => {
    if (
      !state.data ||
      !["queued", "running"].includes(state.data.state) ||
      document.hidden
    )
      return;
    const timer = setTimeout(() => setPoll((n) => n + 1), 2500);
    return () => clearTimeout(timer);
  }, [state.data]);
  return (
    <section className="panel">
      <h2>Công việc Python</h2>
      <form
        className="search-form"
        onSubmit={(e) => {
          e.preventDefault();
          setTracked(id);
          setPoll((n) => n + 1);
        }}
      >
        <label>
          Mã công việc
          <input
            required
            pattern={idPattern}
            value={id}
            onChange={(e) => setId(e.target.value)}
          />
        </label>
        <button>Theo dõi</button>
      </form>
      {!tracked ? (
        <p className="hint">
          Dán mã công việc đã nhận. Backend chưa có API liệt kê toàn bộ job.
        </p>
      ) : (
        <DataState state={state}>
          {state.data && (
            <>
              <p>
                <Status value={state.data.state} />
              </p>
              <p>
                Mã: <code>{state.data.id}</code>
              </p>
              {state.data.cancel_requested && (
                <p>Đã yêu cầu hủy; đang đợi công cụ dừng.</p>
              )}
              {state.data.error && (
                <p role="alert">
                  Công việc thất bại:{" "}
                  {state.data.error.code === "runtime_unavailable"
                    ? "Môi trường Python chưa sẵn sàng. Quản trị viên cần kiểm tra runtime."
                    : state.data.error.code === "timeout"
                      ? "Công cụ đã chạy quá thời gian cho phép."
                      : state.data.error.code}
                </p>
              )}
              {state.data.state === "succeeded" && (
                <>
                  <h3>Kết quả từ máy chủ</h3>
                  <Plain value={state.data.result} />
                </>
              )}
              {["queued", "running"].includes(state.data.state) && (
                <ConfirmButton
                  title="Hủy công việc?"
                  detail="Gửi yêu cầu dừng. Công việc đang chạy chỉ chuyển sang đã hủy khi tiến trình thật đã dừng."
                  danger
                  onConfirm={async () => {
                    await api.post(`/jobs/${tracked}/cancel`);
                    state.reload();
                  }}
                >
                  Hủy công việc
                </ConfirmButton>
              )}
            </>
          )}
        </DataState>
      )}
    </section>
  );
}
function Tools({ api, installation }: { api: Api; installation: string }) {
  const toolNames: Record<string, string> = {
    finance_cit_estimate: "Thuế thu nhập doanh nghiệp",
    finance_cit_schedule: "Lịch ưu đãi thuế doanh nghiệp",
    finance_payroll_total: "Chi phí lương và thuế cá nhân",
    finance_fct_withhold: "Khấu trừ thuế nhà thầu",
    finance_fct_grossup: "Quy đổi tiền thực nhận trước thuế",
    finance_tariff: "Thuế nhập khẩu tham khảo",
    finance_location_sim: "So sánh chi phí địa điểm",
    finance_refs_calendar: "Lịch tuân thủ",
    finance_refs_odi: "Danh mục đầu tư ra nước ngoài",
  };
  const state = useData(
    () => api.request<any[]>(`/installations/${installation}/bindings`),
    [api, installation],
  );
  const [binding, setBinding] = useState(""),
    [job, setJob] = useState("");
  const action = useAction();
  const stable = useRef<{ payload: string; key: string } | null>(null);
  const selected = state.data?.find((b) => b.id === binding);
  return (
    <>
      <section className="panel">
        <h2>Công cụ Python đã duyệt</h2>
        <DataState state={state}>
          {state.data?.length ? (
            <>
              <label>
                Chọn công cụ
                <select
                  aria-label="Chọn công cụ"
                  value={binding}
                  onChange={(e) => {
                    setBinding(e.target.value);
                    setJob("");
                  }}
                >
                  <option value="">Chọn công cụ…</option>
                  {state.data.map((b) => (
                    <option key={b.id} value={b.id}>
                      {toolNames[b.mcp_name] || b.mcp_name}
                    </option>
                  ))}
                </select>
              </label>
              {selected && (
                <SchemaForm
                  key={selected.id}
                  schema={selected.input_schema}
                  busy={action.busy}
                  onSubmit={(arguments_) =>
                    action.run(async () => {
                      const payload = JSON.stringify({
                        binding_id: selected.id,
                        arguments: arguments_,
                      });
                      if (stable.current?.payload !== payload)
                        stable.current = { payload, key: key() };
                      const j = await api.post("/invocations", {
                        binding_id: selected.id,
                        arguments: arguments_,
                        idempotency_key: stable.current!.key,
                      });
                      setJob(j.id);
                    }, "Đã gửi công việc tới máy chủ.")
                  }
                />
              )}
            </>
          ) : (
            empty(
              "Phiên bản này chưa có công cụ Python được duyệt. Không thể tự chạy script từ ZIP.",
            )
          )}
        </DataState>
        {action.feedback}
      </section>
      {job && <JobPanel key={job} api={api} initialId={job} />}
    </>
  );
}
