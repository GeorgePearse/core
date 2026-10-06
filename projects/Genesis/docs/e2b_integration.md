# E2B Cloud Sandbox Integration ☁️

Genesis integrates with [E2B](https://e2b.dev/) to provide secure, sandboxed cloud environments for evaluating code. This is particularly useful for:

*   **Security**: Running untrusted or evolved code safely isolated from your local machine.
*   **Parallelism**: Scaling evaluations to hundreds of concurrent sandboxes without clogging your local CPU.
*   **Reproducibility**: Ensuring every evaluation runs in a pristine, identical environment.

## Prerequisites

1.  **E2B Account**: Sign up at [e2b.dev](https://e2b.dev).
2.  **API Key**: Get your API key from the E2B dashboard.
3.  **Dependencies**: Install the E2B Python SDK:
    ```bash
    pip install e2b
    # or with uv
    uv pip install e2b
    ```
4.  **Environment Variable**: Add your API key to your `.env` file:
    ```bash
    E2B_API_KEY=e2b_...
    ```

## Configuration

To use E2B, you simply need to use the `e2b` cluster configuration. This can be done via command line or variant files.

### Basic Usage

Run any task using E2B by overriding the cluster config:

```bash
genesis_launch \
    variant=circle_packing_example \
    cluster=e2b
```

### Configuring Dependencies

Since E2B sandboxes start fresh, you must specify any Python dependencies your evaluation script needs. These are defined in `configs/cluster/e2b.yaml`.

To customize dependencies for your specific run, you can override them on the command line:

```bash
genesis_launch \
    variant=circle_packing_example \
    cluster=e2b \
    job_config.dependencies=["numpy","scipy","pandas"]
```

Or create a custom configuration file.

### E2B Configuration Options

Here are the key parameters available in `configs/cluster/e2b.yaml`:

```yaml
job_config:
  _target_: genesis.launch.E2BJobConfig
  
  # Base template (default is "base" for standard Python)
  template: "base"
  
  # Max runtime per evaluation in seconds
  timeout: 300
  
  # Python packages to install via pip
  dependencies:
    - numpy
    
  # Additional files to upload to the sandbox
  # format: { "remote_path": "local_path" }
  additional_files: {}
  
  # Environment variables for the sandbox
  env_vars:
    MY_VAR: "value"

evo_config:
  job_type: "e2b"
  # Number of concurrent sandboxes to run
  max_parallel_jobs: 10
```

## How it Works

1.  **Submission**: When Genesis needs to evaluate a candidate program, it submits the job to the `E2BJobLauncher`.
2.  **Sandbox Creation**: A new E2B sandbox is instantiated in the cloud.
3.  **Setup**:
    *   The `evaluate.py` and candidate `initial.py` (modified) are uploaded.
    *   Specified `dependencies` are installed.
4.  **Execution**: The evaluation script is executed inside the sandbox.
5.  **Result Retrieval**: Genesis captures the stdout/stderr and any result files produced.
6.  **Cleanup**: The sandbox is automatically destroyed.

## Creating Custom E2B Templates

For complex environments (e.g., needing system libraries or specific pre-installed tools), you can create custom E2B templates.

1.  Use the E2B CLI to create a template.
2.  Update your `job_config.template` to point to your new template ID.

Refer to the [E2B Documentation](https://e2b.dev/docs) for details on custom templates.
