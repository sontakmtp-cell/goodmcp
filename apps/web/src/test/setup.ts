import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { webcrypto } from "node:crypto";
Object.defineProperty(globalThis, "crypto", {
  value: webcrypto,
  configurable: true,
});
HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute("open", "");
};
HTMLDialogElement.prototype.close = function () {
  this.removeAttribute("open");
  this.dispatchEvent(new Event("close"));
};
afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  history.replaceState(null, "", "/");
});
