"""E2B sandbox executor for isolated test execution."""

import hashlib
import json
import os
import time
import asyncio
from pathlib import Path
from typing import Any, Optional

from evaluator.agent import AgentInvoker
from evaluator.executors.base import (
    ExecutionContext,
    ExecutionError,
    ExecutorBackend,
    SandboxConfig,
)
from evaluator.models import TestCase, TestSuite


class SandboxPool:
    """Manages a pool of reusable e2b sandbox sessions."""

    def __init__(self, max_sessions: int = 5) -> None:
        """Initialize sandbox pool.

        Args:
            max_sessions: Maximum number of concurrent sandbox sessions
        """
        self.max_sessions = max_sessions
        self.available_sandboxes: list[Any] = []  # List of e2b Sandbox instances
        self.active_sandboxes: dict[str, Any] = {}  # session_id -> Sandbox
        # Import deferred to handle missing e2b gracefully
        self._e2b_module = None
        self._sandbox_class = None

    def _get_e2b_module(self) -> Any:
        """Lazily import e2b module."""
        if self._e2b_module is None:
            try:
                import e2b_code_interpreter  # type: ignore[import-not-found]

                self._e2b_module = e2b_code_interpreter
                self._sandbox_class = e2b_code_interpreter.Sandbox
            except ImportError:
                raise ExecutionError(
                    "e2b-code-interpreter not installed. Install with: "
                    "uv pip install 'evaluator[e2b]'"
                )
        return self._e2b_module

    def acquire(
        self,
        config: SandboxConfig,
        template_id: Optional[str] = None,
    ) -> tuple[str, Any]:
        """Acquire a sandbox session.

        Args:
            config: Sandbox configuration
            template_id: Optional template ID to use

        Returns:
            Tuple of (session_id, sandbox_instance)
        """
        self._get_e2b_module()

        # Create new sandbox using the .create() factory method
        retries = 3
        last_error = None

        for attempt in range(retries):
            try:
                sandbox = self._sandbox_class.create(timeout=config.timeout_seconds)
                break
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    time.sleep(2**attempt)  # Exponential backoff: 1, 2, 4
                    continue
                raise ExecutionError(f"Failed to create sandbox after {retries} attempts: {str(e)}")

        session_id = sandbox.sandbox_id
        self.active_sandboxes[session_id] = sandbox
        return session_id, sandbox

    def release(self, session_id: str) -> None:
        """Release a sandbox session back to the pool.

        Args:
            session_id: Sandbox session ID
        """
        if session_id in self.active_sandboxes:
            sandbox = self.active_sandboxes.pop(session_id)
            try:
                sandbox.kill()
            except Exception:
                pass  # Sandbox may already be terminated

    async def acquire_async(
        self,
        config: SandboxConfig,
        template_id: Optional[str] = None,
    ) -> tuple[str, Any]:
        """Acquire a sandbox session asynchronously.

        Args:
            config: Sandbox configuration
            template_id: Optional template ID to use

        Returns:
            Tuple of (session_id, sandbox_instance)
        """
        self._get_e2b_module()

        # Import async sandbox class
        from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-not-found]

        # Create new sandbox with the specified template
        retries = 3
        last_error = None
        sandbox = None

        for attempt in range(retries):
            try:
                sandbox = await AsyncSandbox.create(
                    template=template_id,
                    timeout=config.timeout_seconds,
                )
                break
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    await asyncio.sleep(2**attempt)  # Exponential backoff: 1, 2, 4
                    continue
                raise ExecutionError(f"Failed to create sandbox after {retries} attempts: {str(e)}")

        session_id = sandbox.sandbox_id
        self.active_sandboxes[session_id] = sandbox
        return session_id, sandbox

    async def release_async(self, session_id: str) -> None:
        """Release a sandbox session back to the pool asynchronously.

        Args:
            session_id: Sandbox session ID
        """
        if session_id in self.active_sandboxes:
            sandbox = self.active_sandboxes.pop(session_id)
            try:
                await sandbox.kill()
            except Exception:
                pass  # Sandbox may already be terminated

    def shutdown(self) -> None:
        """Shutdown all sandbox sessions."""
        for session_id in list(self.active_sandboxes.keys()):
            self.release(session_id)
        self.available_sandboxes.clear()


