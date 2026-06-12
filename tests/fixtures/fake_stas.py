from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "success"

    input_filename = sys.stdin.readline().strip()
    output_filename = sys.stdin.readline().strip()

    if mode == "fail":
        Path("STASERR").write_text("COULD NOT PROCESS THIS INPUT\n", encoding="utf-8")
        print("fake STAS failed", file=sys.stderr)
        return 2

    if mode == "no-output":
        print("fake STAS completed without output")
        return 0

    input_content = Path(input_filename).read_text(encoding="utf-8")
    Path(output_filename).write_text(
        f"FAKE STAS OUTPUT\nTEMP={os.environ.get('TEMP', '')}\nTMP={os.environ.get('TMP', '')}\n{input_content}",
        encoding="utf-8",
    )
    print("fake STAS success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
