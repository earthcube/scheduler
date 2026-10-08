# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Dagster-based data orchestration system for scientific data harvesting and processing, specifically designed for the EarthCube community. The system uses containerized workflows to run Gleaner (data harvesting) and Nabu (data processing) tools for indexing websites with JSON-LD structured data.

## Key Technologies

- **Dagster 1.7.10+** - Main orchestration framework using Software Defined Assets (SDA) pattern
- **Python 3.11** - Primary language  
- **PostgreSQL 13.3** - Dagster backend database
- **Docker/Docker Compose** - Containerization and deployment
- **MinIO/S3** - Object storage for configurations and data
- **Blazegraph** - RDF triplestore for graph data storage
- **earthcube-utilities** - Custom library for EarthCube-specific functionality

## Development Commands

### Local Development (Native)
```bash
# Set up environment
export $(cat dagster/implnets/deployment/.env | xargs)

# Run Dagster development server
cd dagster/implnets
dagster dev

# Run specific workflow modules
cd dagster/implnets/workflows/tasks
dagster dev
```

### Docker-based Development
```bash
cd dagster/implnets/deployment
cp envFile.env .env
# Edit .env file with your configuration
./dagster_localrun.sh
# Access Dagster UI at http://localhost:3000
```

### Asset and Job Operations
```bash
# Materialize specific assets
python -m dagster asset materialize -m tasks --select task/source_list,task/loadstatsHistory

# Execute jobs with partitions
dagster job execute eco_summon_and_release_job --partition geocodes_demo_data
```

### Testing
```bash
# Run tests (uses pytest framework)
cd dagster/implnets/workflows/[workflow_name]
pytest tests/
```

## Architecture

### Multi-Workflow System
- **workflows/ingest/** - Data ingestion pipelines using Gleaner tool
- **workflows/tasks/** - Scheduled processing tasks using Nabu tool  
- **workflows/ecrr/** - Earth Cube Resource Registry specific workflows
- **workflows/tutorial/** - Example/tutorial workflows

### Container Architecture
- **dagster-dagit** - Web UI (port 3000)
- **dagster-daemon** - Background scheduler and sensor manager
- **dagster-code-ingest** - Ingest workflow container
- **dagster-code-tasks** - Tasks workflow container  
- **dagster-postgres** - Metadata storage
- **headless** - Chrome headless for web scraping

### Multi-Tenant Support
- Configurable namespaces in graph database
- Tenant-specific configurations via `tenant.yaml`
- Organization-based data isolation

## Key Configuration Files

### Core Configuration
- `dagster/implnets/deployment/.env` - Environment variables (50+ required)
- `dagster/implnets/configs/gleanerconfig.yaml` - Data source definitions
- `dagster/implnets/configs/tenant.yaml` - Community/organization definitions
- `dagster/implnets/configs/nabuconfig.yaml` - Data processing configuration

### Dagster Configuration
- `dagster/implnets/workspace.yaml` - Workspace definition
- `dagster/implnets/dagster.yaml` - Instance configuration

### Docker Configuration
- `dagster/implnets/deployment/compose_local.yaml` - Local development
- `dagster/implnets/deployment/compose_project.yaml` - Production stack
- Environment-specific override files available

## Data Pipeline Flow

1. **Configuration Monitoring** - S3 sensors detect changes to config files
2. **Data Harvesting** - Gleaner tool scrapes websites for JSON-LD data
3. **Data Processing** - Nabu tool transforms and validates data
4. **Graph Loading** - Data loaded into Blazegraph triplestore
5. **Statistics & Reports** - Generate usage and processing reports

## Directory Structure

```
dagster/implnets/
├── workflows/              # Core workflow modules
│   ├── ingest/            # Data ingestion (Gleaner)
│   ├── tasks/             # Processing tasks (Nabu)  
│   ├── ecrr/              # Resource registry workflows
│   └── tutorial/          # Examples
├── deployment/            # Docker deployment configs
├── configs/               # Configuration files
├── shared/                # Shared utilities
└── build/                 # Docker build files
```

## Environment Setup

### Required Networks
- `traefik_proxy` - External network for routing
- `headless_gleanerio` - Headless browser network

### Required Volumes  
- `dagster-postgres` - PostgreSQL data persistence

### Critical Environment Variables
- MinIO/S3 credentials and endpoints
- Graph database URLs and namespaces
- Docker/Portainer API configuration
- Gleaner/Nabu tool configurations
- Slack notification settings

## Troubleshooting

### Common Issues
- If workflows show as "not working" in UI, regenerate code using the pygen/makefile approach
- Network creation failures: Check Docker swarm status and existing networks
- Missing environment file: Copy and edit `envFile.env` to `.env`

### Monitoring
- Dagster UI provides pipeline status and logs
- Slack integration for failure notifications
- Comprehensive logging stored in S3
- Asset lineage tracking through Dagster's dependency graph