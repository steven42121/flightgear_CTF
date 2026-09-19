"""验证 env.lock 哈希（供 launcher 调用）。"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from server.anticheat.l1_envlock import EnvLockVerifier


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", required=True)
    parser.add_argument("--fg-root", required=True)
    parser.add_argument("--fg-bin", default=None)
    parser.add_argument("--scenery", default=None)
    args = parser.parse_args()
    
    if not args.fg_bin:
        import platform
        if platform.system() == "Windows":
            args.fg_bin = r"C:\Program Files\FlightGear 2024.1\bin"
        else:
            args.fg_bin = "/opt/flightgear/bin"
    
    verifier = EnvLockVerifier(args.lock)
    report = verifier.verify_all(
        Path(args.fg_root),
        Path(args.fg_bin),
        Path(args.scenery) if args.scenery else None
    )
    
    if report["overall"] != "PASS":
        print(f"ERROR: {report['overall']}", file=sys.stderr)
        for issue in report.get("issues", []):
            print(f"  - {issue}", file=sys.stderr)
        sys.exit(1)
    
    print(f"OK: {report['fg_version']}")
    sys.exit(0)


if __name__ == "__main__":
    main()
