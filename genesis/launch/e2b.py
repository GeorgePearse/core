"""
E2B Cloud Sandbox launcher for Genesis.

This module provides integration with E2B (e2b.dev) for running evaluations
in cloud-based sandboxes. This enables highly parallel execution of
evaluation jobs across isolated environments.
"""

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from e2b import Sandbox
except ImportError:
    # Fall back to e2b_code_interpreter if available
    try:
        from e2b_code_interpreter import Sandbox
    except ImportError:
        Sandbox = None  # type: ignore

from genesis.utils import load_results

logger = logging.getLogger(__name__)


@dataclass
class E2BSandboxJob:
    """Represents a running E2B sandbox job."""

    job_id: str
    sandbox: Sandbox
    results_dir: str
    start_time: float
    exec_fname: str


# Global registry of active E2B jobs
E2B_JOBS: Dict[str, E2BSandboxJob] = {}


def get_e2b_api_key() -> str:
    """Get E2B API key from environment."""
    # Try to load from .env file if python-dotenv is available
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    api_key = os.environ.get("E2B_API_KEY")
    if not api_key:
        raise ValueError(
            "E2B_API_KEY environment variable not set. "
            "Please set it in your .env file or environment."
        )
    return api_key


def _ensure_sandbox_available() -> None:
    """Ensure E2B Sandbox is available."""
    if Sandbox is None:
        raise ImportError(
            "E2B package not installed. Please install it with: pip install e2b"
        )


def submit(
    log_dir: str,
    cmd: List[str],
    exec_fname: str,
    eval_program_path: str,
    timeout: int = 300,
    template: str = "base",
    verbose: bool = False,
    dependencies: Optional[List[str]] = None,
) -> str:
    """
    Submit a job to run in an E2B sandbox.

    Args:
        log_dir: Directory to store logs locally.
        cmd: Command to execute (used for compatibility, but we'll construct our own).
        exec_fname: Path to the file to evaluate.
        eval_program_path: Path to the evaluation script.
        timeout: Sandbox timeout in seconds.
        template: E2B sandbox template to use.
        verbose: Whether to enable verbose logging.
        dependencies: List of pip packages to install in the sandbox.

    Returns:
        str: Job ID for tracking the sandbox.
    """
    _ensure_sandbox_available()

    job_id = f"e2b-{uuid.uuid4().hex[:8]}"
    log_dir_path = Path(log_dir)
    log_dir_path.mkdir(parents=True, exist_ok=True)

    if verbose:
        logger.info(f"Creating E2B sandbox for job {job_id}...")

    try:
        # E2B v2.x uses Sandbox.create() instead of constructor
        sandbox = Sandbox.create(
            template=template,
            timeout=timeout,
            api_key=get_e2b_api_key(),
        )

        # Install any required dependencies
        if dependencies:
            deps_str = " ".join(dependencies)
            if verbose:
                logger.info(f"Installing dependencies: {deps_str}")
            sandbox.commands.run(f"pip install {deps_str}")

        # Upload the program file to evaluate
        if Path(exec_fname).exists():
            with open(exec_fname, "r") as f:
                program_content = f.read()

            # Create the program file in the sandbox
            sandbox_program_path = "/home/user/main.py"
            sandbox.files.write(sandbox_program_path, program_content)

            if verbose:
                logger.info(f"Uploaded program to {sandbox_program_path}")

        # Upload the evaluation script
        if Path(eval_program_path).exists():
            with open(eval_program_path, "r") as f:
                eval_content = f.read()

            sandbox_eval_path = "/home/user/evaluate.py"
            sandbox.files.write(sandbox_eval_path, eval_content)

            if verbose:
                logger.info(f"Uploaded evaluator to {sandbox_eval_path}")

        # Create results directory in sandbox
        sandbox.commands.run("mkdir -p /home/user/results")

        # Store job info
        E2B_JOBS[job_id] = E2BSandboxJob(
            job_id=job_id,
            sandbox=sandbox,
            results_dir=log_dir,
            start_time=time.time(),
            exec_fname=exec_fname,
        )

        # Start the evaluation asynchronously
        # The command runs in background, we'll poll for results
        eval_cmd = (
            f"cd /home/user && python evaluate.py "
            f"--program_path main.py "
            f"--results_dir results "
            f"> results/job_log.out 2> results/job_log.err"
        )

        if verbose:
            logger.info(f"Running evaluation: {eval_cmd}")

        # Run asynchronously by not waiting for result
        sandbox.commands.run(eval_cmd, timeout=timeout)

        if verbose:
            logger.info(f"Submitted E2B job {job_id}")

        return job_id

    except Exception as e:
        logger.error(f"Failed to create E2B sandbox: {e}")
        # Write error to log files
        with open(log_dir_path / "job_log.err", "w") as f:
            f.write(f"E2B sandbox creation failed: {e}\n")
        with open(log_dir_path / "job_log.out", "w") as f:
            f.write("")

        raise


