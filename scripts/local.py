"""Start the persistent local G1 foundation, or stop without removing volumes."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("up", "down", "status", "runtime"))
    parser.add_argument('--release',type=Path,help='Operator-approved offline G4 release.json')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("setup_local", ROOT / "scripts/setup-local.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    directory = module.setup(ROOT / ".local/secrets")
    (ROOT / ".local/g3-samples").mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "HUB_SECRETS_DIR": str(directory)}
    base = ["docker", "compose", "-p", "goodmcp-local", "-f", str(ROOT / "infra/compose.yml")]

    def run(*command): subprocess.run(base + list(command), cwd=ROOT, env=env, check=True)

    if args.operation == "up":
        run("build", "api", "caddy")
        run("up", "-d", "--wait", "postgres")
        run("run", "--rm", "--no-deps", "admin", "python", "-m", "goodmcp.admin", "roles")
        run("run", "--rm", "--no-deps", "migrate")
        run("run", "--rm", "--no-deps", "admin")
        active=ROOT/'.local/g4/active/release.json'
        run("up", "-d", "--wait", "api", "auth", "worker", "caddy", *(['dispatcher'] if active.exists() else []))
        print("Local Hub: " + env.get("HUB_PUBLIC_BASE_URL", "http://127.0.0.1:18080") + "/health/ready")
    elif args.operation=='runtime':
        if not args.release or not args.release.is_file():raise ValueError('Provide --release for the offline build')
        env['HUB_G4_RELEASE_DIR']=str(args.release.resolve().parent)
        run('run','--rm','--no-deps','runtime_admin','python','-m','goodmcp.runtime_admin','--active')
        active=ROOT/'.local/g4/active';active.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(args.release,active/'release.new.json');(active/'release.new.json').replace(active/'release.json')
        env['HUB_G4_RELEASE_DIR']=str(active)
        run('--profile','g4','up','-d','dispatcher')
        print('Approved local Python runtime enabled; no test probe bindings.')
    elif args.operation == "down": run('--profile','g4',"down")
    else: run('--profile','g4',"ps")


if __name__ == "__main__": main()
