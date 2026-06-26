#!/usr/bin/env bash

SCRIPT_DIR=$(dirname "$(realpath "${BASH_SOURCE[0]}")")

plan_name="CONG_DIST"
n_steps=1000
seed=42
tol=0.01
pop_col="total_pop_20"
json_dir="JSON_dualgraphs"
output_dir="chain_outputs"

json_file="$(realpath ./${json_dir}/UT_vtd_graph_2024.json)"
final_output_file="$(realpath ./${output_dir}/UT_chain_${n_steps}_steps.jsonl)"

rm -f "$final_output_file"

frcw \
    --assignment-col "$plan_name" \
    --graph-json "$json_file" \
    --n-steps $n_steps \
    --pop-col $pop_col \
    --rng-seed $seed \
    --tol $tol \
    --variant district-pairs-region-aware \
    --region-weights '{"COUNTYFP20": 0.5, "PLACE_ID": 0.5}' \
    --writer canonical \
    --batch-size 1 \
    --n-threads 1 \
    --output-file "${final_output_file}"
