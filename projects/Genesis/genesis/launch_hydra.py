#!/usr/bin/env python3
from pathlib import Path
from dotenv import load_dotenv
import hydra
from omegaconf import DictConfig, OmegaConf
from genesis.core import EvolutionRunner
import subprocess
import warnings


def get_git_info():
    """Get git repository information."""
    try:
        # Get commit hash
        commit_sha = (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode("utf-8")
            .strip()
        )

        # Get branch name
        branch = (
            subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode("utf-8")
            .strip()
        )

        # Check for uncommitted changes
        status = (
            subprocess.check_output(
                ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL
            )
            .decode("utf-8")
            .strip()
        )
        is_dirty = bool(status)

        return commit_sha, branch, is_dirty
    except Exception as e:
        warnings.warn(f"Failed to retrieve git info: {e}")
        return None, None, False


@hydra.main(config_path="../configs", config_name="config", version_base=None)
def main(cfg: DictConfig):
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)

    print("Experiment configurations:")
    print(OmegaConf.to_yaml(cfg, resolve=True))

    job_cfg = hydra.utils.instantiate(cfg.job_config)
    db_cfg = hydra.utils.instantiate(cfg.db_config)
    evo_cfg = hydra.utils.instantiate(cfg.evo_config)

    # Populate git info
    commit_sha, branch, is_dirty = get_git_info()
    evo_cfg.git_commit_sha = commit_sha
    evo_cfg.git_branch = branch
    evo_cfg.git_dirty = is_dirty

    # Set strategy name from config if available, otherwise use default
    # Note: hydra output dir or config name might be useful here
    if hasattr(cfg, "variant"):
        evo_cfg.strategy_name = cfg.variant

    evo_runner = EvolutionRunner(
        evo_config=evo_cfg,
        job_config=job_cfg,
        db_config=db_cfg,
        verbose=cfg.verbose,
    )
    evo_runner.run()


if __name__ == "__main__":
    main()
