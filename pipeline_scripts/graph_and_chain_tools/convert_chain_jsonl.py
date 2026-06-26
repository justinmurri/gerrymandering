"""Convert step,[...] chain lines to canonical {"sample", "assignment"} JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import jsonlines as jl


def parse_line(line: str) -> dict:
    line = line.strip()
    if not line:
        raise ValueError("empty line")
    if line.startswith("{"):
        return json.loads(line)
    step_str, assignment_str = line.split(",", 1)
    return {"sample": int(step_str), "assignment": json.loads(assignment_str)}


def convert(input_path: Path, output_path: Path) -> int:
    records = []
    with open(input_path) as f:
        for line in f:
            if line.strip():
                records.append(parse_line(line))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with jl.open(output_path, "w") as writer:
        writer.write_all(records)
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()
    n = convert(Path(args.input), Path(args.output))
    print(f"Converted {n} plans -> {args.output}")


if __name__ == "__main__":
    main()
