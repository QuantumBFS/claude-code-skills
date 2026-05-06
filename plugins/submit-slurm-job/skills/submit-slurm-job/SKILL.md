---
name: submit-slurm-job
description: "Submit GPU compute jobs to the Slurm cluster. Handles sbatch script generation with correct partition, GPU type, python path, and node selection."
user_invocable: true
---

# Submit Slurm GPU Job

## Overview

Generate and submit sbatch scripts for GPU compute jobs on the cluster. Handles all cluster-specific details: partition, GPU types, node selection, python path.

## Configuration

Before using this skill, set the following in your project's `CLAUDE.md` or environment:

| Variable | Example | Description |
|----------|---------|-------------|
| `PYTHON_PATH` | `/path/to/miniconda3/envs/myenv/bin/python3` | Full path to Python interpreter |
| `PROJECT_DIR` | `/home/user_xxx/private/homefile` | **Must be under `~/private/homefile`**; Slurm submission is only allowed from this path |
| `PARTITION` | `home` | Slurm partition name (the only compute partition) |

**Cluster rule:** scripts and submissions must live under `~/private/homefile`. Data should live under `~/private/datafile`. Run `sbatch`/`srun` only after `cd ~/private/homefile/...`.

## Workflow

### Step 1: Gather Parameters

Ask the user (with `AskUserQuestion`) what they want to run. Key parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `job_name` | (required) | Short job name for SBATCH |
| `gpu_type` | (required) | GPU model, **must be explicit** (e.g., `A100_40G`, `V100`, `A800`) |
| `n_gpu` | `1` | Number of GPUs |
| `time` | `24:00:00` | Wall time limit |
| `mem` | `32G` | Memory |
| `cpus` | `4` | CPUs per task |
| `script` | (required) | Python script path (must live under `~/private/homefile`) |
| `args` | (required) | Script arguments |
| `output_dir` | `{PROJECT_DIR}` | Directory for log files (keep under `~/private/homefile`) |

### Step 2: Select GPU and Node

- **Always specify GPU model in `--gres`**: use `gpu:MODEL:N` (e.g., `gpu:A100_40G:1`, `gpu:A800:2`). `gpu:1` will be rejected.
- Use `slurm_gpustat` (cluster-provided wheel) or `scontrol show nodes -o` to see available GPU models.
- Fragmentation guideline: for A800, there is one 8-GPU node and another 2-GPU node. Prefer ≤2-GPU jobs on the 2-GPU node; larger jobs on the 8-GPU node.
- If the user explicitly requests a node, add `--nodelist=node`.

### Step 3: Write and Submit sbatch Script

**Important:** ensure the script is written under `~/private/homefile/...` and run `sbatch` from that directory (cluster enforcement).

Generate the sbatch script following this template:

```bash
#!/bin/bash
#SBATCH --partition={PARTITION}  # home
#SBATCH --cpus-per-task={cpus}
#SBATCH --mem={mem}
#SBATCH --gres=gpu:{gpu_type}:{n_gpu}
#SBATCH --nodes=1
#SBATCH --time={time}
#SBATCH --job-name={job_name}
#SBATCH -o {output_dir}/{job_name}_%j.out

echo The current job ID is $SLURM_JOB_ID
echo Running on $SLURM_JOB_NODELIST
echo CUDA devices: $CUDA_VISIBLE_DEVICES
echo ==== Job started at `date` ====
nvidia-smi
echo

{PYTHON_PATH} \
    {script} \
    {args}

echo
echo ==== Job finished at `date` ====
```

Key rules:
- **Partition**: use `home` (the only compute partition).
- **Working directory**: script and submission must be under `~/private/homefile/...`.
- **Python path**: use full path `{PYTHON_PATH}` (do NOT `conda activate`).
- **Output**: use `-o` for combined stdout+stderr.
- **GPU model**: must be explicit in `--gres`.
- **No `--nodelist`** unless the user explicitly requests a specific node.

Write the script to `{output_dir}/{job_name}.sh` (under `~/private/homefile`), then submit with `sbatch` from the same directory.

### Step 4: Report

After submission, report:
- Job ID(s) from sbatch output
- Log file location: `{output_dir}/{job_name}_{JOBID}.out`
- How to monitor: `squeue -u $USER`, `tail -f {log_file}`
- How to cancel: `scancel {JOBID}`
- If jobs get auto-`scancel`, verify you submitted from the correct project (`~/private/homefile` matching the web UI project) and that requested resources are within quota.

## Multiple Jobs

If the user wants to submit multiple jobs (e.g., different datasets on different GPUs):
1. Create separate `.sh` scripts for each job
2. Submit all with a loop: `for f in script1.sh script2.sh ...; do sbatch $f; done`
3. Report all job IDs

## Common Patterns

### Sequential tasks on one GPU
Put multiple python commands in a single script, separated by `echo` markers.

### Parallel tasks across GPUs
Create separate scripts, each requesting one GPU. Submit all scripts independently.

### Using `--nodelist` for specific nodes
Only add `#SBATCH --nodelist=n004` when the user explicitly wants a specific node. Otherwise let Slurm schedule based on GPU type availability.
