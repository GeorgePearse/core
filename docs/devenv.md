# Development Environment (devenv + Nix)

Genesis uses [devenv](https://devenv.sh/) to provide a fully reproducible development environment. A single command gives you Python 3.12, Rust stable, Node.js, uv, Terraform, Liquibase, PostgreSQL, and every other tool the monorepo needs.

## Prerequisites

Install Nix and devenv:

```bash
# Install Nix (Determinate Systems installer recommended)
curl --proto '=https' --tlsv1.2 -sSf -L https://install.determinate.systems/nix | sh -s -- install

# Install devenv
nix-env -if https://install.devenv.sh/latest
```

Optionally, install [direnv](https://direnv.net/) for automatic shell activation:

```bash
# macOS
brew install direnv

# Or via Nix
nix-env -i direnv
```

Add the direnv hook to your shell (e.g. in `~/.bashrc` or `~/.zshrc`):

```bash
eval "$(direnv hook bash)"   # or zsh, fish
```

## Getting Started

```bash
cd core   # the repo root

# Option A: Manual activation
devenv shell

# Option B: Automatic via direnv (if installed)
direnv allow
# The environment activates automatically whenever you cd into the repo.
```

On first run, Nix downloads and caches all dependencies. Subsequent activations are near-instant.

## What's Included

| Category | Tools |
|----------|-------|
| **Python** | Python 3.12, uv, ruff |
| **Rust** | Rust stable, cargo, clippy, rustfmt, maturin |
| **Node** | Node.js 20+, npm |
| **Infrastructure** | Terraform, Liquibase, hadolint |
| **Database** | PostgreSQL 15 (managed service + client tools) |
| **Dev utilities** | just, OpenBLAS |
| **Quality** | prek, ty (installed via `uv tool` on first shell entry) |

## Services

devenv manages a local PostgreSQL instance automatically:

```bash
# Start services (happens automatically in devenv shell)
devenv up

# PostgreSQL is available at localhost:5432, database "genesis"
psql genesis
```

The `docker-compose.yml` still works if you prefer Docker-based Postgres.

## Common Workflows

```bash
# Install Python project in editable mode
uv pip install -e ".[dev]"

# Run evolution experiment
genesis_launch variant=circle_packing_example

# Build Rust backend
cd lib/rust && cargo build --release

# Build squeeze Rust extension
cd projects/squeeze && just install

# Run pre-commit hooks
prek run --all-files

# Run type checker
ty check lib/python/genesis/
```

## Troubleshooting

**`devenv shell` is slow on first run**: This is expected -- Nix is downloading all dependencies. Subsequent runs use the local store cache and are fast.

**`prek` or `ty` not found**: These are installed via `uv tool` on first shell entry. Run `uv tool install prek && uv tool install ty` manually if the automatic install was skipped.

**Port 5432 already in use**: Another PostgreSQL instance (e.g. from Docker) may be running. Stop it first, or change the port in `devenv.nix`.

**direnv not activating**: Run `direnv allow` in the repo root after cloning. Ensure the direnv hook is in your shell rc file.
