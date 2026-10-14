#!/bin/bash
set -Eeuo pipefail

ISO=$(ls -1ctr ugv-jetson-*.iso | tail -n 1)

echo "Pushing $ISO to PiKVM $PIKVM..."
tar -c $ISO | ssh root@$PIKVM "kvmd-helper-otgmsd-remount rw && rm -f /var/lib/kvmd/msd/ugv-jetson-*.iso && tar --overwrite -x -C /var/lib/kvmd/msd/ ; kvmd-helper-otgmsd-remount ro"

