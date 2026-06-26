"""Shared plotting helpers for figure scripts."""

from __future__ import annotations

import json
from pathlib import Path

import jsonlines as jl
import matplotlib.pyplot as plt
import numpy as np
from gerrytools.plotting import districtr
from matplotlib.ticker import MaxNLocator, StrMethodFormatter


def load_human_plans(path: Path) -> dict:
    with open(path) as f:
        return dict(sorted(json.load(f).items()))


def load_district_scores(path: Path) -> list[float]:
    values: list[float] = []
    with jl.open(path) as reader:
        for obj in reader:
            values.extend(obj["scores"].values())
    return values


def load_plan_level_scores(path: Path, key: str | None = None) -> list[float]:
    values: list[float] = []
    with jl.open(path) as reader:
        for obj in reader:
            if key is None:
                values.append(float(obj["scores"]))
            else:
                values.append(float(obj["scores"][key]))
    return values


def add_human_vlines(ax: plt.Axes, human_plans: dict, value_fn, *, offset: float = 0.05) -> None:
    colors = districtr(len(human_plans))
    for i, (plan, scores) in enumerate(human_plans.items()):
        val = value_fn(scores)
        if val is None:
            continue
        if isinstance(val, dict):
            for j, v in enumerate(val.values()):
                ax.axvline(float(v) + i * offset, label=plan if j == 0 else None, color=colors[i])
        else:
            ax.axvline(float(val) + i * offset, label=plan, color=colors[i])


def add_int_hist(ax, data, color, label):
    lo, hi = int(min(data)), int(max(data))
    bins = np.arange(lo - 0.5, hi + 1.5, 1)
    ax.hist(data, bins=bins, alpha=0.5, color=color, density=True, label=label)
    return ax, lo, hi


def int_hist(ax, data, title, xlabel, color, label):
    ax, lo, hi = add_int_hist(ax, data, color, label)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Frequency")
    ax.set_xticks(np.arange(lo, hi + 1, 1))
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:0.2f}"))
    return ax


def save_figure(figures_dir: Path, filename: str) -> Path:
    figures_dir.mkdir(parents=True, exist_ok=True)
    output = figures_dir / filename
    plt.savefig(output, bbox_inches="tight", dpi=300)
    plt.close()
    return output
