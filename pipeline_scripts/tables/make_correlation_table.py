"""Compactness vs partisan metric correlation summary table.

Usage:
    python make_correlation_table.py --config config_UT.yaml
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config_loader import (  # noqa: E402
    figures_dir,
    load_config,
    metric_output_path,
    project_root,
    resolve_ensemble_meta,
    subsample_for_scatter,
)
from correlation import (  # noqa: E402
    COMPACTNESS_METRICS,
    Y_METRICS,
    COMPACTNESS_LABELS,
    Y_LABELS,
    compute_r,
    load_compactness,
    load_lrvs,
    load_symmetry,
    r_to_color,
    text_color,
)

COLUMNS = [(c, y) for c in COMPACTNESS_METRICS for y in Y_METRICS]
COLUMN_HEADERS = [f"{COMPACTNESS_LABELS[c]} vs {Y_LABELS[y]}" for c, y in COLUMNS]


def main() -> None:
    parser = argparse.ArgumentParser(description="Compactness correlation summary table.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--ensembles", nargs="*", default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    top_dir = project_root(args.config)
    fig_dir = figures_dir(cfg, top_dir)
    fig_dir.mkdir(parents=True, exist_ok=True)

    table_cfg = cfg["tables"]["compactness_correlation"]
    ensemble_names = args.ensembles or table_cfg["ensembles"]
    subsample_size = cfg["performance"]["subsample"]["scatter"]
    seed = cfg["performance"]["random_seed"]

    rows = []
    for name in ensemble_names:
        meta = resolve_ensemble_meta(cfg, name)
        row: dict = {"name": name, "label": meta["label"]}

        sym_path = metric_output_path(cfg, top_dir, "symmetry", name)
        lrvs_path = metric_output_path(cfg, top_dir, "rmd", name, output_key="lrvs")
        sym_map = load_symmetry(sym_path) if sym_path.exists() else {}
        lrvs_list = load_lrvs(lrvs_path) if lrvs_path.exists() else []

        for compact_metric in COMPACTNESS_METRICS:
            compact_path = metric_output_path(cfg, top_dir, compact_metric, name)
            if not compact_path.exists():
                for y_metric in Y_METRICS:
                    row[(compact_metric, y_metric)] = None
                continue

            compactness_rows = load_compactness(compact_path)
            for y_metric in Y_METRICS:
                if y_metric in ("PB", "EG") and not sym_map:
                    row[(compact_metric, y_metric)] = None
                    continue
                if y_metric == "LRVS" and not lrvs_list:
                    row[(compact_metric, y_metric)] = None
                    continue
                row[(compact_metric, y_metric)] = compute_r(
                    compactness_rows,
                    sym_map,
                    lrvs_list,
                    y_metric,
                    subsample=subsample_for_scatter(cfg, name),
                    subsample_size=subsample_size,
                    seed=seed,
                )
        rows.append(row)

    csv_path = top_dir / table_cfg["output_csv"]
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Ensemble"] + COLUMN_HEADERS)
        for row in rows:
            values = [
                f"{row[(c, y)]:.4f}" if row[(c, y)] is not None else ""
                for c, y in COLUMNS
            ]
            writer.writerow([row["label"]] + values)
    print(f"Wrote {csv_path}")

    html_path = top_dir / table_cfg["output_html"]
    with open(html_path, "w") as f:
        f.write("""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Compactness vs Fairness Correlations</title>
<style>
  body { font-family: sans-serif; padding: 2em; }
  table { border-collapse: collapse; margin-top: 1em; }
  th, td { padding: 8px 14px; border: 1px solid #ccc; text-align: center; }
  th { background: #f0f0f0; }
  td.label { text-align: left; font-weight: bold; background: #fafafa; }
  td.missing { color: #aaa; }
</style></head><body>
<h2>Compactness vs Partisan Fairness — Pearson r</h2><table>
""")
        f.write("<tr><th>Ensemble</th>" + "".join(f"<th>{h}</th>" for h in COLUMN_HEADERS) + "</tr>\n")
        for row in rows:
            f.write(f'<tr><td class="label">{row["label"]}</td>')
            for c, y in COLUMNS:
                r = row[(c, y)]
                if r is None:
                    f.write('<td class="missing">—</td>')
                else:
                    bg = r_to_color(r)
                    fg = text_color(bg)
                    f.write(f'<td style="background:{bg};color:{fg}">{r:.4f}</td>')
            f.write("</tr>\n")
        f.write("</table></body></html>\n")
    print(f"Wrote {html_path}")


if __name__ == "__main__":
    main()
