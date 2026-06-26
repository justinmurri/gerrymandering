# %%
"""Cull plans by road connectivity
"""
from gerrychain import Graph, Partition
import jsonlines as jl
from tqdm import tqdm
from pathlib import Path
import geopandas as gpd
from gerrychain.constraints.contiguity import contiguous, contiguous_components
from joblib import Parallel, delayed
from joblib_progress import joblib_progress


script_dir = Path(__file__).parent
top_dir = script_dir.parents[1]

# script_dir = "/Users/jarvis/Dropbox/Utah sprint 2025/tyler_utah_runs/notebooks"
# top_dir = "/Users/jarvis/Dropbox/Utah sprint 2025/tyler_utah_runs"


# %%
ensembles = [('harvard',6000), 
            ('harvard_winnowed_pb', 3_202),   # winnowed to PB=0 only
            ('recom1M_winnowed_pb', 205_101), # winnowed to PB=0 only
            ('recom1M',1_000_000), 
            ('practice100k', 100_000)
            ]



input_files = {'recom1M': "/chain_outputs/UT_chain_1000000_steps.jsonl",
            'recom1M_winnowed_pb': "/data/UT_chain_1000000_winnowed_pb_PI_unweighted.jsonl",
            'harvard': "/data/UT_6000_plans_harvard.jsonl",
            'harvard_winnowed_pb': "/data/UT_harvard_winnowed_pb_PI_unweighted.jsonl",
            'practice100k': "/data/UT_chain_100000_steps_practice(reversibleRA).jsonl"
            }



for graph_type in ['queen','rook']:
    print(f"\n Processing road connectivity winnowing for {graph_type} graph...")
    road_graph = Graph.from_json(f"{top_dir}/JSON_dualgraphs/2020road_graph_{graph_type}_w_2025_elections_data_edited.json")
    road_nodes = list(road_graph.nodes)


    def winnow_contiguous(obj):
        assignment = {n: obj['assignment'][n] for n in road_nodes}
        partition = Partition(
            road_graph,
            assignment
            )
        return {obj['sample']: contiguous(partition)}

    for ensemble, n_samples in ensembles:
        winnowed_samples = []
        winnowed_assignments = []
        count = 0
        with jl.open(f"{top_dir}{input_files[ensemble]}") as reader:
            ## winnow road-contiguous plans in parallel
            with joblib_progress(description=f"Processing contiguity for {ensemble}", total=n_samples):
                winnowed_samples = Parallel(n_jobs=-1)(delayed(winnow_contiguous)(obj) for obj in reader)
            
        print(f"Consolidating results for {ensemble}...")
        with jl.open(f"{top_dir}{input_files[ensemble]}") as reader:
            for i,obj in tqdm(enumerate(reader), total=n_samples):
                count += 1
                if winnowed_samples[i][obj['sample']]:
                    winnowed_assignments.append({"assignment":obj['assignment'], "sample":obj['sample']})


        print(f"Number of road-contiguous plans in {graph_type} {ensemble} = {len(winnowed_assignments)} out of {count}")

        with jl.open(f"{top_dir}/data/{ensemble}_winnowed_roads_{graph_type}.jsonl", "w") as f:
            f.write_all(winnowed_assignments)



