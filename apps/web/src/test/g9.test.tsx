import { it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { App } from "../App";
import { PluginList, Projects } from "../Admin";
import { Platform, WorkspaceBar, Invitation } from "../Workspace";
import { PluginDetail } from "../Plugins";
import { Api, type Plugin } from "../api";
import { type WebSession } from "../auth";
vi.mock("../Sharks", () => ({Sharks: () => <canvas aria-hidden="true" />}));
const session: WebSession = {user:{id:"u",email:"member@example.com",platform_admin:false,email_verified:true,google_linked:true},csrf:"csrf-value",workspace_id:"ws-a",workspaces:[{id:"ws-a",name:"Nhóm A",role:"member"},{id:"ws-b",name:"Nhóm B",role:"viewer"}],google_enabled:true};
const response = (data:unknown,status=200) => new Response(JSON.stringify({data}),{status});
const api = (role: string) => new Api("csrf",{workspace_id:"ws-a",name:"Nhóm A",role});
it("restores a member directly into /app after reload without stored credentials", async () => {
  history.replaceState(null,"","/app");
  const fetch = vi.fn(async (url:string) => url === "/auth/web/session" ? response(session) : response({items:[],next_cursor:null}));
  vi.stubGlobal("fetch",fetch);
  render(<App />);
  expect(await screen.findByRole("heading",{name:"Nhóm A"})).toBeVisible();
  expect(screen.queryByRole("button",{name:"Quản trị workspace"})).toBeNull();
  expect(screen.queryByRole("button",{name:"Tải ZIP"})).toBeNull();
  expect(screen.getByRole("button",{name:"Dự án"})).toBeVisible();
  expect(localStorage.length).toBe(0);
  expect(sessionStorage.length).toBe(0);
});
it("changes only the web workspace and reloads authoritative session rights", async () => {
  const fetch = vi.fn().mockResolvedValue(response({workspace_id:"ws-b"}));
  vi.stubGlobal("fetch",fetch);
  const reload = vi.fn().mockResolvedValue(undefined);
  render(<WorkspaceBar session={session} reload={reload} navigate={() => {}} />);
  fireEvent.change(screen.getByRole("combobox",{name:"Chọn workspace"}),{target:{value:"ws-b"}});
  await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
  expect(fetch.mock.calls[0][0]).toBe("/auth/web/select-workspace");
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({workspace_id:"ws-b"});
  expect(new Headers(fetch.mock.calls[0][1].headers).get("X-CSRF-Token")).toBe(session.csrf);
  expect(fetch).toHaveBeenCalledTimes(1);
});
it("does not request platform data for workspace owners without platform authority", () => {
  const fetch=vi.fn();vi.stubGlobal("fetch",fetch);
  render(<Platform session={{...session,workspaces:[{id:"ws-a",name:"A",role:"owner"}]}} />);
  expect(screen.getByText("Chưa có quyền quản trị nền tảng")).toBeVisible();
  expect(fetch).not.toHaveBeenCalled();
});
it("keeps viewer projects readable without a create form", async () => {
  vi.stubGlobal("fetch",vi.fn().mockImplementation(() => Promise.resolve(response({items:[{id:"p",name:"Dự án dùng chung",revision:1}],next_cursor:null}))));
  render(<Projects api={api("viewer")} />);
  expect(await screen.findByText("Dự án dùng chung")).toBeVisible();
  expect(screen.getByRole("button",{name:"Mở dự án"})).toBeVisible();
  expect(screen.queryByRole("button",{name:"Tạo dự án"})).toBeNull();
});
it("never offers viewers plugin mutations or Python invocation", async () => {
  const plugin:Plugin={installation_id:"i",plugin_version_id:"v",name:"Plugin",enabled:true,revision:1,manifest_version:"1",preview:{}};
  const fetch=vi.fn().mockImplementation(() => Promise.resolve(response({items:[{id:"v2",manifest_version:"2"}],next_cursor:null})));
  vi.stubGlobal("fetch",fetch);
  render(<PluginDetail api={api("viewer")} plugin={plugin} onBack={() => {}} />);
  await screen.findByText("2");
  expect(screen.queryByRole("button",{name:"Tắt plugin"})).toBeNull();
  expect(screen.queryByRole("button",{name:"Dùng bản này"})).toBeNull();
  expect(screen.queryByRole("button",{name:"Tải ZIP gốc"})).toBeNull();
  fireEvent.click(screen.getByRole("button",{name:"Công cụ Python"}));
  expect(screen.getByText("Vai trò chỉ xem không được chạy công cụ Python.")).toBeVisible();
  expect(fetch).toHaveBeenCalledTimes(1);
});
it("keeps a rejected invitation visible without claiming membership", async () => {
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(response(null,403)));
  render(<Invitation session={session} token="one-use-invite" reload={async()=>{}} onLogin={()=>{}} />);
  fireEvent.click(screen.getByRole("button",{name:"Nhận lời mời"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("chưa có quyền");
  expect(screen.queryByText(/Đã nhận lời mời/)).toBeNull();
});
