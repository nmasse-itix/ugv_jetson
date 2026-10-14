#!/bin/bash
set -Eeuo pipefail

# Build and push the UGV demo runtime image.
#
# Usage: sudo ./app/build.sh [tag]   (from anywhere; the context is the repo root)
#   no tag -> a timestamp, and ":latest" moves onto it
#   a tag  -> that tag only

EXPLICIT_TAG="${1:-}"
export REGISTRY_AUTH_FILE=/etc/containers/auth.json
TAG="${EXPLICIT_TAG:-$(date "+%Y%m%d%H%M%S")}"
IMAGE="quay.io/robotic-agent-fleet-demo/ugv-jetson/app"

cd "$(dirname "$0")/.."
podman build -f app/Containerfile -t "$IMAGE:$TAG" .
podman push "$IMAGE:$TAG"
if [ -z "$EXPLICIT_TAG" ]; then
  podman tag "$IMAGE:$TAG" "$IMAGE:latest"
  podman push "$IMAGE:latest"
fi
echo "Done: $IMAGE:$TAG"
