import json

input_path  = "/Users/justinmurri/Gerrymander-Research/data/UT_chain_500000_steps_(RW := 0.3).jsonl"
output_path = "/Users/justinmurri/Gerrymander-Research/data/UT_chain_500000_steps_(RW := 0.3)_proper.jsonl"

with open(input_path) as infile, open(output_path, "w") as outfile:
    for line in infile:
        line = line.strip()
        if not line:
            continue
        sample_str, assignment_str = line.split(",", 1)
        row = {"sample": int(sample_str), "assignment": json.loads(assignment_str)}
        outfile.write(json.dumps(row) + "\n")

print("Done!")