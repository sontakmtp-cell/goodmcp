"""Generate local file secrets once. Never print credentials or overwrite existing ones."""
import argparse
from pathlib import Path
import secrets


def setup(directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ("admin_password", "migrator_password", "runtime_password", "owner_password"):
        path = directory / name
        if path.exists():
            if len(path.read_text(encoding="utf-8").strip()) < 16:
                raise RuntimeError("Existing secret invalid; explicit operator repair required")
            continue
        with path.open("x", encoding="utf-8") as stream:
            stream.write(secrets.token_urlsafe(36) + "\n")
        # Compose file secrets are bind-mounted; containers use fixed UID 10001.
        # Parent directory remains private on POSIX; Windows uses the host user's ACL.
        path.chmod(0o644)
    return directory


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=Path(__file__).resolve().parents[1] / ".local/secrets")
    args = parser.parse_args()
    print("Secret files ready: " + str(setup(args.dir)))
