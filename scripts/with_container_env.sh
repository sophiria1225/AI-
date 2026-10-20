#!/bin/sh
set -eu
HARNESS_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export PATH="$HARNESS_ROOT/.tools/bin:$PATH"
export DOCKER_CONFIG="$HARNESS_ROOT/.runtime/docker"
export DOCKER_HOST="${HARNESS_DOCKER_HOST:-unix://$HOME/.colima/harness-e0/docker.sock}"
exec "$@"
