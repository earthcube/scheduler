import time

import docker
import requests
from pydantic import Field
from dagster import ConfigurableResource, get_dagster_logger


class QleverResource(ConfigurableResource):
    """Controls a Qlever triplestore container.

    Index rebuilds are triggered by restarting the container; the container
    entrypoint runs: qlever get-data → qlever index → qlever start.
    get-data downloads *_release.nq files from S3 as configured in the Qleverfile.
    """

    QLEVER_CONTAINER_NAME: str = Field(
        description="Name of the Qlever Docker container to restart for index rebuilds."
    )
    QLEVER_SPARQL_ENDPOINT: str = Field(
        description="Base HTTP URL for Qlever SPARQL queries, used for health checks. e.g. http://qlever:7019"
    )
    QLEVER_DOCKER_URL: str = Field(
        default="unix:///var/run/docker.sock",
        description="Docker socket or TCP endpoint. Mount /var/run/docker.sock into the Dagster container."
    )
    QLEVER_HEALTH_TIMEOUT: int = Field(
        default=600,
        description="Seconds to wait for Qlever to become healthy after restart."
    )
    QLEVER_HEALTH_POLL_INTERVAL: int = Field(
        default=15,
        description="Seconds between health-check polls while waiting for Qlever."
    )

    def _client(self):
        return docker.DockerClient(base_url=self.QLEVER_DOCKER_URL, version="1.43")

    def restart_and_rebuild(self, context) -> float:
        """Restart the container and block until Qlever is serving queries.

        Returns the wall-clock seconds from restart to first healthy response.
        Raises TimeoutError if QLEVER_HEALTH_TIMEOUT is exceeded.
        """
        log = context.log
        client = self._client()
        container = client.containers.get(self.QLEVER_CONTAINER_NAME)
        log.info(f"Restarting Qlever container '{self.QLEVER_CONTAINER_NAME}' to trigger index rebuild")
        container.restart(timeout=30)
        time.sleep(10)  # allow container to transition out of running state before polling
        return self._wait_for_healthy(context)

    def _wait_for_healthy(self, context) -> float:
        log = context.log
        start = time.time()
        check_url = f"{self.QLEVER_SPARQL_ENDPOINT}?query=SELECT+%2A+WHERE+%7B+%3Fs+%3Fp+%3Fo+%7D+LIMIT+1"
        while True:
            elapsed = time.time() - start
            if elapsed > self.QLEVER_HEALTH_TIMEOUT:
                raise TimeoutError(
                    f"Qlever container '{self.QLEVER_CONTAINER_NAME}' did not become healthy "
                    f"within {self.QLEVER_HEALTH_TIMEOUT}s"
                )
            try:
                r = requests.get(
                    check_url,
                    headers={"Accept": "application/sparql-results+json"},
                    timeout=10,
                )
                if r.status_code == 200:
                    log.info(f"Qlever healthy after {elapsed:.0f}s")
                    return elapsed
            except Exception as e:
                log.debug(f"Qlever not ready ({elapsed:.0f}s elapsed): {e}")
            time.sleep(self.QLEVER_HEALTH_POLL_INTERVAL)

    def triple_count(self) -> int:
        """Return the total triple count from the running Qlever index."""
        r = requests.get(
            self.QLEVER_SPARQL_ENDPOINT,
            params={"query": "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }"},
            headers={"Accept": "application/sparql-results+json"},
            timeout=60,
        )
        r.raise_for_status()
        return int(r.json()["results"]["bindings"][0]["n"]["value"])
