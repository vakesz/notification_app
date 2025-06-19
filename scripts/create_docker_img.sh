#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="notification-app"
VERSION=$(python - <<'PY'
import tomllib
with open('pyproject.toml', 'rb') as f:
    print(tomllib.load(f)["project"]["version"])
PY
)
BACKUP_FILE="${IMAGE_NAME}-${VERSION}.tar"

echo "Building ${IMAGE_NAME}:${VERSION}"
docker build --pull -t "${IMAGE_NAME}:${VERSION}" .

echo "Saving image to ${BACKUP_FILE}"
docker save -o "${BACKUP_FILE}" "${IMAGE_NAME}:${VERSION}"
