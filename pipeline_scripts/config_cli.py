"""Small CLI helpers for bash pipeline runners.

Usage examples:
  python config_cli.py pipeline-flags /path/to/config.yaml
  python config_cli.py cull-settings /path/to/config.yaml
  python config_cli.py cull-pairs /path/to/config.yaml /path/to/project
  python config_cli.py list metrics|figures|tables /path/to/config.yaml
  python config_cli.py script metrics polsby /path/to/config.yaml
  python config_cli.py script figures metric_histograms /path/to/config.yaml
  python config_cli.py script tables full_summary /path/to/config.yaml
  python config_cli.py attach-pi-script /path/to/config.yaml
  python config_cli.py canonical-template /path/to/config.yaml
  python config_cli.py canonical-path /path/to/config.yaml ensemble_name
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    fmt = {
        "abbrev": cfg["state"]["abbrev"],
        "vintage": cfg["state"]["data_vintage"],
    }
    return _resolve(cfg, fmt)


def _resolve(obj, fmt: dict):
    if isinstance(obj, str):
        try:
            return obj.format_map(fmt)
        except KeyError:
            return obj
    if isinstance(obj, dict):
        return {k: _resolve(v, fmt) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve(i, fmt) for i in obj]
    return obj


def pipeline_flags(cfg: dict) -> None:
    steps = cfg.get("pipeline", {}).get("steps", {})
    preprocess = bool(
        steps.get("attach_pi", False)
        or steps.get("cull_pb", False)
        or steps.get("cull_roads", False)
    )
    print(
        int(preprocess),
        int(bool(steps.get("metrics"))),
        int(bool(steps.get("tables"))),
        int(bool(steps.get("figures"))),
    )


def preprocessing_flags(cfg: dict) -> None:
    steps = cfg.get("pipeline", {}).get("steps", {})
    attach = bool(steps.get("attach_pi", False))
    cull = bool(steps.get("cull_pb", False) or steps.get("cull_roads", False))
    print(int(attach), int(cull))


def cull_settings(cfg: dict) -> None:
    steps = cfg.get("pipeline", {}).get("steps", {})
    do_pb = bool(steps.get("cull_pb", False))
    do_roads = bool(steps.get("cull_roads", False))
    road_types = " ".join(cfg["preprocessing"]["cull"]["road_types"])
    print(int(do_pb), int(do_roads), road_types)


def cull_pairs(cfg: dict, top_dir: Path) -> None:
    steps = cfg.get("pipeline", {}).get("steps", {})
    cull_names = steps.get("cull_ensembles")
    if not cull_names:
        cull_names = [e["name"] for e in cfg["ensembles"]]

    by_name = {e["name"]: e for e in cfg["ensembles"]}
    for name in cull_names:
        if name not in by_name:
            raise SystemExit(f"Unknown cull_ensemble: {name!r}")
        raw = top_dir / by_name[name]["chain_raw"]
        print(f"{raw}\t{name}")


def list_steps(kind: str, cfg: dict) -> None:
    steps = cfg.get("pipeline", {}).get("steps", {})
    if kind == "metrics":
        names = steps.get("metrics", [])
    elif kind == "figures":
        names = steps.get("figures", [])
        if not names:
            names = list(cfg.get("figures", {}).get("scripts", {}).keys())
    elif kind == "tables":
        names = steps.get("tables", [])
        if not names:
            names = ["full_summary", "compactness_summary", "compactness_correlation"]
    else:
        raise SystemExit(f"Unknown step kind: {kind!r}")
    print(" ".join(names))


def script_path(kind: str, name: str, cfg: dict) -> None:
    if kind == "metrics":
        print(cfg["metrics"][name]["script"])
    elif kind == "figures":
        entry = cfg["figures"]["scripts"].get(name, name)
        print(entry["script"] if isinstance(entry, dict) else entry)
    elif kind == "tables":
        print(cfg["tables"][name]["script"])
    else:
        raise SystemExit(f"Unknown script kind: {kind!r}")


def attach_pi_script(cfg: dict) -> None:
    print(cfg["preprocessing"]["attach_pi"]["script"])


def canonical_template(cfg: dict) -> None:
    print(cfg["chain_derivatives"]["canonical"])


def canonical_path(cfg: dict, ensemble_name: str) -> None:
    print(cfg["chain_derivatives"]["canonical"].format(name=ensemble_name))


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        raise SystemExit(__doc__)

    cmd = argv[1]
    if cmd == "pipeline-flags":
        pipeline_flags(load_config(argv[2]))
    elif cmd == "preprocessing-flags":
        preprocessing_flags(load_config(argv[2]))
    elif cmd == "cull-settings":
        cull_settings(load_config(argv[2]))
    elif cmd == "cull-pairs":
        cfg = load_config(argv[2])
        cull_pairs(cfg, Path(argv[3]))
    elif cmd == "list":
        list_steps(argv[2], load_config(argv[3]))
    elif cmd == "script":
        script_path(argv[2], argv[3], load_config(argv[4]))
    elif cmd == "attach-pi-script":
        attach_pi_script(load_config(argv[2]))
    elif cmd == "canonical-template":
        canonical_template(load_config(argv[2]))
    elif cmd == "canonical-path":
        canonical_path(load_config(argv[2]), argv[3])
    else:
        raise SystemExit(f"Unknown command: {cmd!r}")


if __name__ == "__main__":
    main(sys.argv)
