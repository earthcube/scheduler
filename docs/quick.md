# Notes

### Run Deploy Dagster locally (ROUGH)
Dagster needs a docker instance to run Gleanerio. We usually do this in a remote container.
Basically, you can run a single workflow with the UI from that workflows directory with a `dagster run`

You will need to deploy dagster containers to portainer, for a docker swarm
0. get the portainer url, and auth token 
0.  SSH to the  make hosting the docker.

1. Pull scheduler repo
2. cd dagster/implnets/deployment
3. create a copy of envFile.env and **edit env variables**
   4. PROJECT=test
   5. GLEANERIO_MINIO_ADDRESS ++
   6. GLEANERIO_GRAPH_URL, GLEANERIO_GRAPH_NAMESPACE
   7. GLEANERIO_DOCKER_URL, GLEANERIO_PORTAINER_APIKEY
   8. SCHED_HOSTNAME defaults to sched
5. as noted as noted in (Compose, Environment and Docker API Assets), deploy the configuration to s3. 
6. ~~create network and volumes needed `dagster_setup_docker.sh`~~
7. manually add configs (used by dagster)
   10. workspace-{project}
   11. dagster from:dagster/implnets/deployment/dagster.yaml
7. add configs to S3/Minio. (used by workflows)
   8. scheduler/configs/gleanerconfig.yml
   9. scheduler/configs/tenant.yml
   10. scheduler/configs/nabuconfig.yml
8. then you can run a command. in runConfigs there are PyCharm run files (duplicate, then edit). This is the basic command line below
   9. set ENV
   11. `cd dagster/implnets/workflows/ingest`
   12. `dagster run`

**NEED MORE EXAMPLES**

