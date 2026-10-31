import { useState, useEffect } from "react";
import {
  Graph,
  SquaresFour,
  Plugs,
  FolderOpen,
  Users,
  Gear,
  ArrowLeft,
  UploadSimple,
  ArrowRight,
} from "@phosphor-icons/react";
import { Api, key, saveBlob, type Page, type Plugin } from "./api";
import { revoke, type Credential } from "./auth";
import {
  useAction,
  useData,
  DataState,
  ConfirmButton,
  Plain,
  Status,
  empty,
} from "./ui";
import { PluginDetail, UploadPanel, JobPanel } from "./Plugins";
import { description } from "./App";
const menus = [
  { label: "Tổng quan", icon: SquaresFour },
  { label: "MCP & Plugin", icon: Plugs },
  { label: "Dự án", icon: FolderOpen },
  { label: "Người dùng & Kết nối", icon: Users },
  { label: "Hệ thống", icon: Gear },
];
export function Admin({
  api,
  credential,
  onLogin,
  onForget,
  onPortal,
}: {
  api: Api | null;
  credential: Credential | null;
  onLogin: () => void;
  onForget: () => void;
  onPortal: () => void;
}) {
  const [menu, setMenu] = useState(0);
  if (!api)
    return (
      <div className="admin-login">
        <a className="brand" href="/">
          <Graph size={30} />
          GoodMCP
        </a>
        <main id="main">
          <h1>Quản trị GoodMCP</h1>
          <p>
            Đăng nhập bằng tài khoản được cấp để quản lý vùng dữ liệu của bạn.
          </p>
          <button className="primary" onClick={onLogin}>
            Đăng nhập
          </button>
          <button onClick={onPortal}>Về trang chủ</button>
        </main>
      </div>
    );
  if (!["owner", "admin"].includes(api.workspace.role))
    return (
      <main id="main" className="admin-login">
        <h1>Chưa có quyền quản trị</h1>
        <p>Khu vực này dành cho chủ sở hữu và quản trị viên.</p>
        <button onClick={onPortal}>Về cổng người dùng</button>
      </main>
    );
  return (
    <div className="admin-shell">
      <aside className="sidebar">
        <a className="brand" href="/">
          <Graph size={30} weight="duotone" />
          GoodMCP
        </a>
        <p className="sidebar-label">KHÔNG GIAN QUẢN TRỊ</p>
        <nav aria-label="Quản trị">
          {menus.map((m, i) => (
            <button
              key={m.label}
              aria-current={menu === i ? "page" : undefined}
              className={menu === i ? "active" : ""}
              onClick={() => setMenu(i)}
            >
              <m.icon size={21} />
              {m.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <Shield />
          <button onClick={onPortal}>
            <ArrowLeft />
            Cổng người dùng
          </button>
        </div>
      </aside>
      <div className="admin-body">
        <header className="admin-top">
          <span>{api.workspace.name}</span>
          <span className="badge">
            {api.workspace.role === "owner" ? "Chủ sở hữu" : "Quản trị viên"}
          </span>
        </header>
        <main id="main" key={menu} className="admin-main">
          <p className="eyebrow">GOODMCP / QUẢN TRỊ</p>
          <h1>{menus[menu].label}</h1>
          {menu === 0 ? (
            <>
              <p className="intro">
                Mọi công cụ và dự án, trong một không gian riêng.
              </p>
              <div className="quick-grid">
                <button className="quick-card" onClick={() => setMenu(1)}>
                  <UploadSimple size={28} />
                  <strong>Thêm MCP & Plugin</strong>
                  <span>Tải ZIP, xem trước và bật phiên bản.</span>
                  <ArrowRight />
                </button>
                <button className="quick-card" onClick={() => setMenu(2)}>
                  <FolderOpen size={28} />
                  <strong>Tiếp tục dự án</strong>
                  <span>Mở lại tài liệu và bước đang làm.</span>
                  <ArrowRight />
                </button>
              </div>
              <section className="panel">
                <h2>Workspace đang kết nối</h2>
                <p>
                  Thao tác sử dụng API và quyền đã cấp cho vùng dữ liệu này.
                </p>
                <p className="hint">
                  Mỗi kết nối AI cần được cấp quyền riêng trước khi đọc tài liệu,
                  chạy công cụ hoặc làm việc với dự án.
                </p>
              </section>
            </>
          ) : menu === 1 ? (
            <PluginList api={api} />
          ) : menu === 2 ? (
            <Projects api={api} />
          ) : menu === 3 ? (
            <section className="panel">
              <h2>Phiên web của bạn</h2>
              <p>
                Đã xác thực · {api.workspace.name} · {api.workspace.role}
              </p>
              <p>
                Máy chủ chưa có API liệt kê người dùng và toàn bộ kết nối AI.
              </p>
              {credential && (
                <ConfirmButton
                  title="Thu hồi phiên web?"
                  detail="Ngừng quyền API của phiên web này. Các kết nối AI khác và cookie đăng nhập không bị thu hồi."
                  danger
                  onConfirm={async () => {
                    await revoke(credential);
                    onForget();
                  }}
                >
                  Thu hồi phiên web
                </ConfirmButton>
              )}
              <p>
                <a href="/auth/account">Quản lý tài khoản / đăng xuất</a>
              </p>
            </section>
          ) : (
            <System api={api} />
          )}
        </main>
      </div>
    </div>
  );
}
function Shield() {
  return (
    <p className="private-note">
      Vùng dữ liệu riêng tư
      <br />
      <small>Không có đăng ký công khai</small>
    </p>
  );
}
function PluginList({ api }: { api: Api }) {
  const [cursor, setCursor] = useState(""),
    [page, setPage] = useState(1),
    [selected, setSelected] = useState<Plugin | null>(null),
    [upload, setUpload] = useState(false);
  const state = useData(
    () =>
      api.request<Page<Plugin>>(
        "/plugins?limit=20" +
          (cursor ? "&cursor=" + encodeURIComponent(cursor) : ""),
      ),
    [api, cursor],
  );
  if (selected)
    return (
      <PluginDetail
        key={selected.installation_id}
        api={api}
        plugin={selected}
        onBack={() => {
          setSelected(null);
          state.reload();
        }}
      />
    );
  return (
    <>
      <div className="section-toolbar">
        <p className="intro">
          Thêm kỹ năng, tài liệu và công cụ cho AI của bạn.
        </p>
        <button
          className="primary"
          aria-expanded={upload}
          onClick={() => setUpload(!upload)}
        >
          <UploadSimple />
          Tải ZIP
        </button>
      </div>
      {upload && <UploadPanel api={api} onInstalled={state.reload} />}
      <DataState state={state}>
        {state.data?.items.length ? (
          <div className="list">
            {state.data.items.map((p) => (
              <article className="list-item" key={p.installation_id}>
                <div className="item-icon">
                  <Plugs size={25} />
                </div>
                <div className="item-content">
                  <h2>{p.name}</h2>
                  <p>{description(p)}</p>
                  <small>Phiên bản {p.manifest_version} · Riêng tư</small>
                </div>
                <span className="badge">
                  {p.enabled ? "Đang bật" : "Đã tắt"}
                </span>
                <button onClick={() => setSelected(p)}>
                  Chi tiết <ArrowRight />
                </button>
              </article>
            ))}
          </div>
        ) : (
          empty("Chưa có plugin được cài. Tải ZIP để bắt đầu.")
        )}
        <div className="actions">
          <button onClick={state.reload}>Tải lại</button>
          <span className="pagination-info" aria-live="polite">
            Trang {page}
          </span>
          {cursor && (
            <button
              onClick={() => {
                setCursor("");
                setPage(1);
              }}
            >
              Về đầu
            </button>
          )}
          {state.data?.next_cursor && (
            <button
              onClick={() => {
                setCursor(state.data!.next_cursor!);
                setPage((p) => p + 1);
              }}
            >
              Trang tiếp
            </button>
          )}
        </div>
      </DataState>
    </>
  );
}
function System({ api }: { api: Api }) {
  const action = useAction(),
    [health, setHealth] = useState("Chưa kiểm tra");
  return (
    <>
      <section className="panel">
        <h2>Trạng thái dịch vụ</h2>
        <p role="status">{health}</p>
        <button
          disabled={action.busy}
          onClick={() =>
            action.run(async () => {
              setHealth("Đang kiểm tra…");
              let r;
              try {
                r = await fetch("/health/ready", {
                  cache: "no-store",
                  signal: AbortSignal.timeout(10000),
                });
              } catch {
                setHealth("Không kết nối được");
                throw new Error("Không kết nối được máy chủ.");
              }
              if (!r.ok) {
                setHealth("Chưa sẵn sàng");
                throw new Error("Dịch vụ chưa sẵn sàng.");
              }
              const body = await r.json();
              if (body.data?.status !== "ready") {
                setHealth("Chưa xác định");
                throw new Error("Chưa nhận được trạng thái hợp lệ.");
              }
              setHealth("API và cơ sở dữ liệu sẵn sàng.");
            })
          }
        >
          Kiểm tra lại
        </button>
        {action.feedback}
      </section>
      <JobPanel api={api} />
      <section className="panel">
        <h2>Nhật ký, tài nguyên & sao lưu</h2>
        <p>
          Chưa hỗ trợ: backend chưa cung cấp API xem logs, CPU/RAM/đĩa hoặc chạy
          và kiểm tra backup.
        </p>
        <p className="hint">
          Quản trị viên theo dõi nhật ký và sao lưu trên máy chủ. Các chức năng
          này chưa có điều khiển trong giao diện.
        </p>
      </section>
    </>
  );
}
function Projects({ api }: { api: Api }) {
  const [cursor, setCursor] = useState(""),
    [page, setPage] = useState(1),
    [selected, setSelected] = useState(""),
    [create, setCreate] = useState(false),
    [name, setName] = useState(""),
    [installation, setInstallation] = useState(""),
    [createKey, setCreateKey] = useState(key);
  const state = useData(
    () =>
      api.request<Page<any>>(
        "/projects?limit=20" +
          (cursor ? "&cursor=" + encodeURIComponent(cursor) : ""),
      ),
    [api, cursor],
  );
  const plugins = useData(
    () => api.request<Page<Plugin>>("/plugins?limit=100"),
    [api],
  );
  const action = useAction();
  if (selected)
    return (
      <ProjectDetail
        api={api}
        id={selected}
        onBack={() => {
          setSelected("");
          state.reload();
        }}
      />
    );
  return (
    <>
      <div className="section-toolbar">
        <p className="intro">
          Tiếp tục công việc từ đúng phiên bản và tài liệu đã lưu.
        </p>
        <button
          className="primary"
          onClick={() => setCreate(!create)}
          aria-expanded={create}
        >
          Tạo dự án
        </button>
      </div>
      {create && (
        <section className="panel">
          <h2>Dự án mới</h2>
          <DataState state={plugins}>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                action.run(async () => {
                  const p = await api.post("/projects", {
                    installation_id: installation,
                    name,
                    idempotency_key: createKey,
                    timezone: "Asia/Saigon",
                  });
                  setSelected(p.id);
                });
              }}
            >
              <label>
                Tên dự án
                <input
                  required
                  maxLength={200}
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    setCreateKey(key());
                  }}
                />
              </label>
              <label>
                Plugin đang bật
                <select
                  required
                  value={installation}
                  onChange={(e) => {
                    setInstallation(e.target.value);
                    setCreateKey(key());
                  }}
                >
                  <option value="">Chọn plugin…</option>
                  {plugins.data?.items
                    .filter((x) => x.enabled)
                    .map((p) => (
                      <option key={p.installation_id} value={p.installation_id}>
                        {p.name}
                      </option>
                    ))}
                </select>
              </label>
              <button className="primary" disabled={action.busy}>
                Tạo dự án
              </button>
            </form>
            {plugins.data?.next_cursor && (
              <p className="hint">
                Chỉ hiển thị 100 plugin đầu. Chọn từ danh mục đầy đủ qua MCP nếu
                vượt số này.
              </p>
            )}
          </DataState>
          {action.feedback}
        </section>
      )}
      <DataState state={state}>
        {state.data?.items.length ? (
          <div className="list">
            {state.data.items.map((p) => (
              <article className="list-item" key={p.id}>
                <FolderOpen size={28} />
                <div className="item-content">
                  <h2>{p.name}</h2>
                  <p>Revision {p.revision}</p>
                </div>
                <button onClick={() => setSelected(p.id)}>Mở dự án</button>
              </article>
            ))}
          </div>
        ) : (
          empty("Chưa có dự án. Tạo dự án từ một plugin đang bật.")
        )}
        <div className="actions">
          <button onClick={state.reload}>Tải lại</button>
          <span className="pagination-info" aria-live="polite">
            Trang {page}
          </span>
          {cursor && (
            <button
              onClick={() => {
                setCursor("");
                setPage(1);
              }}
            >
              Về đầu
            </button>
          )}
          {state.data?.next_cursor && (
            <button
              onClick={() => {
                setCursor(state.data!.next_cursor!);
                setPage((p) => p + 1);
              }}
            >
              Trang tiếp
            </button>
          )}
        </div>
      </DataState>
    </>
  );
}
function ProjectDetail({
  api,
  id,
  onBack,
}: {
  api: Api;
  id: string;
  onBack: () => void;
}) {
  const [cursor, setCursor] = useState(""),
    [file, setFile] = useState<any>(null),
    [path, setPath] = useState("opc-doc/outputs/note.md"),
    [content, setContent] = useState(""),
    [writeKey, setWriteKey] = useState(key);
  const state = useData(
    () =>
      api.request<any>(
        `/projects/${id}` +
          (cursor ? "?cursor=" + encodeURIComponent(cursor) : ""),
      ),
    [api, id, cursor],
  );
  useEffect(() => {
    const stage = state.data?.resume_stage;
    if (!stage || path !== "opc-doc/outputs/note.md") return;
    const directory = stage === "execution" ? "05-mvp-design" : stage;
    const stamp = new Intl.DateTimeFormat("sv-SE", {
      timeZone: "Asia/Saigon",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    })
      .format(new Date())
      .replaceAll("-", "")
      .replaceAll(":", "")
      .replace(" ", "-");
    setPath(`opc-doc/outputs/${directory}/note-${stamp}.md`);
  }, [state.data, path]);
  const action = useAction();
  return (
    <>
      <button onClick={onBack}>
        <ArrowLeft />
        Danh sách dự án
      </button>
      <DataState state={state}>
        {state.data && (
          <>
            <section className="panel">
              <h2>{state.data.name}</h2>
              <p>Revision {state.data.revision}</p>
              <p>
                Phiên bản ghim: <code>{state.data.plugin_version_id}</code>
              </p>
              <p>
                Bước tiếp tục:{" "}
                {state.data.resume_stage ||
                  "Dự án tài liệu — chưa có workflow OPC"}
              </p>
              <p className="hint">
                Đổi phiên bản plugin không thay đổi bản ghim của dự án này.
              </p>
              <button onClick={state.reload}>Tải lại trạng thái</button>
            </section>
            <section className="panel">
              <h2>Tài liệu đã lưu</h2>
              {state.data.files?.length ? (
                <ul className="resource-list">
                  {state.data.files.map((f: any) => (
                    <li key={f.id}>
                      <button
                        disabled={action.busy}
                        onClick={() =>
                          action.run(async () =>
                            setFile(
                              await api.request(
                                `/projects/${id}/files/${f.id}`,
                              ),
                            ),
                          )
                        }
                      >
                        {f.logical_path}
                      </button>
                      <Status value={f.status} />
                    </li>
                  ))}
                </ul>
              ) : (
                empty("Chưa có tài liệu.")
              )}
              <div className="actions">
                {cursor && (
                  <button onClick={() => setCursor("")}>Về đầu</button>
                )}
                {state.data.next_cursor && (
                  <button onClick={() => setCursor(state.data.next_cursor)}>
                    Trang tiếp
                  </button>
                )}
              </div>
              {file && (
                <>
                  <h3>{file.logical_path}</h3>
                  <Plain value={file.content} />
                  <div className="actions">
                    <button
                      onClick={() =>
                        saveBlob(
                          new Blob([file.content], { type: "text/plain" }),
                          "project-page.txt",
                        )
                      }
                    >
                      Tải trang đang đọc
                    </button>
                    {file.next_offset != null && (
                      <button
                        disabled={action.busy}
                        onClick={() =>
                          action.run(async () =>
                            setFile(
                              await api.request(
                                `/projects/${id}/files/${file.file_id || file.id}?offset=${file.next_offset}`,
                              ),
                            ),
                          )
                        }
                      >
                        Đọc tiếp
                      </button>
                    )}
                  </div>
                  <p className="hint">
                    Tải từng trang nội dung; backend chưa hỗ trợ export toàn bộ
                    dự án.
                  </p>
                </>
              )}
            </section>
            <section className="panel">
              <h2>Lưu bản nháp</h2>
              <p>Chỉ lưu tài liệu, không xác nhận hoàn thành bước.</p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  action.run(async () => {
                    await api.post(`/projects/${id}/artifacts`, {
                      logical_path: path,
                      content,
                      media_type: "text/markdown",
                      expected_revision: state.data.revision,
                      idempotency_key: writeKey,
                    });
                    setWriteKey(key());
                    state.reload();
                  }, "Đã lưu bản nháp.");
                }}
              >
                <label>
                  Tên tài liệu trong dự án
                  <input
                    required
                    pattern="opc-doc/.*"
                    maxLength={240}
                    value={path}
                    onChange={(e) => {
                      setPath(e.target.value);
                      setWriteKey(key());
                    }}
                  />
                </label>
                <label>
                  Nội dung
                  <textarea
                    rows={6}
                    required
                    maxLength={262144}
                    value={content}
                    onChange={(e) => {
                      setContent(e.target.value);
                      setWriteKey(key());
                    }}
                  />
                </label>
                <button className="primary" disabled={action.busy}>
                  Lưu bản nháp
                </button>
              </form>
            </section>
          </>
        )}
      </DataState>
      {action.feedback}
    </>
  );
}
