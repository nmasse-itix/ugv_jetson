#!/bin/bash
# Start the UGV demo: Jupyter Lab in the background, app.py in the foreground.
#
# With arguments, run them instead (e.g. "bash" for a debug shell).
set -Eeuo pipefail

SRC=/home/admin/ugv_jetson

if [ ! -f "$SRC/app.py" ]; then
  echo "No source code in $SRC: is the host's git clone mounted?" >&2
  exit 1
fi

# The scripts and the docs expect the virtualenv at ugv_jetson/ugv-env (it is
# gitignored). It lives in the image: link it into the mounted clone.
ln -sfn /opt/ugv-env "$SRC/ugv-env"

if [ $# -gt 0 ]; then
  exec "$@"
fi

cd "$SRC"
/opt/ugv-env/bin/python -m jupyter lab --ip=0.0.0.0 --port=8888 --no-browser &
exec /opt/ugv-env/bin/python "$SRC/app.py"
