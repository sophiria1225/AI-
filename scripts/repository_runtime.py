"""Explicit per-repository paths while preserving the existing default runtime."""
from pathlib import PurePosixPath


def runtime_for(config, default_environment):
    selected = config.get("repository_runtime", {})
    if set(selected) - {"workdir", "python", "environment"}:
        raise ValueError("Unknown repository runtime field")
    workdir = selected.get("workdir", "/testbed")
    python = selected.get("python", "/opt/miniconda3/envs/testbed/bin/python")
    environment = selected.get("environment", default_environment)
    for path in (workdir, python):
        if (not isinstance(path, str) or "\0" in path
                or not PurePosixPath(path).is_absolute()
                or ".." in PurePosixPath(path).parts):
            raise ValueError("Repository runtime paths must be explicit absolute paths")
    if (not isinstance(environment, dict) or not environment.get("PATH")
            or any(not isinstance(k, str) or not isinstance(v, str) or "\0" in k + v
                   for k, v in environment.items())):
        raise ValueError("Repository runtime requires explicit string environment values and PATH")
    return {"workdir": workdir, "python": python, "environment": dict(environment)}
