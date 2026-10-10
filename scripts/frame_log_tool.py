"""Read the frame log out of an Aseko Local diagnostics download.

Usage:

    python scripts/frame_log_tool.py DIAGNOSTICS.json [--around N] [--window S] [--jsonl OUT]

Without options it prints every marker with its time and note, then a summary.
``--around N`` prints the frames received within ``--window`` seconds (default
60) before and after marker N -- the frames that go with the photo taken after
tapping it.  ``--jsonl OUT`` writes every record, with absolute times, to a
JSON-lines file for your own tooling.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import sys
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any

# Load frame_log.py by path: importing the package would pull in Home Assistant.
_spec = importlib.util.spec_from_file_location(
    "frame_log",
    Path(__file__).resolve().parents[1]
    / "custom_components/aseko_local/recording/frame_log.py",
)
_frame_log = importlib.util.module_from_spec(_spec)
# registered before it runs: its dataclasses look their module up by name
sys.modules[_spec.name] = _frame_log
_spec.loader.exec_module(_frame_log)
decode_lines = _frame_log.decode_lines


def load_records(path: Path) -> list[dict[str, Any]]:
    """Return every frame log record of a diagnostics download."""
    diagnostics = json.loads(path.read_text(encoding="utf-8"))
    frame_log = diagnostics.get("data", diagnostics).get("frame_log")
    if not frame_log:
        msg = f"{path}: no frame_log section"
        raise SystemExit(msg)
    blob = zlib.decompress(base64.b64decode(frame_log["blob"]))
    return list(decode_lines(blob.splitlines(keepends=True)))


def main() -> None:
    """Run the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("diagnostics", type=Path)
    parser.add_argument("--around", type=int, help="marker number")
    parser.add_argument("--window", type=float, default=60.0, help="seconds")
    parser.add_argument("--jsonl", type=Path, help="write every record here")
    args = parser.parse_args()

    records = load_records(args.diagnostics)

    if args.jsonl:
        with args.jsonl.open("w", encoding="utf-8") as out:
            for record in records:
                out.write(json.dumps(record) + "\n")
        print(f"wrote {len(records)} records to {args.jsonl}")

    if args.around is not None:
        marks = [r for r in records if r["k"] == "mark" and r["n"] == args.around]
        if not marks:
            msg = f"no marker {args.around}"
            raise SystemExit(msg)
        at = datetime.fromisoformat(marks[0]["t"]).timestamp()
        for record in records:
            offset = datetime.fromisoformat(record["t"]).timestamp() - at
            if abs(offset) <= args.window:
                label = (
                    f"MARK {record['n']} {record.get('note', '')}"
                    if record["k"] == "mark"
                    else record["d"]
                )
                print(f"{offset:+7.1f}s {record['k']:7s} {label}")
        return

    for record in records:
        if record["k"] == "mark":
            since = ", ".join(
                f"{serial}: {age}s" for serial, age in record.get("since", {}).items()
            )
            print(
                f"marker {record['n']:3d}  {record['t']}  {record.get('note', '')}"
                + (f"  (last frame {since} before)" if since else "")
            )
    kinds: dict[str, int] = {}
    for record in records:
        kinds[record["k"]] = kinds.get(record["k"], 0) + 1
    if records:
        print(
            f"{len(records)} records {kinds} from {records[0]['t']} to {records[-1]['t']}"
        )


if __name__ == "__main__":
    main()
