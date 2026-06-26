"""Compactness vs partisan metric correlation utilities."""

from __future__ import annotations

from pathlib import Path

import jsonlines as jl
import numpy as np

COMPACTNESS_METRICS = ["polsby", "reock"]
Y_METRICS = ["PB", "EG", "LRVS"]
COMPACTNESS_LABELS = {"polsby": "Polsby-Popper", "reock": "Reock"}
Y_LABELS = {"PB": "Partisan Bias", "EG": "Efficiency Gap", "LRVS": "LRVS"}


def load_compactness(path: Path) -> list[tuple[int, float]]:
    rows = []
    with jl.open(path) as reader:
        for obj in reader:
            mean_score = float(np.mean(list(obj["scores"].values())))
            rows.append((obj["sample"], mean_score))
    return rows


def load_symmetry(path: Path) -> dict[int, dict[str, float]]:
    result = {}
    with jl.open(path) as reader:
        for obj in reader:
            result[obj["sample"]] = obj["scores"]
    return result


def load_lrvs(path: Path) -> list[float]:
    values = []
    with jl.open(path) as reader:
        for obj in reader:
            values.append(float(obj["scores"]))
    return values


def compute_r(
    compactness_rows: list[tuple[int, float]],
    sym_map: dict[int, dict[str, float]],
    lrvs_list: list[float],
    y_metric: str,
    *,
    subsample: bool,
    subsample_size: int,
    seed: int,
) -> float | None:
    xs, ys = [], []
    for i, (sample_id, compact_val) in enumerate(compactness_rows):
        if y_metric in ("PB", "EG"):
            if sample_id not in sym_map:
                continue
            y_val = sym_map[sample_id][y_metric]
        else:
            if i >= len(lrvs_list):
                continue
            y_val = lrvs_list[i]
        xs.append(compact_val)
        ys.append(y_val)

    if len(xs) < 2:
        return None

    xs = np.array(xs)
    ys = np.array(ys)

    if subsample and len(xs) > subsample_size:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(xs), size=subsample_size, replace=False)
        xs = xs[idx]
        ys = ys[idx]

    return float(np.corrcoef(xs, ys)[0, 1])


def r_to_color(r: float) -> str:
    r = max(-1.0, min(1.0, r))
    if r >= 0:
        intensity = int(round(r * 200))
        return f"#{255 - intensity:02x}{255 - intensity:02x}ff"
    intensity = int(round(-r * 200))
    return f"#ff{255 - intensity:02x}{255 - intensity:02x}"


def text_color(bg_hex: str) -> str:
    r = int(bg_hex[1:3], 16)
    g = int(bg_hex[3:5], 16)
    b = int(bg_hex[5:7], 16)
    brightness = (r * 299 + g * 587 + b * 114) / 1000
    return "#000000" if brightness > 128 else "#ffffff"
