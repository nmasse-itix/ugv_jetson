#!/bin/bash
# Point the pan-tilt camera, grab a fresh frame, and overlay a grid labelled in
# ABSOLUTE gimbal angles (degrees), so a vision model can servo on it:
# to centre an object, read the yellow labels next to it and send those angles.
#
# Usage: look.sh [PAN TILT] [OUTPUT.jpg]
#   look.sh 0 0            # look straight ahead
#   look.sh -40 10         # look left and slightly up
#   look.sh                # keep the current angles (last ones set by this script)
#
# Prints the path of the annotated frame and the angles it was taken at.
#
# Conventions (measured on robot-b, 2026-10-14, by phase correlation):
#   - PAN: negative = left, positive = right (gimbal T:133 X). TILT: positive = up (Y).
#   - About 5.7 px per degree near the centre of the 800x600 frame, i.e. roughly
#     +-70 deg horizontally and +-52 deg vertically. The lens is a fisheye: the
#     labels are exact near the centre and approximate near the edges, so servo
#     in steps (look, correct, look again) rather than in one jump.
#   - The MJPEG feed first hands out a stale frame (the previous position): the
#     script keeps the last of several frames, after the gimbal has settled.
set -Eeuo pipefail

API="${UGV_API:-http://127.0.0.1:5000}"
STATE="${XDG_RUNTIME_DIR:-/tmp}/ugv-gimbal"
PX_PER_DEG="${UGV_PX_PER_DEG:-5.7}"
FONT=/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf

if [ $# -ge 2 ] && [[ "$1" =~ ^-?[0-9]+$ ]] && [[ "$2" =~ ^-?[0-9]+$ ]]; then
  PAN="$1"; TILT="$2"; shift 2
  # Mechanical range of the UGV gimbal.
  [ "$PAN" -lt -180 ] && PAN=-180; [ "$PAN" -gt 180 ] && PAN=180
  [ "$TILT" -lt -45 ] && TILT=-45; [ "$TILT" -gt 90 ] && TILT=90
  curl -fsS -X POST "$API/send_ctrl" -H 'Content-Type: application/json' \
    -d "{\"T\":133,\"X\":$PAN,\"Y\":$TILT,\"SPD\":0,\"ACC\":128}" >/dev/null </dev/null
  echo "$PAN $TILT" > "$STATE"
  sleep 2
elif [ -f "$STATE" ]; then
  read -r PAN TILT < "$STATE"
else
  PAN=0; TILT=0
fi

OUT="${1:-/tmp/look_$(date +%s%N).jpg}"
RAW="$(mktemp --suffix=.jpg)"
trap 'rm -f "$RAW"' EXIT

ffmpeg -nostdin -loglevel error -i "$API/video_feed" -frames:v 10 -update 1 -y "$RAW"

# One line every 10 degrees inside the frame, labelled with its absolute angle.
FILTER="$(awk -v pan="$PAN" -v tilt="$TILT" -v k="$PX_PER_DEG" -v font="$FONT" 'BEGIN {
  W = 800; H = 600; cx = W / 2; cy = H / 2; f = ""
  txt = "fontfile=" font ":fontcolor=yellow:fontsize=16:box=1:boxcolor=black@0.6:boxborderw=3"
  for (a = int((pan - 80) / 10) * 10; a <= pan + 80; a += 10) {
    x = int(cx + (a - pan) * k)
    if (x < 0 || x >= W) continue
    f = f sprintf("drawbox=x=%d:y=0:w=1:h=%d:color=yellow@0.5:t=fill,", x, H)
    f = f sprintf("drawtext=%s:text=%s:x=%d-text_w/2:y=4,", txt, "P" a, x)
  }
  for (b = int((tilt - 60) / 10) * 10; b <= tilt + 60; b += 10) {
    y = int(cy - (b - tilt) * k)
    if (y < 0 || y >= H) continue
    f = f sprintf("drawbox=x=0:y=%d:w=%d:h=1:color=cyan@0.5:t=fill,", y, W)
    f = f sprintf("drawtext=%s:fontcolor=cyan:text=%s:x=4:y=%d-text_h/2,", txt, "T" b, y)
  }
  # Centre of the image = where the camera points now.
  f = f sprintf("drawbox=x=%d:y=%d:w=21:h=3:color=red:t=fill,", cx - 10, cy - 1)
  f = f sprintf("drawbox=x=%d:y=%d:w=3:h=21:color=red:t=fill,", cx - 1, cy - 10)
  f = f sprintf("drawtext=%s:fontcolor=white:text=%s:x=W-text_w-6:y=H-text_h-6", txt, "'"'"'now P" pan " T" tilt "'"'"'")
  print f
}')"

ffmpeg -nostdin -loglevel error -i "$RAW" -vf "$FILTER" -q:v 3 -y "$OUT"
echo "$OUT (pan=$PAN tilt=$TILT; yellow P labels = pan angle of each vertical line, cyan T labels = tilt angle of each horizontal line, red cross = current aim)"
