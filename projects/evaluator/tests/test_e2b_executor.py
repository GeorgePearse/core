"""Unit tests for E2BExecutor template building and caching."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from evaluator.executors.base import ExecutionError
from evaluator.executors.e2b import E2BExecutor


class TestE2BExecutorTemplateBuilding:
    """Test suite for E2BExecutor template building functionality."""

    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary cache directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def temp_env_dir(self):
        """Create temporary environment directory with sample Dockerfiles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_dir = Path(tmpdir) / "environments"
            env_dir.mkdir()

            # Create base Dockerfile
            base_dockerfile = env_dir / "base.Dockerfile"
            base_dockerfile.write_text("""FROM python:3.11-slim
RUN apt-get update
RUN pip install anthropic
""")

            # Create claude-tools Dockerfile
            tools_dockerfile = env_dir / "claude-tools.Dockerfile"
            tools_dockerfile.write_text("""FROM python:3.11-slim
RUN apt-get update
RUN pip install anthropic
RUN cargo install ripgrep
""")

            yield env_dir

    @pytest.fixture
    def executor(self, temp_cache_dir):
        """Create an E2BExecutor with temporary cache."""
        with patch("evaluator.executors.e2b.AgentInvoker"):
            executor = E2BExecutor(cache_dir=temp_cache_dir)
            yield executor

    def test_hash_dockerfile(self, executor, temp_env_dir):
        """Test SHA-256 hashing of Dockerfile content."""
        dockerfile_path = temp_env_dir / "base.Dockerfile"

        # Compute hash
        hash_result = executor._hash_dockerfile(dockerfile_path)

        # Verify hash is lowercase hex
        assert isinstance(hash_result, str)
        assert len(hash_result) == 64  # SHA-256 hex is 64 chars
        assert hash_result == hash_result.lower()

        # Verify hash is consistent
        hash_result2 = executor._hash_dockerfile(dockerfile_path)
        assert hash_result == hash_result2

    def test_hash_dockerfile_different_content(self, executor, temp_env_dir):
        """Test that different Dockerfiles produce different hashes."""
        dockerfile1 = temp_env_dir / "base.Dockerfile"
        dockerfile2 = temp_env_dir / "claude-tools.Dockerfile"

        hash1 = executor._hash_dockerfile(dockerfile1)
        hash2 = executor._hash_dockerfile(dockerfile2)

        assert hash1 != hash2

    def test_load_template_cache_from_disk(self, executor, temp_cache_dir):
        """Test loading template cache from disk."""
        # Create a template cache file
        cache_data = {
            "curated_templates": {
                "base": {"template_id": "tmpl_abc123"},
            },
            "custom_templates": {},
        }
        cache_path = temp_cache_dir / "template-mapping.json"
        with open(cache_path, "w") as f:
            json.dump(cache_data, f)

        # Load cache
        cache = executor._load_template_cache()

        assert cache["curated_templates"]["base"]["template_id"] == "tmpl_abc123"

    def test_load_template_cache_creates_default(self, executor, temp_cache_dir):
        """Test that loading non-existent cache creates default structure."""
        # Don't create cache file
        cache = executor._load_template_cache()

        assert "curated_templates" in cache
        assert "custom_templates" in cache
        assert cache["curated_templates"] == {}
        assert cache["custom_templates"] == {}

    def test_save_template_cache(self, executor, temp_cache_dir):
        """Test saving template cache to disk."""
        executor._template_cache = {
            "curated_templates": {
                "base": {"template_id": "tmpl_xyz789"},
            },
            "custom_templates": {},
        }

        executor._save_template_cache()

        # Verify file was created
        cache_path = temp_cache_dir / "template-mapping.json"
        assert cache_path.exists()

        # Verify contents
        with open(cache_path) as f:
            saved_data = json.load(f)
        assert saved_data["curated_templates"]["base"]["template_id"] == "tmpl_xyz789"

    def test_get_curated_template_exists(self, executor, temp_cache_dir):
        """Test getting a curated template that exists in cache."""
        # Set up cache
        executor._template_cache = {
            "curated_templates": {
                "base": {"template_id": "tmpl_abc123"},
                "claude-tools": {"template_id": "tmpl_def456"},
            },
            "custom_templates": {},
        }

        template_id = executor._get_curated_template("base")
        assert template_id == "tmpl_abc123"

    def test_get_curated_template_not_exists(self, executor):
        """Test getting a curated template that doesn't exist."""
        executor._template_cache = {"curated_templates": {}, "custom_templates": {}}

        template_id = executor._get_curated_template("base")
        assert template_id is None

    def test_get_cached_template_exists(self, executor):
        """Test getting a cached custom template by hash."""
        content_hash = "abc123def456"
        executor._template_cache = {
            "curated_templates": {},
            "custom_templates": {content_hash: {"template_id": "tmpl_custom123"}},
        }

        template_id = executor._get_cached_template(content_hash)
        assert template_id == "tmpl_custom123"

    def test_get_cached_template_not_exists(self, executor):
        """Test getting a custom template that doesn't exist."""
        executor._template_cache = {"curated_templates": {}, "custom_templates": {}}

        template_id = executor._get_cached_template("nonexistent_hash")
        assert template_id is None

    def test_cache_template_curated(self, executor):
        """Test caching a curated template."""
        # Set up initial cache
        executor._template_cache = {
            "curated_templates": {
                "base": {
                    "template_id": None,
                    "dockerfile": ".evaluator/environments/base.Dockerfile",
                },
            },
            "custom_templates": {},
        }

        # Cache the template
        executor._cache_template("base", "tmpl_new123")

        assert executor._template_cache["curated_templates"]["base"]["template_id"] == "tmpl_new123"

    def test_cache_template_custom(self, executor, temp_env_dir):
        """Test caching a custom template."""
        executor._template_cache = {"curated_templates": {}, "custom_templates": {}}

        content_hash = "custom_hash_123"
        dockerfile_path = temp_env_dir / "base.Dockerfile"

        executor._cache_template(content_hash, "tmpl_custom789", dockerfile_path)

        assert (
            executor._template_cache["custom_templates"][content_hash]["template_id"]
            == "tmpl_custom789"
        )
        assert executor._template_cache["custom_templates"][content_hash]["dockerfile_path"] == str(
            dockerfile_path
        )

    def test_build_template_generates_template_id(self, executor, temp_env_dir):
        """Test that _build_template generates a template ID."""
        dockerfile_path = temp_env_dir / "base.Dockerfile"

        with patch.object(executor.pool, "_get_e2b_module"):
            template_id = executor._build_template(dockerfile_path)

        # Should be in format: tmpl_<first 16 chars of hash>
        assert template_id.startswith("tmpl_")
        assert len(template_id) == 21  # tmpl_ (5) + 16 chars

    def test_build_template_file_not_found(self, executor):
        """Test that _build_template raises error for non-existent Dockerfile."""
        with patch.object(executor.pool, "_get_e2b_module"):
            with pytest.raises(ExecutionError, match="Failed to build template"):
                executor._build_template(Path("nonexistent.Dockerfile"))

    def test_build_or_get_template_curated_cached(self, executor):
        """Test _build_or_get_template returns cached curated template."""
        # Set up cache with existing template
        executor._template_cache = {
            "curated_templates": {
                "base": {"template_id": "tmpl_cached123"},
            },
            "custom_templates": {},
        }

        with patch.object(executor, "_build_template") as mock_build:
            template_id = executor._build_or_get_template(template_name="base")

        # Should return cached template without building
        assert template_id == "tmpl_cached123"
        mock_build.assert_not_called()

    def test_build_or_get_template_curated_not_cached(self, executor, temp_env_dir, monkeypatch):
        """Test _build_or_get_template builds uncached curated template."""
        # Change to temp environment directory parent so .evaluator/environments path exists
        env_parent = temp_env_dir.parent
        monkeypatch.chdir(env_parent)

        # Create .evaluator/environments structure in current directory
        env_dir = Path(".evaluator/environments")
        env_dir.mkdir(parents=True, exist_ok=True)
        base_dockerfile = env_dir / "base.Dockerfile"
        base_dockerfile.write_text("FROM python:3.11-slim\nRUN pip install anthropic\n")

        executor._template_cache = {
            "curated_templates": {
                "base": {
                    "dockerfile": ".evaluator/environments/base.Dockerfile",
                    "template_id": None,
                },
            },
            "custom_templates": {},
        }

        with patch.object(executor.pool, "_get_e2b_module"):
            template_id = executor._build_or_get_template(template_name="base")

        # Should build new template
        assert template_id.startswith("tmpl_")
        # Cache should be updated
        assert executor._template_cache["curated_templates"]["base"]["template_id"] == template_id

    def test_build_or_get_template_custom_cached(self, executor, temp_env_dir):
        """Test _build_or_get_template returns cached custom Dockerfile."""
        dockerfile_path = temp_env_dir / "base.Dockerfile"
        content_hash = executor._hash_dockerfile(dockerfile_path)

        executor._template_cache = {
            "curated_templates": {},
            "custom_templates": {content_hash: {"template_id": "tmpl_custom_cached"}},
        }

        with patch.object(executor, "_build_template") as mock_build:
            template_id = executor._build_or_get_template(dockerfile_path=dockerfile_path)

        # Should return cached template without building
        assert template_id == "tmpl_custom_cached"
        mock_build.assert_not_called()

    def test_build_or_get_template_custom_not_cached(self, executor, temp_env_dir):
        """Test _build_or_get_template builds uncached custom Dockerfile."""
        dockerfile_path = temp_env_dir / "base.Dockerfile"

        executor._template_cache = {"curated_templates": {}, "custom_templates": {}}

        with patch.object(executor.pool, "_get_e2b_module"):
            template_id = executor._build_or_get_template(dockerfile_path=dockerfile_path)

        # Should build new template
        assert template_id.startswith("tmpl_")
        # Cache should be updated
        content_hash = executor._hash_dockerfile(dockerfile_path)
        assert (
            executor._template_cache["custom_templates"][content_hash]["template_id"] == template_id
        )

    def test_build_or_get_template_no_args_raises_error(self, executor):
        """Test that _build_or_get_template raises error with no arguments."""
        with pytest.raises(
            ExecutionError, match="Either dockerfile_path or template_name must be provided"
        ):
            executor._build_or_get_template()

    def test_inject_environment_vars_validates_input(self, executor):
        """Test that _inject_environment_vars validates input."""
        from unittest.mock import MagicMock

        # Create a mock sandbox object
        mock_sandbox = MagicMock()
        mock_sandbox.commands.run.return_value = None

        # Should not raise with valid dict
        executor._inject_environment_vars({"KEY": "value"}, mock_sandbox)
        mock_sandbox.commands.run.assert_called_once()

        # Should raise with non-dict
        with pytest.raises(ExecutionError, match="must be a dictionary"):
            executor._inject_environment_vars("not a dict", mock_sandbox)

    def test_copy_instruction_files_file_not_found(self, executor):
        """Test that _copy_instruction_files raises error for non-existent file."""
        with pytest.raises(ExecutionError, match="Instruction file not found"):
            executor._copy_instruction_files(Path("nonexistent.md"), "session_123")

    def test_copy_instruction_files_validates_path(self, executor, temp_env_dir):
        """Test that _copy_instruction_files validates file existence."""
        from unittest.mock import MagicMock

        instruction_file = temp_env_dir / "CLAUDE.md"
        instruction_file.write_text("# Instructions")

        # Create a mock sandbox object
        mock_sandbox = MagicMock()
        mock_sandbox.files.write.return_value = None

        # Should not raise with existing file
        result = executor._copy_instruction_files(instruction_file, mock_sandbox)
        mock_sandbox.files.write.assert_called_once()
        assert result == f"/workspace/{instruction_file.name}"


