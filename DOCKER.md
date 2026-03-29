# Genesis Docker Setup

This guide explains how to run the Genesis Evolution Platform using Docker and Docker Compose.

## Prerequisites

- Docker Engine 20.10+ or Docker Desktop
- Docker Compose 2.0+
- At least 4GB available RAM
- API keys for OpenAI and/or Anthropic

## Quick Start

1. **Copy the environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` and add your API keys:**
   ```bash
   # Required: At least one LLM provider
   OPENAI_API_KEY=sk-your-openai-api-key-here
   ANTHROPIC_API_KEY=sk-ant-your-anthropic-api-key-here

   # Optional: E2B for cloud sandbox execution
   E2B_API_KEY=your-e2b-api-key-here
   ```

3. **Build and start the containers:**
   ```bash
   docker-compose up -d
   ```

4. **View logs:**
   ```bash
   docker-compose logs -f backend
   ```

5. **Access the Web UI:**
   Open your browser to [http://localhost:8000](http://localhost:8000)

## Architecture

The Docker setup includes:

- **Backend Service** (`genesis-backend`): Python 3.12 application running the Genesis evolution framework and web UI
- **Persistent Volumes**: Data and results are stored in `./data` and `./results` directories

## Services

### Backend Service

The backend container runs:
- Genesis evolution framework (`genesis` Python package)
- Web UI visualization server (port 8000)
- Evolution experiments via `genesis_launch` command

**Environment Variables:**
- `GENESIS_DATA_DIR`: Directory for database files (default: `/app/data`)
- `GENESIS_RESULTS_DIR`: Directory for results (default: `/app/results`)
- `OPENAI_API_KEY`: OpenAI API key
- `ANTHROPIC_API_KEY`: Anthropic API key
- `E2B_API_KEY`: E2B cloud sandbox API key (optional)

## Volume Mounts

The Docker Compose setup mounts the following directories:

| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| `./data` | `/app/data` | SQLite databases and metadata |
| `./results` | `/app/results` | Experiment results and outputs |
| `./genesis` | `/app/genesis` | Source code (dev mode only) |
| `./configs` | `/app/configs` | Configuration files (dev mode only) |
| `./examples` | `/app/examples` | Example experiments (dev mode only) |

## Development vs Production

### Development Mode (Default)

The default `docker-compose.yml` mounts source code for live development:

```yaml
volumes:
  - ./genesis:/app/genesis
  - ./configs:/app/configs
  - ./examples:/app/examples
```

Changes to Python files are immediately available inside the container.

### Production Mode

For production deployments, comment out the source code volume mounts in `docker-compose.yml`:

```yaml
volumes:
  # Mount directories for persistent data
  - ./data:/app/data
  - ./results:/app/results

  # Mount source code for development (comment out for production)
  # - ./genesis:/app/genesis
  # - ./configs:/app/configs
  # - ./examples:/app/examples
```

Then rebuild the image to bake in the code:

```bash
docker-compose build
docker-compose up -d
```

## Common Commands

### Start services:
```bash
docker-compose up -d
```

### Stop services:
```bash
docker-compose down
```

### View logs:
```bash
# Backend only
docker-compose logs -f backend
```

### Rebuild after code changes:
```bash
docker-compose build backend
docker-compose up -d backend
```

### Execute commands in the backend container:
```bash
# Start a bash shell
docker-compose exec backend bash

# Run an evolution experiment
docker-compose exec backend genesis_launch variant=circle_packing_example

# Check Python version
docker-compose exec backend python --version
```

### Clean up everything (including volumes):
```bash
docker-compose down -v
rm -rf data/ results/
```

## Running Evolution Experiments

### From the Host

Execute experiments directly using docker-compose:

```bash
docker-compose exec backend genesis_launch variant=circle_packing_example
```

### Inside the Container

Enter the container and run commands:

```bash
docker-compose exec backend bash
cd /app
genesis_launch variant=circle_packing_example
```

### Custom Experiments

Place your experiment files in the mounted directories:

```bash
# On your host machine
mkdir -p examples/my_experiment
# Add your initial.py and evaluate.py
```

Then run:

```bash
docker-compose exec backend genesis_launch \
  evo_config.init_program_path=/app/examples/my_experiment/initial.py \
  cluster.eval_program_path=/app/examples/my_experiment/evaluate.py
```

## Web UI Access

The Genesis Web UI is accessible at [http://localhost:8000](http://localhost:8000) once the backend service is running.

To change the port, modify `.env`:

```bash
GENESIS_WEBUI_PORT=8080
```

Then restart:

```bash
docker-compose down
docker-compose up -d
```

## Troubleshooting

### Port Already in Use

If port 8000 is already in use, change the port mapping in `.env`:

```bash
GENESIS_WEBUI_PORT=8080
```

### Out of Memory

Increase Docker's memory allocation:
- **Docker Desktop**: Settings → Resources → Memory → Increase to 8GB
- **Linux**: Ensure host has sufficient RAM

### Container Won't Start

Check logs for errors:

```bash
docker-compose logs backend
```

Common issues:
- Missing API keys in `.env`
- Invalid environment variables
- Port conflicts
- Insufficient disk space

### Permission Issues

If you encounter permission errors with mounted volumes:

```bash
# Fix ownership (Linux/macOS)
sudo chown -R $(whoami):$(id -gn) data/ results/

# Or run with proper permissions
docker-compose run --user $(id -u):$(id -g) backend bash
```

## Advanced Configuration

### Custom Docker Compose Override

Create a `docker-compose.override.yml` for local customizations:

```yaml
version: '3.8'

services:
  backend:
    environment:
      - CUSTOM_VAR=value
    ports:
      - "9000:8000"
```

### Build Arguments

Customize the Docker build:

```bash
docker-compose build --build-arg PYTHON_VERSION=3.12.4 backend
```

### Resource Limits

Add resource limits in `docker-compose.yml`:

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
```

## Security Considerations

1. **Never commit `.env` file** - It contains sensitive API keys
2. **Use secrets management** for production deployments:
   ```bash
   docker secret create openai_key ./openai_key.txt
   ```
3. **Regular updates**: Rebuild images to get security patches
   ```bash
   docker-compose pull
   docker-compose build --no-cache
   ```

## Support

For issues related to:
- **Docker setup**: Check this document and logs
- **Genesis framework**: See [README.md](README.md) and [docs/](docs/)
- **Configuration**: See [docs/configuration.md](docs/configuration.md)
- **Web UI**: See [docs/webui.md](docs/webui.md)

## Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Genesis Configuration Guide](docs/configuration.md)
