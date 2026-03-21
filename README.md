# Claude Code Skills for HPC

A collection of Claude Code skills for high-performance computing workflows, focusing on Slurm cluster job submission.

## What are Claude Code Skills?

Skills are reusable prompt templates that extend Claude Code's capabilities. They live in `.claude/skills/` and can be invoked with `/skill-name`.

## Installation

1. Copy the skill directory to your project:
   ```bash
   cp -r submit-slurm-job /path/to/your/project/.claude/skills/
   ```

2. Configure paths in your project's `.claude/CLAUDE.md`:
   ```markdown
   ## Slurm Configuration

   - PYTHON_PATH: `/path/to/miniconda3/envs/myenv/bin/python3`
   - PROJECT_DIR: `/home/your_user/private/homefile`   # scripts/logs must live here
   - PARTITION: `home`                                 # compute partition
   ```

3. Restart Claude Code or reload the project.

## Available Skills

### `submit-slurm-job`

Submit GPU compute jobs to Slurm clusters. Handles:
- Automatic sbatch script generation
- GPU type selection (V100, A100, A800, H200, etc.)
- Node scheduling
- Log file management
- Cluster rules: submit from `~/private/homefile` and **always specify GPU model** in `--gres`

**Usage:**
```
/submit-slurm-job
```

Claude will ask you for job parameters (script path, GPU type, memory, etc.) and generate + submit the sbatch script.

**Example:**
```
User: /submit-slurm-job
Claude: What would you like to run?
User: Train my model with train.py --epochs 100
Claude: [generates and submits job]
```

## Requirements

- Slurm cluster with GPU nodes
- Claude Code (formerly AWS Code)
- Python environment for your compute jobs

## Contributing

Contributions welcome! Please ensure:
- Skills are well-documented
- Paths are parameterized (no hardcoded user paths)
- Examples are included

## License

MIT
