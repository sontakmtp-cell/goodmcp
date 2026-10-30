# Expert model policy

These are host subagent selector names, not OpenAI API model IDs. This is an
instruction policy applied when tools support model selection; plugin metadata
does not force the conversation's model.

| Expert | Skill | Preferred model | Reasoning effort |
| --- | --- | --- | --- |
| opc-team-lead (Điều phối đội OPC) | opc-orchestrator | `gpt-6.1-sol` | high |
| opc-resource-auditor (Kiểm kê nguồn lực) | opc-resource-audit | `gpt-6-luna` | medium |
| opc-niche-strategist (Chiến lược thị trường ngách) | opc-niche-positioning | `gpt-6.1-sol` | high |
| opc-value-designer (Thiết kế giá trị) | opc-value-proposition | `gpt-6.1-sol` | medium |
| opc-model-architect (Thiết kế mô hình kinh doanh) | opc-business-model-design | `gpt-6.1-sol` | high |
| opc-mvp-designer (Thiết kế thử nghiệm MVP) | opc-mvp-designer | `gpt-6.1-sol` | high |
| opc-conversion-designer (Thiết kế chuyển đổi) | opc-conversion-loop | `gpt-6.1-sol` | medium |
| opc-asset-strategist (Tổ chức tài sản tái sử dụng) | opc-asset-ops | `gpt-6-luna` | medium |
| opc-dashboard-reviewer (Chẩn đoán vận hành) | opc-dashboard-review | `gpt-6.1-sol` | high |

Escalate complex Luna tasks to `gpt-6.1-sol` / high. If Sol is unavailable, do not silently demote strategic judgment to Luna; disclose the limitation and use the best supported host model. The active lead inherits the main chat model unless the user selects another model in the host.
