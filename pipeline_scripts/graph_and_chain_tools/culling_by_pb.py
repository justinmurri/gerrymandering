"""Cull the MCMC plans by partisan bias (PB) = 0 for each of the three
    types of imaginary "partisan index" (PI) elections, and save the winnowed plans
    to new JSONL files.
"""


from gerrychain import Graph, Partition
from gerrychain.updaters import Election
from gerrychain.metrics import partisan_bias, efficiency_gap, mean_median
from pprint import pprint
import jsonlines as jl
from tqdm import tqdm
import numpy as np
from pathlib import Path

script_dir = Path(__file__).parent
top_dir = script_dir.parents[1]

# script_dir = "/Users/jarvis/Dropbox/Utah sprint 2025/tyler_utah_runs/notebooks"
# top_dir = "/Users/jarvis/Dropbox/Utah sprint 2025/tyler_utah_runs"



graph = Graph.from_json(f"{top_dir}/JSON_dualgraphs/UT_vtd_graph_2025_w_PIs.json")

race_names = [      #'pres_08',
                    'pres_12',
                    'pres_16',
                    'sen_16',
                    'pres_20',
                    'sen_18',
                    'gov_16',
                    'gov_20',
                    'ag_16',
                    'ag_20',
                    #'treas_20', # no dem candidate in 2020
                    'aud_20',
                    'ag_24',
                    'gov_24', #Lyman is NOT counted as republican
                    'sen_24',
                    'aud_24',
                    'pres_24'
                ]

# Create Election for all the real elections
all_elections = []
for name in race_names:
    all_elections.append(
        Election(
            name,
            {"Dem": f"{name}_dem", "GOP": f"{name}_rep"},
            alias=name
        )
    )


# Partisan index "elections" are not real elections, so need to be 
# added separately.

PI_elections = [
    # Election(
    #     "PI_weighted",
    #     {"Dem": "PI_weighted_dem", "GOP": "PI_weighted_rep"},
    #     alias="PI_1"
    # ),
    # Election(
    #     "PI_median",
    #     {"Dem": "PI_median_dem", "GOP": "PI_median_rep"},
    #     alias="PI_2"
    # ),
     Election(
        "PI_unweighted",
        {"Dem": "PI_unweighted_dem", "GOP": "PI_unweighted_rep"},
        alias="PI_3"
    )
    ]


# Cull by PB=0 for each of the PI elections
for election in PI_elections:
    print(f'Culling by PB=0 for {election.name} election...')   
    election_updaters = {election.name: election}

    zero_bias_count = 0

    unique_districts = set()
    counts_by_district_tuple = {}


    winnowed_pb_samples = []
    with jl.open(f"{top_dir}/chain_outputs/UT_chain_1000000_steps.jsonl") as reader:
        for line in tqdm(reader):
            for i in range(1, 5):
                district_tuple = tuple(np.where(np.array(line["assignment"]) == i)[0])
                unique_districts.add(district_tuple)
                counts_by_district_tuple[district_tuple] = (
                    counts_by_district_tuple.get(district_tuple, 0) + 1
                )

            assignment = {i: str(d) for i, d in enumerate(line["assignment"])}
            partition = Partition(
                graph,
                assignment,
                updaters={"population": lambda p: p["pop"]} | election_updaters,
            )

            # winnow by PB=0 
            pb = partisan_bias(partition[election.name])
            if pb == 0:
                zero_bias_count += 1
                winnowed_pb_samples.append(line)

    with jl.open(f"{top_dir}/data/UT_chain_1000000_winnowed_pb_{election.name}.jsonl", "w") as f:
        f.write_all(winnowed_pb_samples)

    print(f"Results for {election.name}:")  
    print(f"Number of unique districts: {len(unique_districts)}")
    print(
        "Counts by district tuple top 5 most common counts: ",
        sorted(counts_by_district_tuple.values(), reverse=True)[:5],
    )
    print(f"Number of plans with PB=0 per {election.name}: {zero_bias_count}\n")




##################################################
##################################################
# Now cull harvard

# Cull three times: once for each PI_type
for election in PI_elections:
    election_updaters = {election.name: election}

    zero_bias_count = {election.name: 0}

    unique_districts = set()
    counts_by_district_tuple = {}


    winnowed_pb_samples = []
    with jl.open(f"{top_dir}/data/UT_6000_plans_harvard.jsonl") as reader:
        for line in tqdm(reader):
            for i in range(1, 5):
                district_tuple = tuple(np.where(np.array(line["assignment"]) == i)[0])
                unique_districts.add(district_tuple)
                counts_by_district_tuple[district_tuple] = (
                    counts_by_district_tuple.get(district_tuple, 0) + 1
                )

            assignment = {i: str(d) for i, d in enumerate(line["assignment"])}
            partition = Partition(
                graph,
                assignment,
                updaters={"population": lambda p: p["pop"]} | election_updaters,
            )


            # winnow by PB=0 
            pb = partisan_bias(partition[election.name])
            if pb == 0:
                zero_bias_count[election.name] += 1
                winnowed_pb_samples.append(line)

    with jl.open(f"{top_dir}/data/UT_harvard_winnowed_pb_{election.name}.jsonl", "w") as f:
        f.write_all(winnowed_pb_samples)

    print(f"Results for {election.name}:")  
    print(f"Number of unique districts: {len(unique_districts)}")
    print(
        "Counts by district tuple top 5 most common counts: ",
        sorted(counts_by_district_tuple.values(), reverse=True)[:5],
    )
    print()
    pprint(zero_bias_count[election.name])







