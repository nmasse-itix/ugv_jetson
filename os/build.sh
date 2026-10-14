#!/bin/bash

set -Eeuo pipefail

# Build the bootc image of the UGV Jetson, and the ISO that installs it.
# Derived from robotic-agent-fleet/os/build.sh.
#
# Usage: sudo ./build.sh [tag]
#   sudo ./build.sh            # tag = a timestamp, and ":latest" moves onto it
#   sudo ./build.sh v1.2       # tag = v1.2, and ":latest" is left where it is
#   sudo SKIP_ISO=1 ./build.sh # image only, for a "bootc switch" / Flight Control rollout
#
# Unlike the RAF build, the ISO is NOT pushed to quay: it embeds the enrollment
# key and the registry pull secret, and goes straight to the PiKVM instead
# (see push-to-pikvm.sh).

EXPLICIT_TAG="${1:-}"
SKIP_ISO="${SKIP_ISO:-}"

if [ $UID -ne 0 ]; then
  echo "Must run as root!"
  exit 1
fi

export REGISTRY_AUTH_FILE=/etc/containers/auth.json
export TARGET_TAG="${EXPLICIT_TAG:-$(date "+%Y%m%d%H%M%S")}"
export TARGET_IMAGE="quay.io/robotic-agent-fleet-demo/ugv-jetson/os:${TARGET_TAG}"
export RHEL_ISO_IMAGE="rhel-9.8-aarch64-boot.iso"

if [ -z "$SKIP_ISO" ]; then
  if [ ! -f flightctl-config.yaml ]; then
    echo "flightctl-config.yaml is missing!"
    echo "Generate it with 'flightctl certificate request --signer=enrollment --expiration=3650d --output=embedded > flightctl-config.yaml'"
    exit 1
  fi

  if [ ! -f "${RHEL_ISO_IMAGE}" ]; then
    echo "${RHEL_ISO_IMAGE} ISO image is missing!"
    echo "Download it from https://access.redhat.com/downloads/content/rhel!"
    exit 1
  fi

  # Wi-Fi profiles baked into the install, kept out of git: they carry PSKs.
  shopt -s nullglob
  WIFI_PROFILES=(wifi/*.nmconnection)
  shopt -u nullglob

  if [ ${#WIFI_PROFILES[@]} -eq 0 ]; then
    echo "No Wi-Fi profile in wifi/!"
    echo "Copy the example and fill it in:"
    echo "  cp wifi.nmconnection.example wifi/lab-5g.nmconnection"
    echo "or lift a working profile off a machine already on that network:"
    echo "  sudo cat /etc/NetworkManager/system-connections/<ssid>.nmconnection \\"
    echo "    | ./sanitize-wifi-profile.py 20 > wifi/<ssid>.nmconnection"
    exit 1
  fi

  if grep -l 'CHANGE-ME' "${WIFI_PROFILES[@]}"; then
    echo "The Wi-Fi profiles above still hold example values."
    exit 1
  fi

  echo "Wi-Fi profiles to embed: ${WIFI_PROFILES[*]}"
fi

if ! podman login --get-login quay.io &>/dev/null; then
  echo "Push credentials for quay.io required! Logging in..."
  podman login quay.io
fi

# Reclaim what previous runs left behind: every tag of this script's own
# repository, and the ISO files it wrote. The registry is the archive for the
# images; the build cache is left alone so a rebuild can skip the dnf transaction.
echo "Cleaning previous builds out of local storage..."
mapfile -t stale_images < <(podman images --filter reference="${TARGET_IMAGE%:*}" --format '{{.Repository}}:{{.Tag}}')
if [ ${#stale_images[@]} -gt 0 ]; then
  printf '  image     %s\n' "${stale_images[@]}"
  podman rmi --force "${stale_images[@]}" >/dev/null
fi
if [ -z "$SKIP_ISO" ]; then
  shopt -s nullglob
  stale_isos=(ugv-jetson-*.iso)
  shopt -u nullglob
  if [ ${#stale_isos[@]} -gt 0 ]; then
    printf '  iso       %s\n' "${stale_isos[@]}"
    rm -f "${stale_isos[@]}"
  fi
fi

echo "Building bootc image..."
podman build -t "$TARGET_IMAGE" .

# The Kickstart points the installed node at this reference with "bootc switch":
# an image that was not pushed produces a node whose upgrades fail.
echo "Pushing bootc image to $TARGET_IMAGE..."
podman push "$TARGET_IMAGE"

if [ -z "$EXPLICIT_TAG" ]; then
  echo "Moving :latest onto $TARGET_TAG..."
  podman tag "$TARGET_IMAGE" "${TARGET_IMAGE%:*}:latest"
  podman push "${TARGET_IMAGE%:*}:latest"
fi

if [ -n "$SKIP_ISO" ]; then
  echo "SKIP_ISO set, done: $TARGET_IMAGE"
  exit 0
fi

echo "Templating Kickstart..."
export __ETC_OSTREE_AUTH_JSON_B32__="$(base32 -w 80 $REGISTRY_AUTH_FILE)"
export __ETC_FLIGHTCTL_CONFIG_YAML_B32__="$(base32 -w 80 flightctl-config.yaml)"
export __ETC_NM_SYSTEM_CONNECTIONS_TGZ_B32__="$(tar czf - --owner=root --group=root --numeric-owner \
  --no-selinux --no-xattrs --no-acls --mode=0600 --transform='s|^wifi/||' "${WIFI_PROFILES[@]}" | base32 -w 80)"
export __TARGET_IMAGE__="$TARGET_IMAGE"

rm -f kickstart.cfg
envsubst '${__ETC_OSTREE_AUTH_JSON_B32__} ${__ETC_FLIGHTCTL_CONFIG_YAML_B32__} ${__ETC_NM_SYSTEM_CONNECTIONS_TGZ_B32__} ${__TARGET_IMAGE__}' < kickstart.cfg.template > kickstart.cfg

echo "Validating Kickstart..."
ksvalidator kickstart.cfg

echo "Exporting bootc image as OCI directory..."
OCI_DIR="$(mktemp -d /var/tmp/ugv-jetson-oci.XXXXXX)"
trap 'rm -rf "$OCI_DIR"' EXIT
skopeo copy --preserve-digests "docker://$TARGET_IMAGE" "oci:$OCI_DIR/container:$TARGET_IMAGE"

echo "Generating ISO image..."
mkksiso -R 'set timeout=60' 'set timeout=5' -R 'set default="1"' 'set default="0"' -c "console=ttyTCU0 console=tty0" -a "$OCI_DIR/container" --ks "kickstart.cfg" "${RHEL_ISO_IMAGE}" "ugv-jetson-${TARGET_TAG}.iso"

echo "Done: ugv-jetson-${TARGET_TAG}.iso"
