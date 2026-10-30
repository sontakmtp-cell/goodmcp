"""Deterministic modern MCP regressions. No provider API or model key needed."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from connections import PROTOCOL, create_connection, validate_config

def load_cases(path: Path) -> list[dict]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("Cases must be a non-empty JSON array")
    ids = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Each case must be an object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in ids:
            raise ValueError("Each case needs a unique non-empty string id")
        ids.add(case_id)
        if not isinstance(case.get("tool"), str) or not case["tool"]:
            raise ValueError("Each case needs a tool name")
        if not isinstance(case.get("arguments", {}), dict):
            raise ValueError("arguments must be an object")
        expected = case.get("expect")
        allowed = {"is_error", "structured_content", "text"}
        if not isinstance(expected, dict) or not expected or set(expected) - allowed:
            raise ValueError("expect needs is_error, structured_content or text")
        if "is_error" in expected and not isinstance(expected["is_error"], bool):
            raise ValueError("is_error must be boolean")
        if "text" in expected and not isinstance(expected["text"], str):
            raise ValueError("text must be a string")
    return cases

async def evaluate(config: dict, cases: list[dict], allow_writes=False) -> dict:
    report = {"required_protocol": PROTOCOL, "observed_protocol": None, "cases": [], "passed": False}
    async with create_connection(config) as connection:
        report["observed_protocol"] = connection.protocol_version
        if connection.protocol_version != PROTOCOL:
            report["error"] = "Required modern protocol was not negotiated"
            return report
        tools = {tool["name"]: tool for tool in await connection.list_tools()}
        for case in cases:
            row = {"id": case["id"], "tool": case["tool"], "passed": False}
            tool = tools.get(case["tool"])
            if tool is None:
                row["error"] = "Tool not discovered"
            elif not allow_writes and tool.get("annotations", {}).get("readOnlyHint") is not True:
                row["error"] = "Write or unannotated tool blocked; authorize isolated write tests explicitly"
            else:
                try:
                    result = await connection.call_tool(case["tool"], case.get("arguments", {}))
                    actual = {
                        "is_error": bool(result.get("isError", False)),
                        "structured_content": result.get("structuredContent"),
                        "text": "\n".join(block["text"] for block in result.get("content", []) if block.get("type") == "text"),
                    }
                    expected = {"is_error": False, **case["expect"]}
                    row["passed"] = all(actual[key] == value for key, value in expected.items())
                    row["mismatched_fields"] = [key for key, value in expected.items() if actual[key] != value]
                    row["actual"] = {key: actual[key] for key in expected}
                except Exception as exc:
                    row["error"] = f"Tool invocation failed ({type(exc).__name__})"
            report["cases"].append(row)
        report["passed"] = all(row["passed"] for row in report["cases"])
    return report

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-writes", action="store_true", help="Authorized isolated write tests only")
    args = parser.parse_args()
    try:
        config = json.loads(args.connection.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("connection must be an object")
        validate_config(config)
        cases = load_cases(args.cases)
    except (ValueError, OSError, TypeError) as exc:
        print(f"Invalid evaluation configuration ({type(exc).__name__})", file=sys.stderr)
        return 2
    try:
        report = asyncio.run(evaluate(config, cases, args.allow_writes))
    except Exception as exc:
        report = {"required_protocol": PROTOCOL, "passed": False,
                  "error": f"Connection/evaluation failed ({type(exc).__name__})"}
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        try:
            args.output.write_text(rendered + "\n", encoding="utf-8")
        except OSError:
            print("Could not write evaluation report", file=sys.stderr)
            return 2
    print(rendered)
    return 0 if report["passed"] else 1

if __name__ == "__main__":
    sys.exit(main())
