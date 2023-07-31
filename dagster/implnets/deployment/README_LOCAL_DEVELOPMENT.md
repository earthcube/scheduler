# Development

Two types:

1) Container based. This uses docker and locally deployed containers
2) dagster dev   - Dagster runs the UI in development mode



## TESTING CONTAINERS

Containers a tested approach. We deploy these container
to production, so it's a good way to test.

```
cd dagster/implnets/deployment
cp envFile.env .env
# configure environment in .env 

./dagster_localrun.sh

```

If you look in dagster_localrun.sh you can see that the 
$PROJECT variable is use to define what files to use, and define

If you look in compose_eco_override.yaml you can see that
additional mounts are added to the containers.

These can be customize in this file for local development.

### customizing the configs
for local development three configs

* gleanerconfigs.yaml gleaner/nabu
* nabuconfigs.yaml - gleaner/nabu
* workspace.yaml -- dagster




## DAGSTER DEV


At the top level (dagster/implents) you can run 

`dagster dev`

You need to set the environment based on dagster/implnets/deployment/envFile.env

It should run workflows/tasks/tasks

defined in the pyproject.toml

```
[tool.dagster]
module_name = "workflows.tasks.tasks"
```

### testing tasks

cd dagster/implnets/workflows/tasks
You need to set the environment based on dagster/implnets/deployment/envFile.env

`dagster dev`
will run just the task, and in editable form, i think.
