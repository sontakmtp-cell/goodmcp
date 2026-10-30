"""Start the persistent local G1 foundation, or stop without removing volumes."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("up", "down", "status"))
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("setup_local", ROOT / "scripts/setup-local.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    directory = module.setup(ROOT / ".local/secrets")
    env = {**os.environ, "HUB_SECRETS_DIR": str(directory)}
    base = ["docker", "compose", "-p", "goodmcp-local", "-f", str(ROOT / "infra/compose.yml")]

    def run(*command): subprocess.run(base + list(command), cwd=ROOT, env=env, check=True)

    if args.operation == "up":
        run("build", "api", "caddy")
        run("up", "-d", "--wait", "postgres")
        run("run", "--rm", "--no-deps", "admin", "python", "-m", "goodmcp.admin", "roles")
        run("run", "--rm", "--no-deps", "migrate")
        run("run", "--rm", "--no-deps", "admin")
        run("up", "-d", "--wait", "api", "worker", "caddy")
        print("G1 local: http://127.0.0.1:" + env.get("HUB_PORT", "18080") + "/health/ready")
    elif args.operation == "down": run("down")
    else: run("ps")


if __name__ == "__main__": main()