class TestE2BExecutorCaching:
    """Integration tests for template caching behavior."""

    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary cache directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def temp_env_dir(self):
        """Create temporary environment directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_dir = Path(tmpdir) / "environments"
            env_dir.mkdir()
            base_dockerfile = env_dir / "base.Dockerfile"
            base_dockerfile.write_text("FROM python:3.11-slim\nRUN pip install anthropic\n")
            yield env_dir

    def test_template_cache_persistence(self, temp_cache_dir, temp_env_dir, monkeypatch):
        """Test that template cache persists across executor instances."""
        monkeypatch.chdir(temp_env_dir.parent)

        with patch("evaluator.executors.e2b.AgentInvoker"):
            # First executor builds template
            executor1 = E2BExecutor(cache_dir=temp_cache_dir)
            executor1._template_cache = {
                "curated_templates": {
                    "base": {"template_id": "tmpl_persistent123"},
                },
                "custom_templates": {},
            }
            executor1._save_template_cache()

            # Second executor should load same cache
            executor2 = E2BExecutor(cache_dir=temp_cache_dir)
            cache = executor2._load_template_cache()

            assert cache["curated_templates"]["base"]["template_id"] == "tmpl_persistent123"

    def test_custom_dockerfile_cache_by_content_hash(self, temp_cache_dir, temp_env_dir):
        """Test that custom Dockerfiles are cached by content hash."""
        dockerfile1 = temp_env_dir / "custom1.Dockerfile"
        dockerfile1.write_text("FROM python:3.11\nRUN pip install anthropic\n")

        dockerfile2 = temp_env_dir / "custom2.Dockerfile"
        dockerfile2.write_text(
            "FROM python:3.11\nRUN pip install anthropic\nRUN pip install pydantic\n"
        )

        with patch("evaluator.executors.e2b.AgentInvoker"):
            executor = E2BExecutor(cache_dir=temp_cache_dir)

            with patch.object(executor.pool, "_get_e2b_module"):
                # Build first custom template
                template_id1 = executor._build_or_get_template(dockerfile_path=dockerfile1)

                # Build second custom template
                template_id2 = executor._build_or_get_template(dockerfile_path=dockerfile2)

                # Should have different template IDs (different content)
                assert template_id1 != template_id2

                # Building again with same content should return cached ID
                template_id1_again = executor._build_or_get_template(dockerfile_path=dockerfile1)
                assert template_id1 == template_id1_again
