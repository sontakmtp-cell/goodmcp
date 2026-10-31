import { useEffect, useState, useRef, type ReactNode } from "react";
import { ApiError } from "./api";
export function Notice({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div role="alert" className="notice error">
      {error instanceof Error
        ? error.message
        : "Không thể hoàn thành thao tác."}
      {error instanceof ApiError && error.requestId && (
        <small>Mã yêu cầu: {error.requestId}</small>
      )}
    </div>
  );
}
export function useAction() {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    [success, setSuccess] = useState("");
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const run = async (fn: () => Promise<unknown>, message = "") => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setSuccess("");
    try {
      await fn();
      if (mounted.current) setSuccess(message);
    } catch (e) {
      if (mounted.current) setError(e);
    } finally {
      if (mounted.current) setBusy(false);
    }
  };
  return {
    busy,
    error,
    success,
    run,
    feedback: (
      <>
        <Notice error={error} />
        {busy && <p role="status">Đang xử lý…</p>}
        {success && (
          <p role="status" className="notice success">
            {success}
          </p>
        )}
      </>
    ),
  };
}
export function useData<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(true),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setBusy(true);
    setData(null);
    setError(null);
    load()
      .then(
        (d) => {
          if (active) setData(d);
        },
        (e) => {
          if (active) setError(e);
        },
      )
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [...deps, revision]);
  return { data, error, busy, reload: () => setRevision((v) => v + 1) };
}
export function DataState({
  state,
  children,
}: {
  state: { busy: boolean; error: unknown; reload: () => void };
  children: ReactNode;
}) {
  return (
    <div aria-busy={state.busy}>
      {state.busy ? (
        <p role="status" className="empty">
          Đang tải dữ liệu…
        </p>
      ) : state.error ? (
        <>
          <Notice error={state.error} />
          <button onClick={state.reload}>Thử lại</button>
        </>
      ) : (
        children
      )}
    </div>
  );
}
export function ConfirmButton({
  children,
  title,
  detail,
  onConfirm,
  disabled = false,
  danger = false,
}: {
  children: ReactNode;
  title: string;
  detail: string;
  onConfirm: () => Promise<unknown>;
  disabled?: boolean;
  danger?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null),
    button = useRef<HTMLButtonElement>(null),
    action = useAction();
  return (
    <>
      <button
        ref={button}
        disabled={disabled}
        className={danger ? "danger" : ""}
        onClick={() => ref.current?.showModal()}
      >
        {children}
      </button>
      <dialog
        ref={ref}
        aria-label={title}
        onClose={() => button.current?.focus()}
      >
        <h2>{title}</h2>
        <p>{detail}</p>
        {action.feedback}
        <div className="actions">
          <button disabled={action.busy} onClick={() => ref.current?.close()}>
            Giữ nguyên
          </button>
          <button
            className={danger ? "danger" : "primary"}
            disabled={action.busy}
            onClick={() =>
              action.run(async () => {
                await onConfirm();
                ref.current?.close();
              })
            }
          >
            Xác nhận
          </button>
        </div>
      </dialog>
    </>
  );
}
export const empty = (text: string) => <p className="empty">{text}</p>;
export function Plain({ value }: { value: unknown }) {
  return (
    <pre className="plain">
      {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
    </pre>
  );
}
export function Status({ value }: { value: string }) {
  const words: Record<string, string> = {
    ready: "Sẵn sàng",
    uploading: "Đang tải",
    queued: "Đang chờ",
    scanning: "Đang kiểm tra",
    running: "Đang chạy",
    succeeded: "Hoàn thành",
    failed: "Thất bại",
    cancelled: "Đã hủy",
    draft: "Bản nháp",
    confirmed: "Đã xác nhận",
    in_progress: "Đang thực hiện",
    completed: "Hoàn thành",
  };
  return <span className="badge">{words[value] || value}</span>;
}
