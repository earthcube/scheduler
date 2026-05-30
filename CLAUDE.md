# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a Dagster-based workflow orchestration system for the EarthCube Scheduler project, specifically designed to run Gleaner and Nabu packages for indexing websites with JSON-LD structured data. The system uses Docker containers and is managed through Portainer.

## Key Architecture

### Project Structure
- `dagster/implnets/` - Main Dagster implementation
- `dagster/implnets/workflows/` - Three main workflow modules:
  - `ingest/` - Data ingestion workflows (Gleaner/Nabu operations)
  - `tasks/` - Weekly maintenance and statistics tasks
  - `ecrr/` - EarthCube Resource Registry custom workflows
- `dagster/implnets/configs/` - Configuration files organized by project (eco, oih, iow, nsdf)
- `dagster/implnets/deployment/` - Docker compose and deployment configurations

### Workflow Architecture
The system operates with three distinct workflow types:
1. **Ingest workflows** (`workflows.ingest`) - Handle data harvesting and loading via Gleaner/Nabu containers
2. **Task workflows** (`workflows.tasks.tasks`) - Generate statistics and maintenance operations
3. **Custom workflows** (`workflows.ecrr`) - Project-specific implementations (EarthCube Resource Registry)

Each workflow is containerized and communicates via gRPC with the main Dagster scheduler.

## Development Commands

### Local Development
```bash
# Set up environment (from dagster/implnets/deployment/)
cp envFile.env .env
# Edit .env with your configuration

# Run Dagster dev server (from dagster/implnets/)
dagster dev --workspace workspace_dev.yaml

# Run local containerized stack
./dagster_localrun.sh
```

### Testing Commands
```bash
# Test specific assets (from dagster/implnets/workflows/tasks/)
dagster dev

# Materialize specific assets
python -m dagster asset materialize -m tasks --select task/task_tenant_sources,task/loadstatsCommunity --partition dev

# List available jobs
python -m dagster job list

# Execute specific job with partition
dagster job execute eco_summon_and_release_job --partition geocodes_demo_data
```

### Build Commands (from dagster/implnets/)
```bash
# Build workflow containers
make wf-build    # Build and tag workflow container
make wf-push     # Push to registry

# Project-specific builds (eco, oih, iow, nsdf)
make eco-generate    # Generate code for ECO project
make eco-build       # Build ECO container
make eco-push        # Push ECO container

# Configuration building
make eco-cfgbuild    # Build configuration files
```

### Testing
The repository includes tests in:
- `dagster/implnets/workflows/ingest/ingest_tests/`
- `dagster/implnets/workflows/tutorial/tutorial_tests/`

Run tests using pytest from the respective workflow directories.

## Configuration Management

### Environment Setup
The main environment configuration is in `dagster/implnets/deployment/envFile.env`. Key variables include:

- `DAGSTER_HOME` - Dagster home directory
- `GLEANERIO_*` - Gleaner/Nabu configuration paths and credentials
- `PROJECT` - Project identifier (eco, oih, iow, nsdf)
- Docker and Portainer configurations

### Multi-Project Architecture
The system supports multiple projects (ECO, OIH, IoW, NSDF) with:
- Separate configuration directories under `configs/`
- Project-specific Docker builds via Makefile targets
- Environment variable switching via `PROJECT` setting

### Configuration Files
- **Workspace configs**: `workspace_dev.yaml` for development, project-specific workspace files for production
- **Gleaner configs**: Project-specific `gleanerconfig.yaml` files in `configs/PROJECT/`
- **Tenant configs**: Define community-source relationships in `tenant.yaml`
- **Docker configs**: Deployment configurations in `deployment/` directory

## Code Style and Conventions

### Python Configuration
- Black formatting: line length 99, Python 3.7+ target
- isort for import sorting
- Pylint with specific message control settings
- Dagster module name: `workflows.tasks.tasks`

### Development Patterns
- **Asset-based architecture**: Uses Dagster's software-defined assets
- **Resource injection**: Custom resources for S3, Blazegraph, GleanerIO operations
- **Partitioning**: Sources and tenants as partitions for parallel processing
- **Sensors**: S3 configuration monitoring and file-based triggers
- **Containerized execution**: Gleaner/Nabu operations run in separate Docker containers

## Deployment

### Local Development with PyCharm
- Use EnvFile plugin for environment variable management
- Run configurations available in `runConfigurations/` directory
- Debug modes available for different workflow components

### Container Deployment
- Uses Docker Compose with Portainer management
- Two-stack deployment: main Dagster stack + project-specific ingest stacks
- Traefik routing for multi-project hosting
- Configuration files deployed as both Docker configs and S3 objects

### Production Considerations
- Environment-specific resource configurations (local vs production)
- Slack integration for failure notifications
- S3 storage for logs, configurations, and processed data
- Blazegraph triplestore for RDF data storage