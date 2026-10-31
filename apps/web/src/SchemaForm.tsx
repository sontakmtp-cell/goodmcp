import { useState } from "react";
type Schema = Record<string, any>;
const labels: Record<string, string> = {
  revenue: "Doanh thu (VND)",
  cost: "Chi phí (VND)",
  rate: "Thuế suất (%)",
  free_years: "Số năm miễn thuế",
  half_years: "Số năm giảm một nửa",
  loss_carry: "Lỗ chuyển kỳ (VND)",
  year: "Năm tính thuế",
  horizon: "Số năm dự tính",
  headcount: "Số nhân viên",
  monthly_gross_wage: "Lương gộp tháng/người (VND)",
  dependents: "Số người phụ thuộc",
  gross_payment: "Thanh toán gộp (VND)",
  net_amount: "Số tiền thực nhận (VND)",
  cif: "Giá trị CIF (VND)",
  category: "Nhóm hàng",
  vat_override: "Thuế VAT thay thế (%)",
  factory_area: "Diện tích nhà xưởng (m²)",
  land_area: "Diện tích đất (m²)",
  provinces: "Tỉnh/thành",
  profit: "Lợi nhuận (VND)",
  cit_override: "Thuế TNDN thay thế (%)",
};
const enumLabels: Record<string, string> = {
  bac_ninh: "Bắc Ninh",
  hai_phong: "Hải Phòng",
  bac_giang: "Bắc Giang",
  binh_duong: "Bình Dương",
  dong_nai: "Đồng Nai",
  ho_chi_minh: "TP. Hồ Chí Minh",
  quang_ngai: "Quảng Ngãi",
  da_nang: "Đà Nẵng",
  machinery_import: "Máy móc nhập khẩu",
  raw_material: "Nguyên liệu",
  intermediate: "Hàng trung gian",
  finished_goods: "Thành phẩm",
  alcohol: "Đồ uống có cồn",
  vehicle: "Phương tiện",
  tobacco: "Thuốc lá",
};
export function fieldSchema(s: Schema): Schema {
  return s.anyOf ? s.anyOf.find((v: Schema) => v.type !== "null") || s : s;
}
export function SchemaForm({
  schema,
  busy,
  onSubmit,
}: {
  schema: Schema;
  busy: boolean;
  onSubmit: (v: Record<string, unknown>) => void;
}) {
  const [values, setValues] = useState<Record<string, any>>(() =>
    Object.fromEntries(
      Object.entries(schema.properties || {})
        .filter(([, s]) => (s as Schema).default != null)
        .map(([k, s]) => [k, (s as Schema).default]),
    ),
  );
  const properties = Object.entries(schema.properties || {}) as [
    string,
    Schema,
  ][];
  const supported = properties.every(([, s]) => {
    const p = fieldSchema(s);
    return (
      ["number", "integer", "string", "boolean"].includes(p.type) ||
      (p.type === "array" && p.items?.enum)
    );
  });
  if (!supported)
    return (
      <p className="notice">
        Biểu mẫu này có kiểu dữ liệu chưa được giao diện hỗ trợ. Dùng công cụ
        qua MCP; chưa thể chạy từ trang này.
      </p>
    );
  return (
    <form
      className="form-grid"
      onSubmit={(e) => {
        e.preventDefault();
        const args: Record<string, unknown> = {};
        for (const [k, s] of properties) {
          const p = fieldSchema(s),
            v = values[k];
          if (v !== "" && v !== undefined)
            args[k] =
              p.type === "number" || p.type === "integer" ? Number(v) : v;
        }
        onSubmit(args);
      }}
    >
      {properties.length === 0 && <p>Công cụ không cần tham số.</p>}
      {properties.map(([name, raw]) => {
        const s = fieldSchema(raw),
          required = schema.required?.includes(name),
          label = labels[name] || raw.title || name;
        return (
          <label key={name}>
            {label}
            {!required && <small>Không bắt buộc</small>}
            {s.type === "array" ? (
              <select
                multiple
                aria-label={label}
                value={values[name] || []}
                onChange={(e) =>
                  setValues({
                    ...values,
                    [name]: Array.from(
                      e.target.selectedOptions,
                      (o) => o.value,
                    ),
                  })
                }
              >
                {s.items.enum.map((v: string) => (
                  <option key={v} value={v}>
                    {enumLabels[v] || v}
                  </option>
                ))}
              </select>
            ) : s.enum ? (
              <select
                required={required}
                value={values[name] ?? ""}
                onChange={(e) =>
                  setValues({ ...values, [name]: e.target.value })
                }
              >
                <option value="">Chọn…</option>
                {s.enum.map((v: string) => (
                  <option key={v} value={v}>
                    {enumLabels[v] || v}
                  </option>
                ))}
              </select>
            ) : s.type === "boolean" ? (
              <input
                type="checkbox"
                checked={values[name] || false}
                onChange={(e) =>
                  setValues({ ...values, [name]: e.target.checked })
                }
              />
            ) : (
              <input
                type={
                  s.type === "number" || s.type === "integer"
                    ? "number"
                    : "text"
                }
                required={required}
                min={
                  s.minimum ??
                  (s.exclusiveMinimum != null
                    ? s.exclusiveMinimum + 0.000001
                    : undefined)
                }
                max={s.maximum}
                step={s.type === "integer" ? 1 : "any"}
                value={values[name] ?? ""}
                onChange={(e) =>
                  setValues({ ...values, [name]: e.target.value })
                }
              />
            )}
          </label>
        );
      })}
      <div className="span-all">
        <button className="primary" disabled={busy}>
          Chạy bằng Python
        </button>
        <p className="hint">
          Kết quả do công cụ Python trên máy chủ tính. Giao diện không tính lại
          công thức.
        </p>
      </div>
    </form>
  );
}
