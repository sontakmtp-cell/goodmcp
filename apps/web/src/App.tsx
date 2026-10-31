import { useEffect, useState, useRef } from "react";
import {
  Graph,
  Copy,
  ArrowRight,
  BookOpen,
  ShieldCheck,
  Plugs,
  ArrowUpRight,
} from "@phosphor-icons/react";
import { Api, ApiError, type Workspace, type Plugin, type Page } from "./api";
import { signIn, completeSignIn, revoke, type Credential } from "./auth";
import { Sharks } from "./Sharks";
import { Admin } from "./Admin";
import {
  ConfirmButton,
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
export function Catalog({ api }: { api: Api }) {
  const [cursor, setCursor] = useState("");
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
        empty(
          "Chưa có plugin đang bật trên trang này. Quản trị viên có thể nhập và bật plugin.",
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
  );
}
export function Portal({
  api,
  credential,
  onLogin,
  onForget,
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
      <section className="hero">
        <Sharks />
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
                <button
                  className="primary"
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
                Hướng dẫn kết nối {platform}
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
              <Catalog api={api} />
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
              <p>Trạng thái các kết nối AI khác chưa được máy chủ cung cấp.</p>
              {credential && (
                <ConfirmButton
                  title="Thu hồi phiên web?"
                  detail="Phiên web hiện tại sẽ mất quyền truy cập. Thao tác này không thu hồi các kết nối AI khác hoặc đăng xuất cookie tài khoản."
                  danger
                  onConfirm={async () => {
                    await revoke(credential);
                    onForget();
                  }}
                >
                  Thu hồi phiên web
                </ConfirmButton>
              )}
              <a href="/auth/account">Quản lý đăng nhập / đăng xuất</a>
            </section>
          )}
        </main>
      </section>
      <footer>
        <a className="brand" href="/">
          GoodMCP
        </a>
        <span>Công cụ của bạn. Trong cuộc chat của bạn.</span>
        <a
          href="https://github.com/stackedlol/ascii-sharks"
          target="_blank"
          rel="noreferrer"
        >
          ASCII sharks · MIT
        </a>
      </footer>
    </div>
  );
}
export function App() {
  const [credential, setCredential] = useState<Credential | null>(null),
    [api, setApi] = useState<Api | null>(null),
    [admin, setAdmin] = useState(location.pathname.startsWith("/admin")),
    [authBusy, setAuthBusy] = useState(false),
    [authError, setAuthError] = useState<unknown>(null);
  const callbackStarted = useRef(false);
  const forget = () => {
    setApi(null);
    setCredential(null);
    setAdmin(false);
    history.replaceState(null, "", "/");
  };
  useEffect(() => {
    const pop = () => setAdmin(location.pathname.startsWith("/admin"));
    window.addEventListener("popstate", pop);
    return () => window.removeEventListener("popstate", pop);
  }, []);
  useEffect(() => {
    if (location.pathname !== "/oauth/callback" || callbackStarted.current)
      return;
    callbackStarted.current = true;
    setAuthBusy(true);
    (async () => {
      try {
        const c = await completeSignIn();
        const probe = new Api(
          c.access_token,
          { workspace_id: "", name: "", role: "" },
          forget,
        );
        const w = await probe.request<Workspace[]>(
          "/api/v1/me/workspaces",
          {},
          false,
        );
        if (!w?.length) throw new Error("Tài khoản chưa có vùng dữ liệu.");
        setCredential(c);
        setApi(
          new Api(c.access_token, w[0], () => {
            forget();
            setAuthError(new ApiError(401));
          }),
        );
        setAdmin(c.admin && ["owner", "admin"].includes(w[0].role));
        history.replaceState(
          null,
          "",
          c.admin && ["owner", "admin"].includes(w[0].role) ? "/admin" : "/",
        );
      } catch (e) {
        forget();
        setAuthError(e);
      } finally {
        setAuthBusy(false);
      }
    })();
  }, []);
  const login = async () => {
    setAuthBusy(true);
    setAuthError(null);
    try {
      await signIn(admin);
    } catch (e) {
      setAuthError(e);
      setAuthBusy(false);
    }
  };
  return (
    <>
      <a className="skip-link" href="#main">
        Đến nội dung chính
      </a>
      {(authBusy || authError) && (
        <div className="auth-status">
          {authBusy && <p role="status">Đang xác thực…</p>}
          <Notice error={authError} />
        </div>
      )}
      {admin ? (
        <Admin
          api={api}
          credential={credential}
          onLogin={login}
          onForget={forget}
          onPortal={() => {
            history.pushState(null, "", "/");
            setAdmin(false);
          }}
        />
      ) : (
        <Portal
          api={api}
          credential={credential}
          onLogin={login}
          onForget={forget}
          onAdmin={() => {
            if (credential && !credential.admin) {
              setAuthBusy(true);
              signIn(true).catch((e) => {
                setAuthError(e);
                setAuthBusy(false);
              });
              return;
            }
            history.pushState(null, "", "/admin");
            setAdmin(true);
          }}
        />
      )}
    </>
  );
}