class E2BExecutor(ExecutorBackend):
    """Executor that runs tests in e2b sandboxes for isolation and security."""

    # Path to the template mapping cache
    TEMPLATE_CACHE_PATH = Path(".evaluator/cache/template-mapping.json")

    def __init__(
        self,
        api_key: Optional[str] = None,
        max_sessions: int = 5,
        sandbox_config: Optional[SandboxConfig] = None,
        cache_dir: Optional[Path] = None,
    ) -> None:
        """Initialize e2b executor.

        Args:
            api_key: Anthropic API key. If None, uses ANTHROPIC_API_KEY env var.
            max_sessions: Maximum concurrent sandbox sessions
            sandbox_config: Default sandbox configuration
            cache_dir: Directory for template cache. If None, uses .evaluator/cache
        """
        self.agent = AgentInvoker(api_key=api_key)
        self.pool = SandboxPool(max_sessions=max_sessions)
        self.sandbox_config = sandbox_config or SandboxConfig()
        self.cache_dir = cache_dir or Path(".evaluator/cache")
        self._initialized = False
        self._template_cache: dict = {}

    def setup(self) -> None:
        """Set up e2b executor."""
        try:
            self.pool._get_e2b_module()
            self._initialized = True
        except ExecutionError:
            # e2b not available, will raise error on first test execution
            pass

    def teardown(self) -> None:
        """Clean up e2b resources."""
        self.pool.shutdown()

    def _load_template_cache(self) -> dict:
        """Load the template cache from disk.

        Returns:
            Dictionary with cached template information
        """
        if not self._template_cache:
            cache_path = self.cache_dir / "template-mapping.json"
            if cache_path.exists():
                with open(cache_path, "r") as f:
                    self._template_cache = json.load(f)
            else:
                self._template_cache = {"curated_templates": {}, "custom_templates": {}}
        return self._template_cache

    def _save_template_cache(self) -> None:
        """Save the template cache to disk."""
        cache_path = self.cache_dir / "template-mapping.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(self._template_cache, f, indent=2)

    def _hash_dockerfile(self, dockerfile_path: Path) -> str:
        """Compute SHA-256 hash of Dockerfile content.

        Args:
            dockerfile_path: Path to the Dockerfile

        Returns:
            Lowercase hex digest of SHA-256 hash
        """
        with open(dockerfile_path, "rb") as f:
            content = f.read()
        return hashlib.sha256(content).hexdigest()

    def _get_curated_template(self, name: str) -> Optional[str]:
        """Get template ID for a curated template.

        Args:
            name: Name of curated template (base, claude-tools, etc.)

        Returns:
            Template ID if exists and is built, None otherwise
        """
        cache = self._load_template_cache()
        if name in cache.get("curated_templates", {}):
            return cache["curated_templates"][name].get("template_id")
        return None

    def _get_cached_template(self, content_hash: str) -> Optional[str]:
        """Look up a custom template in the cache by content hash.

        Args:
            content_hash: SHA-256 hash of Dockerfile content

        Returns:
            Template ID if cached, None otherwise
        """
        cache = self._load_template_cache()
        return cache.get("custom_templates", {}).get(content_hash, {}).get("template_id")

    def _cache_template(
        self, identifier: str, template_id: str, dockerfile_path: Optional[Path] = None
    ) -> None:
        """Cache a template ID.

        Args:
            identifier: Either template name (curated) or content hash (custom)
            template_id: The e2b template ID
            dockerfile_path: Path to Dockerfile (for curated templates)
        """
        cache = self._load_template_cache()

        # Check if this is a curated template
        if identifier in cache.get("curated_templates", {}):
            cache["curated_templates"][identifier]["template_id"] = template_id
        else:
            # Custom template - use identifier as content hash
            if "custom_templates" not in cache:
                cache["custom_templates"] = {}
            cache["custom_templates"][identifier] = {
                "template_id": template_id,
                "dockerfile_path": str(dockerfile_path) if dockerfile_path else None,
            }

        self._template_cache = cache
        self._save_template_cache()

    def _build_template(self, dockerfile_path: Path) -> str:
        """Build a Dockerfile into an e2b template.

        Args:
            dockerfile_path: Path to the Dockerfile

        Returns:
            Template ID of the built template

        Raises:
            ExecutionError: If template building fails
        """
        try:
            # Get e2b module (needed for future SDK integration)
            _e2b = self.pool._get_e2b_module()  # noqa: F841

            # Read Dockerfile content (needed for future SDK integration)
            with open(dockerfile_path, "r") as f:
                _dockerfile_content = f.read()  # noqa: F841

            # Build template using e2b SDK
            # This is a placeholder - actual implementation would call e2b.build_template()
            # For now, generate a template ID based on the hash
            content_hash = self._hash_dockerfile(dockerfile_path)
            template_id = f"tmpl_{content_hash[:16]}"

            # TODO: Actual e2b SDK call
            # template = _e2b.build_template(
            #     dockerfile=_dockerfile_content,
            #     name=f"template-{content_hash[:8]}",
            # )
            # template_id = template.id

            return template_id
        except Exception as e:
            raise ExecutionError(f"Failed to build template from {dockerfile_path}: {str(e)}")

    def _build_or_get_template(
        self, dockerfile_path: Optional[Path] = None, template_name: Optional[str] = None
    ) -> str:
        """Get or build an e2b template.

        Args:
            dockerfile_path: Path to custom Dockerfile. If None, uses template_name.
            template_name: Name of curated template (base, claude-tools). Only used if dockerfile_path is None.

        Returns:
            Template ID for use with e2b

        Raises:
            ExecutionError: If template cannot be obtained
        """
        # Case 1: Curated template
        if dockerfile_path is None and template_name:
            cached_id = self._get_curated_template(template_name)
            if cached_id:
                return cached_id

            # Build curated template
            dockerfile_path = Path(".evaluator/environments") / f"{template_name}.Dockerfile"
            if not dockerfile_path.exists():
                raise ExecutionError(
                    f"Curated template '{template_name}' not found at {dockerfile_path}"
                )

            template_id = self._build_template(dockerfile_path)
            self._cache_template(template_name, template_id, dockerfile_path)
            return template_id

        # Case 2: Custom Dockerfile
        if dockerfile_path:
            if not dockerfile_path.exists():
                raise ExecutionError(f"Dockerfile not found: {dockerfile_path}")

            content_hash = self._hash_dockerfile(dockerfile_path)
            cached_id = self._get_cached_template(content_hash)
            if cached_id:
                return cached_id

            # Build custom template
            template_id = self._build_template(dockerfile_path)
            self._cache_template(content_hash, template_id, dockerfile_path)
            return template_id

        raise ExecutionError("Either dockerfile_path or template_name must be provided")

    def _inject_environment_vars(self, env_vars: dict, sandbox: Any) -> None:
        """Inject environment variables into a sandbox session.

        Args:
            env_vars: Dictionary of environment variables to inject
            sandbox: The e2b sandbox instance

        Raises:
            ExecutionError: If injection fails
        """
        try:
            if not isinstance(env_vars, dict):
                raise ExecutionError("Environment variables must be a dictionary")

            # Create export commands for each environment variable
            if env_vars:
                export_commands = [f'export {key}="{value}"' for key, value in env_vars.items()]
                export_script = " && ".join(export_commands)
                sandbox.commands.run(export_script)

        except Exception as e:
            raise ExecutionError(f"Failed to inject environment variables: {str(e)}")

    def _copy_instruction_files(self, instruction_file_path: Path, sandbox: Any) -> str:
        """Copy instruction files into a sandbox session.

        Args:
            instruction_file_path: Path to the instruction file (e.g., CLAUDE.md)
            sandbox: The e2b sandbox instance

        Returns:
            Path to the instruction file inside the sandbox

        Raises:
            ExecutionError: If copy fails
        """
        try:
            if not instruction_file_path.exists():
                raise ExecutionError(f"Instruction file not found: {instruction_file_path}")

            # Read file content and upload to sandbox
            with open(instruction_file_path, "r") as f:
                content = f.read()

            sandbox_path = f"/home/user/{instruction_file_path.name}"
            sandbox.files.write(sandbox_path, content)

            return sandbox_path

        except Exception as e:
            raise ExecutionError(f"Failed to copy instruction files: {str(e)}")

    def _upload_local_code(self, sandbox: Any) -> None:
        """Upload local evaluator code to sandbox."""
        import tarfile
        import io

        # Find source directory
        # Assuming we are running from root of repo
        src_path = Path("src/evaluator")
        if not src_path.exists():
            # Try to find installed package
            import evaluator

            if hasattr(evaluator, "__file__") and evaluator.__file__:
                src_path = Path(evaluator.__file__).parent
            else:
                print("Warning: Could not find evaluator source code to upload to sandbox.")
                return

        # Create tarball in memory
        f = io.BytesIO()
        with tarfile.open(fileobj=f, mode="w:gz") as tar:
            tar.add(src_path, arcname="evaluator")

        f.seek(0)
        content = f.read()

        # Write to sandbox
        sandbox.files.write("/tmp/evaluator.tar.gz", content)

        # Extract
        extract_result = sandbox.commands.run(
            "mkdir -p /home/user/pkg && tar -xzf /tmp/evaluator.tar.gz -C /home/user/pkg"
        )
        if extract_result.exit_code != 0:
            raise ExecutionError(
                f"Code upload failed: stdout={extract_result.stdout}, stderr={extract_result.stderr}"
            )

    def execute_test(
        self,
        test_case: TestCase,
        test_suite: TestSuite,
    ) -> ExecutionContext:
        """Execute test in e2b sandbox.

        Args:
            test_case: The test case to execute
            test_suite: The test suite context

        Returns:
            ExecutionContext with execution details
        """
        start_time = time.time()
        sandbox = None
        session_id = None

        # Get sandbox config from test suite metadata if available
        sandbox_config = SandboxConfig()
        if "sandbox_environment" in test_suite.metadata:
            config_dict = test_suite.metadata["sandbox_environment"]
            sandbox_config = SandboxConfig(**config_dict)

        try:
            # Step 1: Get template ID (None for default E2B sandbox)
            # Custom templates require E2B account setup - use None for default Python sandbox
            template_id = None
            if sandbox_config.custom_dockerfile:
                # Custom Dockerfile support requires E2B template building
                # For now, log a warning and use default
                print(
                    f"Warning: Custom Dockerfile {sandbox_config.custom_dockerfile} specified "
                    "but custom template building not yet implemented. Using default sandbox."
                )

            # Step 2: Acquire sandbox session with the template
            session_id, sandbox = self.pool.acquire(sandbox_config, template_id)

            # Step 3: Prepare environment variables (e.g., ANTHROPIC_API_KEY)
            # These will be passed directly to the command execution
            env_vars_to_inject = dict(sandbox_config.environment_vars)

            # Always inject API key if available
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                env_vars_to_inject["ANTHROPIC_API_KEY"] = api_key

            # Step 4: Copy instruction files to sandbox (if available)
            instruction_file = test_suite.metadata.get("instruction_file")
            sandbox_instruction_path = None
            if instruction_file and Path(instruction_file).exists():
                sandbox_instruction_path = self._copy_instruction_files(
                    Path(instruction_file), sandbox
                )
                print(f"[E2B] Copied instruction file to {sandbox_instruction_path}")
            else:
                print("[E2B] No instruction file found, running without instructions")

            # Step 5: Install dependencies and upload code
            # Install dependencies
            print("[E2B] Installing dependencies...")
            pip_result = sandbox.commands.run(
                "pip install anthropic pydantic pyyaml --quiet", timeout=120
            )
            if pip_result.exit_code != 0:
                raise ExecutionError(
                    f"pip install failed: stdout={pip_result.stdout}, stderr={pip_result.stderr}"
                )

            # Upload local code
            print("[E2B] Uploading local code...")
            self._upload_local_code(sandbox)

            # Create a Python script to run the agent and capture output
            agent_script = self._create_agent_script(
                task=test_case.task,
                instruction_file=sandbox_instruction_path,
                model=test_suite.model_under_test,
            )

            print(f"\n[REMOTE SCRIPT START]\n{agent_script}\n[REMOTE SCRIPT END]\n")

            # Write the agent script to sandbox
            print("[E2B] Writing agent script...")
            sandbox.files.write("/home/user/run_agent.py", agent_script)

            # Execute the agent script in sandbox
            print("[E2B] Executing agent script...")
            try:
                result = sandbox.commands.run(
                    "python /home/user/run_agent.py",
                    timeout=sandbox_config.timeout_seconds,
                    envs=env_vars_to_inject,  # Pass environment variables directly
                )
                print(f"[E2B] Script completed with exit_code={result.exit_code}")
            except Exception as cmd_error:
                # Try to extract output from the error
                error_str = str(cmd_error)
                print(f"[E2B] Script execution error: {error_str}")

                # E2B CommandExitException may have stdout/stderr attributes
                stdout = getattr(cmd_error, "stdout", "") or ""
                stderr = getattr(cmd_error, "stderr", error_str) or error_str
                exit_code = getattr(cmd_error, "exit_code", 1) or 1

                # Create a mock result object for error handling
                class MockResult:
                    pass

                result = MockResult()
                result.stdout = stdout
                result.stderr = stderr
                result.exit_code = exit_code

            # Parse agent response from output
            agent_response = self._parse_agent_output(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
                test_case=test_case,
                test_suite=test_suite,
            )

            execution_time_ms = (time.time() - start_time) * 1000

            # Step 6: Release sandbox session back to pool
            if session_id:
                self.pool.release(session_id)

            return ExecutionContext(
                agent_response=agent_response,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
                execution_time_ms=execution_time_ms,
                execution_mode="e2b",
                sandbox_info={
                    "session_id": session_id,
                    "template_id": template_id,
                    "template": sandbox_config.template or "base",
                    "timeout_seconds": sandbox_config.timeout_seconds,
                },
            )

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000

            # Clean up sandbox on error
            if session_id:
                try:
                    self.pool.release(session_id)
                except Exception:
                    pass

            return ExecutionContext(
                agent_response=None,  # type: ignore
                execution_time_ms=execution_time_ms,
                execution_mode="e2b",
                error_message=f"Sandbox execution failed: {str(e)}",
                exit_code=1,
            )

    async def execute_test_async(
        self,
        test_case: TestCase,
        test_suite: TestSuite,
    ) -> ExecutionContext:
        """Execute test in e2b sandbox asynchronously.

        Args:
            test_case: The test case to execute
            test_suite: The test suite context

        Returns:
            ExecutionContext with execution details
        """
        start_time = time.time()
        sandbox = None
        session_id = None

        # Get sandbox config from test suite metadata if available
        sandbox_config = SandboxConfig()
        if "sandbox_environment" in test_suite.metadata:
            config_dict = test_suite.metadata["sandbox_environment"]
            sandbox_config = SandboxConfig(**config_dict)

        try:
            # Step 1: Get template ID (None for default E2B sandbox)
            # Custom templates require E2B account setup - use None for default Python sandbox
            template_id = None
            if sandbox_config.custom_dockerfile:
                # Custom Dockerfile support requires E2B template building
                # For now, log a warning and use default
                print(
                    f"Warning: Custom Dockerfile {sandbox_config.custom_dockerfile} specified "
                    "but custom template building not yet implemented. Using default sandbox."
                )

            # Step 2: Acquire sandbox session with the template (async)
            session_id, sandbox = await self.pool.acquire_async(sandbox_config, template_id)

            # Step 3: Prepare environment variables (e.g., ANTHROPIC_API_KEY)
            # These will be passed directly to the command execution
            env_vars_to_inject = dict(sandbox_config.environment_vars)

            # Always inject API key if available
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                env_vars_to_inject["ANTHROPIC_API_KEY"] = api_key

            # Step 4: Copy instruction files to sandbox (if available)
            instruction_file = test_suite.metadata.get("instruction_file")
            sandbox_instruction_path = None
            if instruction_file and Path(instruction_file).exists():
                sandbox_instruction_path = await self._copy_instruction_files_async(
                    Path(instruction_file), sandbox
                )
                print(f"[E2B] Copied instruction file to {sandbox_instruction_path}")
            else:
                print("[E2B] No instruction file found, running without instructions")

            # Step 5: Install dependencies and upload code
            # Install dependencies
            print("[E2B] Installing dependencies...")
            pip_result = await sandbox.commands.run(
                "pip install anthropic pydantic pyyaml --quiet", timeout=120
            )
            if pip_result.exit_code != 0:
                raise ExecutionError(
                    f"pip install failed: stdout={pip_result.stdout}, stderr={pip_result.stderr}"
                )

            # Upload local code
            print("[E2B] Uploading local code...")
            await self._upload_local_code_async(sandbox)

            # Create a Python script to run the agent and capture output
            agent_script = self._create_agent_script(
                task=test_case.task,
                instruction_file=sandbox_instruction_path or instruction_file,
                model=test_suite.model_under_test,
            )

            print(f"\n[REMOTE SCRIPT START]\n{agent_script}\n[REMOTE SCRIPT END]\n")

            # Write the agent script to sandbox
            print("[E2B] Writing agent script...")
            await sandbox.files.write("/home/user/run_agent.py", agent_script)

            # Execute the agent script in sandbox and wait for completion
            print("[E2B] Executing agent script...")
            try:
                result = await sandbox.commands.run(
                    "python /home/user/run_agent.py",
                    timeout=sandbox_config.timeout_seconds,
                    envs=env_vars_to_inject,  # Pass environment variables directly
                )
                print(f"[E2B] Script completed with exit_code={result.exit_code}")
                print(f"[E2B] stdout: {result.stdout[:500] if result.stdout else '(empty)'}")
                print(f"[E2B] stderr: {result.stderr[:500] if result.stderr else '(empty)'}")
            except Exception as cmd_error:
                # Try to extract output from the error
                error_str = str(cmd_error)
                print(f"[E2B] Script execution error: {error_str}")
                print(f"[E2B] Exception type: {type(cmd_error)}")
                print(f"[E2B] Exception attributes: {dir(cmd_error)}")

                # E2B CommandExitException may have stdout/stderr attributes
                stdout = getattr(cmd_error, "stdout", "") or ""
                stderr = getattr(cmd_error, "stderr", error_str) or error_str
                exit_code = getattr(cmd_error, "exit_code", 1) or 1

                print(f"[E2B] Extracted stdout: {stdout[:500] if stdout else '(empty)'}")
                print(f"[E2B] Extracted stderr: {stderr[:500] if stderr else '(empty)'}")

                # Create a mock result object for error handling
                class MockResult:
                    pass

                result = MockResult()
                result.stdout = stdout
                result.stderr = stderr
                result.exit_code = exit_code

            # Parse agent response from output
            agent_response = self._parse_agent_output(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
                test_case=test_case,
                test_suite=test_suite,
            )

            execution_time_ms = (time.time() - start_time) * 1000

            # Step 6: Release sandbox session back to pool
            if session_id:
                await self.pool.release_async(session_id)

            return ExecutionContext(
                agent_response=agent_response,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
                execution_time_ms=execution_time_ms,
                execution_mode="e2b",
                sandbox_info={
                    "session_id": session_id,
                    "template_id": template_id,
                    "template": sandbox_config.template or "base",
                    "timeout_seconds": sandbox_config.timeout_seconds,
                },
            )

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000

            # Clean up sandbox on error
            if session_id:
                try:
                    await self.pool.release_async(session_id)
                except Exception:
                    pass

            return ExecutionContext(
                agent_response=None,  # type: ignore
                execution_time_ms=execution_time_ms,
                execution_mode="e2b",
                error_message=f"Sandbox execution failed: {str(e)}",
                exit_code=1,
            )

    async def _inject_environment_vars_async(self, env_vars: dict, sandbox: Any) -> None:
        """Inject environment variables into a sandbox session asynchronously.

        Args:
            env_vars: Dictionary of environment variables to inject
            sandbox: The e2b sandbox instance

        Raises:
            ExecutionError: If injection fails
        """
        try:
            if not isinstance(env_vars, dict):
                raise ExecutionError("Environment variables must be a dictionary")

            # Create export commands for each environment variable
            if env_vars:
                export_commands = [f'export {key}="{value}"' for key, value in env_vars.items()]
                export_script = " && ".join(export_commands)
                await sandbox.commands.run(export_script)

        except Exception as e:
            raise ExecutionError(f"Failed to inject environment variables: {str(e)}")

    async def _copy_instruction_files_async(self, instruction_file_path: Path, sandbox: Any) -> str:
        """Copy instruction files into a sandbox session asynchronously.

        Args:
            instruction_file_path: Path to the instruction file (e.g., CLAUDE.md)
            sandbox: The e2b sandbox instance

        Returns:
            Path to the instruction file inside the sandbox

        Raises:
            ExecutionError: If copy fails
        """
        try:
            if not instruction_file_path.exists():
                raise ExecutionError(f"Instruction file not found: {instruction_file_path}")

            # Read file content and upload to sandbox
            with open(instruction_file_path, "r") as f:
                content = f.read()

            sandbox_path = f"/home/user/{instruction_file_path.name}"
            await sandbox.files.write(sandbox_path, content)

            return sandbox_path

        except Exception as e:
            raise ExecutionError(f"Failed to copy instruction files: {str(e)}")

    async def _upload_local_code_async(self, sandbox: Any) -> None:
        """Upload local evaluator code to sandbox asynchronously."""
        import tarfile
        import io

        # Find source directory
        # Assuming we are running from root of repo
        src_path = Path("src/evaluator")
        if not src_path.exists():
            # Try to find installed package
            import evaluator

            if hasattr(evaluator, "__file__") and evaluator.__file__:
                src_path = Path(evaluator.__file__).parent
            else:
                print("Warning: Could not find evaluator source code to upload to sandbox.")
                return

        # Create tarball in memory
        f = io.BytesIO()
        with tarfile.open(fileobj=f, mode="w:gz") as tar:
            tar.add(src_path, arcname="evaluator")

        f.seek(0)
        content = f.read()

        # Write to sandbox
        await sandbox.files.write("/tmp/evaluator.tar.gz", content)

        # Extract
        extract_result = await sandbox.commands.run(
            "mkdir -p /home/user/pkg && tar -xzf /tmp/evaluator.tar.gz -C /home/user/pkg"
        )
        if extract_result.exit_code != 0:
            raise ExecutionError(
                f"Code upload failed: stdout={extract_result.stdout}, stderr={extract_result.stderr}"
            )

    def _create_agent_script(
        self,
        task: str,
        instruction_file: Optional[str],
        model: str,
    ) -> str:
        """Create Python script to run agent in sandbox.

        Args:
            task: The task to execute
            instruction_file: Path to instruction file (or None)
            model: Model to use

        Returns:
            Python script as string
        """
        # Escape task for embedding in script
        escaped_task = task.replace('"""', r"\"\"\"").replace("\\", "\\\\")

        # Handle optional instruction file
        if instruction_file:
            instruction_file_arg = f'instruction_file_path="{instruction_file}",'
        else:
            instruction_file_arg = "instruction_file_path=None,"

        return f'''#!/usr/bin/env python3
"""Agent execution script for sandbox."""

import json
import os
import sys

# Add uploaded package to path
sys.path.append("/home/user/pkg")

# Ensure ANTHROPIC_API_KEY is available
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    print(json.dumps({{"error": "ANTHROPIC_API_KEY not set"}}))
    sys.exit(1)

from evaluator.agent import AgentInvoker

try:
    agent = AgentInvoker(api_key=api_key)
    response = agent.invoke(
        task="""{escaped_task}""",
        {instruction_file_arg}
        model="{model}",
    )
    
    # Output response as JSON for parsing
    output = {{
        "full_response": response.full_response,
        "generated_code": response.generated_code,
        "generated_commands": response.generated_commands,
        "tool_calls": response.tool_calls,
        "conversation_trace": response.conversation_trace,
        "task": response.task,
        "model": response.model,
        "instruction_file_path": response.instruction_file_path,
    }}
    print("---AGENT_OUTPUT_START---")
    print(json.dumps(output))
    print("---AGENT_OUTPUT_END---")
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
    sys.exit(1)
'''

    def _parse_agent_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        test_case: TestCase,
        test_suite: TestSuite,
    ) -> "AgentResponse":
        """Parse agent output from sandbox execution.

        Args:
            stdout: Standard output from sandbox
            stderr: Standard error from sandbox
            exit_code: Exit code from sandbox
            test_case: The test case being executed
            test_suite: The test suite context

        Returns:
            AgentResponse parsed from output
        """
        from evaluator.models import AgentResponse

        try:
            # Extract JSON output between markers
            start_marker = "---AGENT_OUTPUT_START---"
            end_marker = "---AGENT_OUTPUT_END---"

            if start_marker in stdout and end_marker in stdout:
                start = stdout.index(start_marker) + len(start_marker)
                end = stdout.index(end_marker)
                json_str = stdout[start:end].strip()
                data = json.loads(json_str)

                if "error" in data:
                    raise ExecutionError(data["error"])

                return AgentResponse(
                    task=data.get("task", test_case.task),
                    full_response=data.get("full_response", ""),
                    generated_code=data.get("generated_code", []),
                    generated_commands=data.get("generated_commands", []),
                    tool_calls=data.get("tool_calls", []),
                    conversation_trace=data.get("conversation_trace", []),
                    model=data.get("model", test_suite.model_under_test),
                    instruction_file_path=data.get(
                        "instruction_file_path",
                        test_suite.metadata.get("instruction_file", ""),
                    ),
                )
            else:
                # Fallback: return raw output as response
                return AgentResponse(
                    task=test_case.task,
                    full_response=stdout or stderr or "No output",
                    model=test_suite.model_under_test,
                    instruction_file_path=test_suite.metadata.get("instruction_file", ""),
                )

        except json.JSONDecodeError as e:
            return AgentResponse(
                task=test_case.task,
                full_response=f"Failed to parse agent output: {e}\nStdout: {stdout}\nStderr: {stderr}",
                model=test_suite.model_under_test,
                instruction_file_path=test_suite.metadata.get("instruction_file", ""),
            )
