# Python adapters G4

`finance/adapter.py` bọc calculators.py, location_sim.py, tariff.py và refs.py
nguyên bản đã kiểm SHA. Input schemas giới hạn ở `packages/core/goodmcp/finance_spec.py`.
Giữ nguyên rounding và hành vi `cit_override=0` của nguồn, kèm warning.

Không có công thức tài chính JavaScript hoặc TF-IDF adapter trong MVP. Chạy 47 ca
đối chiếu Python gốc bằng `scripts/verify.ps1 -Stage G4`; kết quả trong G4.md.
