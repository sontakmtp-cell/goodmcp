import { useEffect, useState, useMemo } from "react";
import {
  Graph,
  Copy,
  ArrowRight,
  BookOpen,
  ShieldCheck,
  Plugs,
  ArrowUpRight,
} from "@phosphor-icons/react";
import { Api, ApiError, type Plugin, type Page } from "./api";
import { signIn, loadSession, type WebSession, type Credential } from "./auth";
import { WorkspaceBar, Account, Members, Connections, Audit, Invitation, Platform, WorkspaceSettings } from "./Workspace";
import { Sharks } from "./Sharks";
import { Admin, PluginList, Projects } from "./Admin";
import {
  Notice,
  useAction,
  useData,
  DataState,
  empty,
} from "./ui";
const platforms = ["ChatGPT", "Claude", "Gemini", "Grok", "CLI"];
const mcpUrl =
  import.meta.env.VITE_MCP_URL || "https://mcp.example.invalid/mcp";
const placeholder =
  !import.meta.env.VITE_MCP_URL || mcpUrl.includes(".invalid");
export function description(plugin: Plugin) {
  const n = plugin.name.toLowerCase();
  return (
    plugin.preview?.manifest?.description ||
    (n.includes("opc")
      ? "Hỗ trợ lập kế hoạch kinh doanh, lưu quyết định và tiếp tục công việc."
      : n.includes("godot") || n.includes("roblox")
        ? "Hồ sơ chuyên gia và tài liệu làm game. Không chạy game engine."
        : n.includes("finance") || n.includes("tax")
          ? "Tra cứu tài liệu và gọi công cụ Python tài chính, thuế đã được duyệt."
          : "Kỹ năng và tài liệu riêng trong vùng dữ liệu của bạn.")
  );
}
export function Catalog({
  api,
  canAdmin,
  onAdmin,
}: {
  api: Api;
  canAdmin: boolean;
  onAdmin: () => void;
}) {
  const [cursor, setCursor] = useState(""),
    [page, setPage] = useState(1);
  const state = useData(
    () =>
      api.request<Page<Plugin>>(
        "/plugins?limit=12" +
          (cursor ? "&cursor=" + encodeURIComponent(cursor) : ""),
      ),
    [api, cursor],
  );
  const plugins = state.data?.items.filter((x) => x.enabled) || [];
  return (
    <DataState state={state}>
      {plugins.length ? (
        <div className="plugin-grid">
          {plugins.map((p) => (
            <article className="plugin-card" key={p.installation_id}>
              <Plugs size={28} weight="duotone" />
              <span className="badge">Riêng tư</span>
              <h3>{p.name}</h3>
              <p>{description(p)}</p>
              <small>Phiên bản {p.manifest_version}</small>
            </article>
          ))}
        </div>
      ) : (
        <>
          {empty(
            "Chưa có plugin đang bật trên trang này. Quản trị viên có thể nhập và bật plugin.",
          )}
          {canAdmin && (
            <div className="actions">
              <button className="primary" onClick={onAdmin}>
                Mở trang quản trị <ArrowRight />
              </button>
            </div>
          )}
        </>
      )}
      <div className="actions">
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
  );
}
export function Portal({
  api,
  onLogin,
  onAdmin,
}: {
  api: Api | null;
  credential: Credential | null;
  onLogin: () => void;
  onForget: () => void;
  onAdmin: () => void;
}) {
  const [platform, setPlatform] = useState("ChatGPT"),
    [guide, setGuide] = useState(false);
  const copy = useAction();
  return (
    <div className="portal">
      <Sharks />
      <section className="hero">
        <header className="portal-header">
          <a className="brand" href="/" aria-label="GoodMCP trang chủ">
            <Graph weight="duotone" size={30} />
            GoodMCP
          </a>
          <nav aria-label="Điều hướng người dùng">
            <a href="#plugins">Plugin</a>
            <a href="#connection" onClick={() => setGuide(true)}>
              Hướng dẫn
            </a>
            {api && ["owner", "admin"].includes(api.workspace.role) && (
              <button onClick={onAdmin}>
                Quản trị <ArrowUpRight />
              </button>
            )}
            {api ? (
              <a href="#account">Tài khoản</a>
            ) : (
              <button onClick={onLogin}>
                Đăng nhập <ArrowRight />
              </button>
            )}
          </nav>
        </header>
        <main id="main">
          <div className="hero-content">
            <p className="eyebrow">Kết nối AI · Mở rộng khả năng</p>
            <h1>
              Kết nối AI của bạn
              <br />
              với <span>GoodMCP</span>
            </h1>
            <p className="hero-description">
              Công cụ và tài liệu của bạn, ngay trong cuộc chat.
              <br />
              Kết nối một lần. Tiếp tục công việc dễ dàng hơn.
            </p>
            <section
              className="connect-card"
              id="connection"
              aria-label="Kết nối AI"
            >
              <h2>1. Chọn AI của bạn</h2>
              <div className="platforms">
                {platforms.map((p) => (
                  <button
                    key={p}
                    aria-pressed={platform === p}
                    className={platform === p ? "selected" : ""}
                    onClick={() => {
                      setPlatform(p);
                      setGuide(true);
                    }}
                  >
                    {p}
                  </button>
                ))}
              </div>
              <h2>2. Sao chép đường dẫn MCP</h2>
              <div className="url-row">
                <label className="sr-only" htmlFor="mcp-url">
                  Đường dẫn MCP
                </label>
                <input id="mcp-url" readOnly value={mcpUrl} />
                <div className="copy-btn-wrapper">
                  <div className="line horizontal top" aria-hidden="true" />
                  <div className="line vertical right" aria-hidden="true" />
                  <div className="line horizontal bottom" aria-hidden="true" />
                  <div className="line vertical left" aria-hidden="true" />

                  <div className="dot top left" aria-hidden="true" />
                  <div className="dot top right" aria-hidden="true" />
                  <div className="dot bottom right" aria-hidden="true" />
                  <div className="dot bottom left" aria-hidden="true" />

                  <button
                    className="copy-btn"
                    onClick={() =>
                      copy.run(async () => {
                        if (!navigator.clipboard)
                          throw new Error(
                            "Trình duyệt không cho sao chép. Hãy chọn và sao chép đường dẫn thủ công.",
                          );
                        try {
                          await navigator.clipboard.writeText(mcpUrl);
                        } catch {
                          throw new Error(
                            "Không sao chép được. Hãy chọn và sao chép đường dẫn thủ công.",
                          );
                        }
                      }, "Đã sao chép đường dẫn.")
                    }
                  >
                    <Copy />
                    Sao chép
                  </button>
                </div>
              </div>
              <p className="url-hint">
                {placeholder
                  ? "URL mẫu — chưa triển khai. Chưa dùng để kết nối thật."
                  : "Đường dẫn do quản trị viên cấu hình; cần kiểm tra khả năng của nền tảng AI."}
              </p>
              {copy.feedback}
              <button
                className="guide-button"
                aria-expanded={guide}
                onClick={() => setGuide(!guide)}
              >
                <BookOpen />
                {guide
                  ? `Đóng hướng dẫn ${platform}`
                  : `Hướng dẫn kết nối ${platform}`}
              </button>
              {guide && (
                <div className="guide">
                  <h3>Kết nối với {platform}</h3>
                  <ol>
                    <li>
                      {platform === "CLI"
                        ? "Chọn một ứng dụng dòng lệnh có hỗ trợ MCP qua HTTP và OAuth."
                        : `Mở phần cài đặt kết nối/công cụ trong ${platform}. Tìm tùy chọn thêm máy chủ MCP từ xa nếu tài khoản có hỗ trợ.`}
                    </li>
                    <li>
                      Điền URL MCP thật do quản trị viên cung cấp. Đường dẫn mẫu
                      ở trên chưa hoạt động; AI cloud không truy cập được máy
                      chủ localhost.
                    </li>
                    <li>
                      Đăng nhập GoodMCP, kiểm tra ứng dụng và vùng dữ liệu, rồi
                      cấp các quyền cần thiết. Quay lại AI để kiểm tra danh sách
                      công cụ.
                    </li>
                  </ol>
                  <p className="hint">
                    Tên menu tùy phiên bản và gói tài khoản. Chưa nghiệm thu kết
                    nối {platform}; lựa chọn này không xác nhận đã kết nối.
                  </p>
                  <a href="/auth/account">Mở tài khoản GoodMCP</a>
                </div>
              )}
            </section>
          </div>
          <section className="catalog-section" id="plugins">
            <p className="eyebrow">Không gian công cụ của bạn</p>
            <h2>
              Thêm khả năng.
              <br className="mobile-break" /> Bớt thao tác.
            </h2>
            <p>Giữ tài liệu, kỹ năng và tiến độ trong cùng một nơi.</p>
            {api ? (
              <Catalog
                api={api}
                canAdmin={["owner", "admin"].includes(api.workspace.role)}
                onAdmin={onAdmin}
              />
            ) : (
              <div className="public-info">
                <ShieldCheck size={30} />
                <h3>Plugin của bạn luôn riêng tư</h3>
                <p>
                  Đăng nhập để xem những plugin được cấp cho vùng dữ liệu của
                  bạn.
                </p>
                <button className="primary" onClick={onLogin}>
                  Đăng nhập để xem <ArrowRight />
                </button>
              </div>
            )}
          </section>
          {api && (
            <section id="account" className="account-section">
              <h2>Tài khoản & kết nối</h2>
              <p>Đã xác thực phiên web · {api.workspace.name}</p>
              <p>Quản lý tài khoản, workspace và các kết nối AI trong khu làm việc.</p>
              <a href="/app/account">Mở tài khoản</a>
            </section>
          )}
        </main>
      </section>
    </div>
  );
}
export function App() {
  const [session, setSession] = useState<WebSession | null>(null),
    [path, setPath] = useState(location.pathname),
    [authBusy, setAuthBusy] = useState(true),
    [authError, setAuthError] = useState<unknown>(null);
  const forget = () => { setSession(null); };
  const navigate = (next: string) => { history.pushState(null, "", next); setPath(next); };
  const reload = async () => {
    try { setSession(await loadSession()); }
    catch (error) { if (error instanceof ApiError && error.status === 401) { forget(); return; } throw error; }
  };
  useEffect(() => {
    const pop = () => setPath(location.pathname);
    window.addEventListener("popstate", pop);
    return () => window.removeEventListener("popstate", pop);
  }, []);
  useEffect(() => {
    // Work areas use dark text; keep their canvas light after SPA navigation too.
    document.documentElement.style.background = /^\/(app|admin|platform)(\/|$)/.test(path)
      ? "#f5f7fb" : "#030910";
  }, [path]);
  useEffect(() => {
    let active = true;
    loadSession().then(value => { if (active) setSession(value); }).catch(error => {
      if (active && !(error instanceof ApiError && error.status === 401)) setAuthError(error);
    }).finally(() => { if (active) setAuthBusy(false); });
    return () => { active = false; };
  }, []);
  const workspace = session?.workspaces.find(w => w.id === session.workspace_id);
  const api = useMemo(() => session && workspace ? new Api(session.csrf,
    {workspace_id: workspace.id, name: workspace.name, role: workspace.role}, () => {
      forget(); setAuthError(new ApiError(401));
    }) : null, [session, workspace]);
  const credential = session ? {csrf: session.csrf, admin: !!workspace && ["owner","admin"].includes(workspace.role)} : null;
  const login = () => { setAuthError(null); signIn(path.startsWith("/admin")).catch(setAuthError); };
  const admin = () => navigate("/admin");
  const invitation = /invite|invitation/.test(path) ? new URLSearchParams(location.search).get("token") : null;
  let content;
  if (invitation) content = <Invitation session={session} token={invitation} reload={reload} onLogin={login} />;
  else if (path.startsWith("/platform") && session) content = <Platform session={session} />;
  else if (path.startsWith("/admin")) content = <Admin key={workspace?.id} api={api} credential={credential} onLogin={login} onForget={forget} onPortal={() => navigate("/app")}
    management={api && session ? <><Members api={api} session={session} reload={reload} /><Connections api={api} session={session} /></> : undefined}
    settings={api && session ? <><WorkspaceSettings session={session} reload={reload} /><Audit api={api} session={session} /></> : undefined} />;
  else if (path.startsWith("/app") && session) content = <main id="main" className="admin-main workspace-main">
    <p className="eyebrow">GOODMCP / KHU LÀM VIỆC</p><p>Chào mừng, {session.user.name || session.user.email}.</p><h1>{workspace?.name || "Chào mừng đến GoodMCP"}</h1>
    <nav className="detail-tabs" aria-label="Khu làm việc">{[["/app","Plugin"],["/app/projects","Dự án"],["/app/connections","Kết nối AI"],["/app/account","Tài khoản"]].map(([href,label]) => <button key={href} aria-current={path === href ? "page" : undefined} onClick={() => navigate(href)}>{label}</button>)}{api && ["owner","admin"].includes(api.workspace.role) && <button onClick={admin}>Quản trị workspace</button>}</nav>
    {path === "/app/account" || !api ? <Account key={workspace?.id} session={session} reload={reload} onForget={forget} /> : path === "/app/projects" ? <Projects key={workspace?.id} api={api} /> : path === "/app/connections" ? <Connections key={workspace?.id} api={api} session={session} /> : <PluginList key={workspace?.id} api={api} />}
  </main>;
  else if ((path.startsWith("/app") || path.startsWith("/platform")) && !authBusy) content = <main id="main" className="admin-login"><h1>Đăng nhập GoodMCP</h1><p>Đăng nhập Google để mở workspace và tiếp tục công việc.</p><button className="primary" onClick={login}>Đăng nhập Google</button><a href="/auth/login">Khôi phục tài khoản quản trị</a></main>;
  else content = <Portal api={api} credential={credential} onLogin={login} onForget={forget} onAdmin={admin} />;
  return <><a className="skip-link" href="#main">Đến nội dung chính</a>{(authBusy || authError) && <div className="auth-status">{authBusy && <p role="status">Đang xác thực…</p>}<Notice error={authError} /></div>}{session && <WorkspaceBar session={session} reload={reload} navigate={navigate} />}{content}</>;
}
