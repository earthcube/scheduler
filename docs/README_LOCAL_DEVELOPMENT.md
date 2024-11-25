# Development

If you look in the doc/README.md that description is probably better.


Two types:

1. dagster dev   - Dagster runs the UI in development mode
1. Container based. This uses docker and locally deployed containers

!!!  note 
    NOTE, the Dagster and the Code containers need to be the same.
    For local development images are named ` dagster-local:latest` and  code containers named `dagster-gleanerio-local:latest`
    and built in the compose_local.yaml
    for production,
      * dagster named: nsfearthcube/dagster-gleanerio:${CONTAINER_DAGSTER_TAG:-latest}
      * code containers  are named `nsfearthcube/dagster-gleanerio-workflow:${CONTAINER_TAG:-latest}`
    

## DAGSTER DEV

At the top level (dagster/implents) you can run 

`dagster dev`

You need to set the environment based on dagster/implnets/deployment/envFile.env

For local development, these environment variable needs to be set

```
DAGSTER_HOME=dagster/dagster_home
DAGSTER_LOCAL_ARTIFACT_STORAGE_DIR=/Users/valentin/development/dev_earthcube/scheduler/dagster/dagster_home/
```

It should run workflows/tasks/tasks

defined in the pyproject.toml

```
[tool.dagster]
module_name = "workflows.tasks.tasks"
```
### Setting up in pycharm

you can add runconfigs in pycharm
![pycharm_dagster_dev_runconfig.png](images%2Fpycharm_dagster_dev_runconfig.png)

You should/need to add the envFile plug in so that env files can be 
![pycharm_dagster_dev_runconfig.png](images%2Fpycharm_dagster_dev_runconfig.png)

### testing tasks

`cd dagster/implnets/workflows/tasks`
You need to set the environment based on dagster/implnets/deployment/envFile.env

`export $(sed  '/^[ \t]*#/d' ../../deployment/.env |  sed '/^$/d' | xargs)`

`dagster dev`

will run just the task, and in editable form, i think.

### testing by materializing assets
#### Env variables:

```yaml
DAGSTER_LOCAL_ARTIFACT_STORAGE_DIR=/Users/valentin/development/dev_earthcube/scheduler/dagster/dagster_home/
GLEANERIO_GLEANER_CONFIG_PATH=/Users/valentin/development/dev_earthcube/scheduler/dagster/implnets/configs/eco/gleanerconfig.yaml
PROJECT=test
```

To materialize an asset from teh command line, you will probably need to materialize the assets it uses (at least the first time)
(might need test_task... )

`python -m dagster asset materialize -m tasks --select task/task_tenant_sources,task/loadstatsCommunity --partition dev `

`python -m dagster asset materialize -m tasks --select task/source_list,task/loadstatsHistory` 

jobs:
https://docs.dagster.io/concepts/ops-jobs-graphs/job-execution#dagster-ui
`python -m dagster job list` 

`dagster dagster job execute eco_summon_and_release_job --partition geocodes_demo_data`

## TESTING CONTAINERS

Containers are a well tested approach. We deploy these container
to production, so it's a good way to test.
There are a set of required files:

* env variables file
* gleaner/nabu configuration files, without any passwords, servers. Those are handled in the env variables
* docker compose file
* docker networks and volumes for the compose files
*  three files uploaded to docker as configs
    * gleanerconfigs.yaml gleaner/nabu
    * nabuconfigs.yaml - gleaner/nabu
    * workspace.yaml -- dagster
* (opptional/advanced) add a compose_project_PROJECT_override.yaml file with additional containers

## PORTAINER API KEY

note on how to do this.
''


## Start
For production environments, script, `dagster_setup_docker.sh`  should create the networks, volumes, and 
upload configuration files

1. setup a project in configs directory, if one des not exist
    2)   add gleanerconfig.yaml, nabuconfig.yaml~~, and workspace.yaml~~ (NOTE NEED A TEMPLATE FOR THIS)
1. copy envFile.env to .env, and edit
1. run  ./dagster_localrun.sh
1. go to https://loclahost:3000/
1. run a small test dataset.

```
cd dagster/implnets/deployment
cp envFile.env .env
# configure environment in .env 

./dagster_localrun.sh

```

If you look in dagster_localrun.sh you can see that the 
$PROJECT variable is used to define what files to use, and define, and to setup a separate 'namespace' in traefik labels.

If you look in compose_local_eco_override.yaml you can see that
additional mounts are added to the containers.

These can be customized in the  `compose_local_PROJECT_override.yaml` for local development.

### customizing the configs
for local development three configs

* configs/PROJECT/gleanerconfigs.yaml gleaner/nabu
* configs/PROJECT/nabuconfigs.yaml - gleaner/nabu
* configs/local/workspace.yaml -- dagster

### Editing/testing code

if you run pygen, then you need to regnerate code. the makefile or a pycharm run config is the best way. 

### MOVING TO PRODUCTION


you need to deploy a `compose_project.yaml`, and a `compose_project_ingest.yaml` 
If a dagster scheduler is already running, you can deploy just the `compose_project_ingest.yaml` 
In future we hope to run multiple `compose_project_ingest.yaml` 

After creating a `compose_project_ingest.yaml` stack

1. clone and edit a workspace.yaml to docker config (this is for an eco project)
```yaml
load_from:

      - grpc_server:
            host: dagster-code-eco-tasks
            port: 4000
            location_name: "eco-tasks"
      - grpc_server:
            host: dagster-code-eco-ingest
            port: 4000
            location_name: "eco-ingest"
```
1. change the env variable `GLEANERIO_DOCKER_WORKSPACE_CONFIG` to point to that config. push 'save' button
1. push _pull and redeploy_ button




# command line deploy
```
docker compose -env .env -f compose_project.yaml  up
docker compose -env .env -f compose_project_ingest.yaml  up
```