def submit_with_files(
    log_dir: str,
    exec_fname: str,
    eval_program_path: str,
    additional_files: Optional[Dict[str, str]] = None,
    timeout: int = 300,
    template: str = "base",
    verbose: bool = False,
    dependencies: Optional[List[str]] = None,
    env_vars: Optional[Dict[str, str]] = None,
) -> str:
    """
    Submit a job to E2B with additional files uploaded.

    Args:
        log_dir: Directory to store logs locally.
        exec_fname: Path to the file to evaluate.
        eval_program_path: Path to the evaluation script.
        additional_files: Dict mapping sandbox paths to local file paths.
        timeout: Sandbox timeout in seconds.
        template: E2B sandbox template to use.
        verbose: Whether to enable verbose logging.
        dependencies: List of pip packages to install.
        env_vars: Environment variables to set in the sandbox.

    Returns:
        str: Job ID for tracking the sandbox.
    """
    _ensure_sandbox_available()

    job_id = f"e2b-{uuid.uuid4().hex[:8]}"
    log_dir_path = Path(log_dir)
    log_dir_path.mkdir(parents=True, exist_ok=True)

    if verbose:
        logger.info(f"Creating E2B sandbox for job {job_id}...")

    try:
        # E2B v2.x uses Sandbox.create() instead of constructor
        sandbox = Sandbox.create(
            template=template,
            timeout=timeout,
            api_key=get_e2b_api_key(),
        )

        # Set environment variables if provided
        if env_vars:
            for key, value in env_vars.items():
                sandbox.commands.run(f'export {key}="{value}"')

        # Install dependencies
        if dependencies:
            deps_str = " ".join(dependencies)
            if verbose:
                logger.info(f"Installing dependencies: {deps_str}")
            result = sandbox.commands.run(f"pip install {deps_str}")
            if verbose:
                logger.debug(f"Dependency installation output: {result.stdout}")

        # Upload the program file
        if Path(exec_fname).exists():
            with open(exec_fname, "r") as f:
                program_content = f.read()
            sandbox.files.write("/home/user/main.py", program_content)

        # Upload the evaluation script
        if Path(eval_program_path).exists():
            with open(eval_program_path, "r") as f:
                eval_content = f.read()
            sandbox.files.write("/home/user/evaluate.py", eval_content)

        # Upload additional files
        if additional_files:
            for sandbox_path, local_path in additional_files.items():
                if Path(local_path).exists():
                    with open(local_path, "r") as f:
                        content = f.read()
                    sandbox.files.write(sandbox_path, content)
                    if verbose:
                        logger.info(f"Uploaded {local_path} to {sandbox_path}")

        # Create results directory
        sandbox.commands.run("mkdir -p /home/user/results")

        # Store job info
        E2B_JOBS[job_id] = E2BSandboxJob(
            job_id=job_id,
            sandbox=sandbox,
            results_dir=log_dir,
            start_time=time.time(),
            exec_fname=exec_fname,
        )

        # Run the evaluation
        eval_cmd = (
            "cd /home/user && python evaluate.py "
            "--program_path main.py "
            "--results_dir results "
            "> results/job_log.out 2> results/job_log.err"
        )

        sandbox.commands.run(eval_cmd, timeout=timeout)

        if verbose:
            logger.info(f"Submitted E2B job {job_id}")

        return job_id

    except Exception as e:
        logger.error(f"Failed to create E2B sandbox: {e}")
        with open(log_dir_path / "job_log.err", "w") as f:
            f.write(f"E2B sandbox creation failed: {e}\n")
        raise


def get_job_status(job_id: str) -> Optional[str]:
    """
    Check if an E2B job is still running.

    Args:
        job_id: The job ID to check.

    Returns:
        str: Job ID if running, empty string if completed, None if not found.
    """
    if job_id not in E2B_JOBS:
        return None

    job = E2B_JOBS[job_id]

    try:
        # Check if sandbox is still alive
        # E2B sandboxes automatically close after timeout
        # We check by trying to run a simple command
        job.sandbox.commands.run("echo 'alive'", timeout=5)
        return job_id  # Still running
    except Exception:
        return ""  # Completed or failed


