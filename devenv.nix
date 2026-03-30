{ pkgs, lib, ... }:

{
  # --- Languages ---
  languages.python = {
    enable = true;
    version = "3.12";
    uv = {
      enable = true;
      sync.enable = false;
    };
  };

  languages.rust = {
    enable = true;
    channel = "stable";
    components = [ "rustfmt" "clippy" ];
  };

  languages.javascript = {
    enable = true;
    npm.enable = true;
  };

  # --- Native dependencies & CLI tools ---
  packages = with pkgs; [
    # Infrastructure
    terraform
    liquibase
    hadolint

    # Database client (psql, pg_dump for DDL sync)
    postgresql_15

    # Build tooling
    just
    maturin
    openblas

    # Python quality tools available in nixpkgs
    ruff
  ];

  # --- Services ---
  services.postgres = {
    enable = true;
    package = pkgs.postgresql_15;
    initialDatabases = [{ name = "genesis"; }];
    port = 5432;
    listen_addresses = "127.0.0.1";
  };

  # --- Environment variables ---
  env = {
    DATABASE_URL = "postgresql://localhost:5432/genesis";
    RUST_LOG = "info";
    CARGO_TERM_COLOR = "always";
  };

  # --- Pre-commit hooks (devenv-managed) ---
  pre-commit.hooks = {
    ruff.enable = true;
    ruff-format.enable = true;
  };

  # --- Shell startup ---
  enterShell = ''
    echo ""
    echo "Genesis dev environment ready"
    echo "  Python: $(python --version 2>&1)"
    echo "  Rust:   $(rustc --version 2>&1)"
    echo "  Node:   $(node --version 2>&1)"
    echo "  uv:     $(uv --version 2>&1)"
    echo ""

    # Install prek and ty via uv (not yet in nixpkgs)
    if ! command -v prek &> /dev/null; then
      echo "Installing prek and ty via uv tool..."
      uv tool install prek 2>/dev/null || true
      uv tool install ty 2>/dev/null || true
    fi
  '';
}
