"""Trigger a QLever service update through the Portainer docker API.

QLever loads from the release files, so a tenant whose graph type is qlever is
not pushed to. Its service is force updated so it reloads the new release.
Tenant config:  graph: {type: qlever, qlever_service: <swarm service name or id>}
"""
import requests


def is_qlever_tenant(tenant) -> bool:
    graph = tenant.get("graph") or {}
    return str(graph.get("type", "")).lower() == "qlever"


def update_qlever_service(docker_url, apikey, service, timeout=60):
    """Force update ``service`` via the docker API at ``docker_url`` (the
    Portainer endpoint docker proxy), so the tasks restart and reload data."""
    if not service:
        raise ValueError("qlever tenant has no graph.qlever_service")
    base = docker_url.rstrip("/")
    headers = {"X-API-Key": apikey}
    r = requests.get(f"{base}/services/{service}", headers=headers, timeout=timeout)
    r.raise_for_status()
    info = r.json()
    spec = info["Spec"]
    task_template = spec.setdefault("TaskTemplate", {})
    task_template["ForceUpdate"] = int(task_template.get("ForceUpdate", 0)) + 1
    r = requests.post(f"{base}/services/{info['ID']}/update",
                      params={"version": info["Version"]["Index"]},
                      headers=headers, json=spec, timeout=timeout)
    r.raise_for_status()
    return info["ID"]
