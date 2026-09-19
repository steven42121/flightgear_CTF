"""验证 env.lock 哈希（供 launcher 调用）。"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from server.anticheat.l1_envlock import EnvLockVerifier
from tools.fg_detect import detect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", required=True)
    parser.add_argument("--fg-root", default=None)
    parser.add_argument("--fg-bin", default=None)
    parser.add_argument("--scenery", default=None)
    args = parser.parse_args()

    fg = detect()

    fg_root = args.fg_root or fg.data_root
    fg_bin  = args.fg_bin  or fg.bin_dir
    fg_scenery = args.scenery or fg.scenery_dir

    if not fg_root:
        print("ERROR: Cannot find FlightGear data directory (FG_ROOT).", file=sys.stderr)
        print("       Set --fg-root or FG_ROOT environment variable.", file=sys.stderr)
        sys.exit(1)
    if not fg_bin:
        print("ERROR: Cannot find FlightGear binary directory.", file=sys.stderr)
        print("       Set --fg-bin or FG_BIN environment variable.", file=sys.stderr)
        sys.exit(1)

    verifier = EnvLockVerifier(args.lock)
    report = verifier.verify_all(
        Path(fg_root),
        Path(fg_bin),
        Path(fg_scenery) if fg_scenery else None
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