def download_results(job_id: str, verbose: bool = False) -> bool:
    """
    Download results from an E2B sandbox to local directory.

    Args:
        job_id: The job ID.
        verbose: Whether to enable verbose logging.

    Returns:
        bool: True if successful, False otherwise.
    """
    if job_id not in E2B_JOBS:
        logger.warning(f"Job {job_id} not found in E2B_JOBS registry")
        return False

    job = E2B_JOBS[job_id]
    results_dir = Path(job.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    try:
        sandbox = job.sandbox

        # Download result files
        result_files = [
            ("results/metrics.json", "metrics.json"),
            ("results/correct.json", "correct.json"),
            ("results/job_log.out", "job_log.out"),
            ("results/job_log.err", "job_log.err"),
        ]

        for sandbox_file, local_file in result_files:
            try:
                content = sandbox.files.read(f"/home/user/{sandbox_file}")
                with open(results_dir / local_file, "w") as f:
                    f.write(content)
                if verbose:
                    logger.debug(f"Downloaded {sandbox_file} to {local_file}")
            except Exception as e:
                if verbose:
                    logger.debug(f"Could not download {sandbox_file}: {e}")
                # Create empty file if download fails
                if "log" in local_file:
                    with open(results_dir / local_file, "w") as f:
                        f.write(f"Could not retrieve log: {e}\n")

        # Also try to download any extra files (like extra.npz, extra.pkl)
        for extra_file in ["results/extra.npz", "results/extra.pkl"]:
            try:
                content = sandbox.files.read(f"/home/user/{extra_file}")
                local_name = Path(extra_file).name
                # For binary files, we need to handle differently
                with open(results_dir / local_name, "wb") as f:
                    if isinstance(content, str):
                        f.write(content.encode())
                    else:
                        f.write(content)
            except Exception:
                pass  # Extra files are optional

        return True

    except Exception as e:
        logger.error(f"Failed to download results for job {job_id}: {e}")
        return False


def cleanup_sandbox(job_id: str, verbose: bool = False) -> None:
    """
    Clean up an E2B sandbox and remove from registry.

    Args:
        job_id: The job ID.
        verbose: Whether to enable verbose logging.
    """
    if job_id not in E2B_JOBS:
        return

    job = E2B_JOBS[job_id]

    try:
        job.sandbox.kill()
        if verbose:
            logger.info(f"Killed sandbox for job {job_id}")
    except Exception as e:
        if verbose:
            logger.debug(f"Error killing sandbox {job_id}: {e}")

    del E2B_JOBS[job_id]


def monitor(
    job_id: str,
    results_dir: str,
    poll_interval: int = 5,
    verbose: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Monitor an E2B job until completion and load its results.

    Args:
        job_id: The E2B job ID to monitor.
        results_dir: Local directory to store results.
        poll_interval: Time in seconds between status checks.
        verbose: Whether to enable verbose logging.

    Returns:
        dict: Dictionary containing job results.
    """
    if verbose:
        logger.info(f"Monitoring E2B job {job_id}...")

    if job_id not in E2B_JOBS:
        logger.warning(f"Job {job_id} not found in E2B_JOBS registry")
        return None

    job = E2B_JOBS[job_id]

    # For E2B, the command has already completed (it's synchronous in submit)
    # We just need to download the results
    download_results(job_id, verbose=verbose)

    # Clean up the sandbox
    cleanup_sandbox(job_id, verbose=verbose)

    # Load and return results
    return load_results(results_dir)


def cancel_job(job_id: str, verbose: bool = False) -> bool:
    """
    Cancel a running E2B job.

    Args:
        job_id: The job ID to cancel.
        verbose: Whether to enable verbose logging.

    Returns:
        bool: True if cancelled successfully, False otherwise.
    """
    if job_id not in E2B_JOBS:
        return False

    try:
        cleanup_sandbox(job_id, verbose=verbose)
        return True
    except Exception as e:
        logger.error(f"Failed to cancel E2B job {job_id}: {e}")
        return False


def get_sandbox_info(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Get information about an E2B sandbox.

    Args:
        job_id: The job ID.

    Returns:
        dict: Information about the sandbox, or None if not found.
    """
    if job_id not in E2B_JOBS:
        return None

    job = E2B_JOBS[job_id]
    return {
        "job_id": job.job_id,
        "results_dir": job.results_dir,
        "start_time": job.start_time,
        "elapsed_time": time.time() - job.start_time,
        "exec_fname": job.exec_fname,
    }
