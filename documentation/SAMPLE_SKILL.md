---
name: visual-target-navigation
description: Drive a camera-equipped robot (e.g. Wall-E UGV) toward a visually-identified target using closed-loop capture-look-move cycles with differential-drive motor commands.
---

# Visual Target Navigation

Use this skill whenever asked to make a camera-equipped robot **approach, follow, or center on** a visually identified object ("go to the blue ball", "follow that person", "look at the red box and drive over").

This is a **closed-loop visual servoing** pattern: capture frame → ask vision where the target is → issue a small motor pulse → repeat. Never issue one big "drive to it" command — you cannot judge distance/heading from a single frame, and robot odometry drifts (wheels slip, surfaces vary).

## The capture-look-move loop

Each iteration:

1. **Capture a single frame** from the MJPEG stream:
   ```bash
   ffmpeg -i http://127.0.0.1:5000/video_feed -frames:v 1 -f mjpeg -y /tmp/walle_view_N.jpg 2>&1 | tail -1
   ```
   Use a **fresh filename each iteration** (`_N` suffix) — overwriting the same path can serve a stale cached frame to the vision call. Use `-f mjpeg` as the muxer (NOT `-f image2`, which demands a `%03d` sequence pattern and errors out; `-update 1` is also not supported by this ffmpeg build).

2. **Ask vision a SPECIFIC comparative question**, not a generic one. Good: "Where is the blue ball relative to the center of the image — left/center/right? Is it bigger/closer than before?" This grounds the answer in what changed, which is what you need to decide the next motor pulse. A vague "what do you see?" wastes a turn.

3. **Issue a short motor pulse, then STOP**:
   ```bash
   curl -s -X POST http://127.0.0.1:5000/send_ctrl -H "Content-Type: application/json" -d '{"T":1,"L":<left_mps>,"R":<right_mps>}'
   sleep <duration>
   curl -s -X POST http://127.0.0.1:5000/send_ctrl -H "Content-Type: application/json" -d '{"T":1,"L":0,"R":0}'
   ```
   Differential drive steering — both values are wheel speeds in m/s:
   - `L == R` → straight ahead
   - `L > R` → curves right (right wheel slower)
   - `L < R` → curves left
   - Typical magnitudes: 0.05–0.25 m/s; pulse durations 0.8–2.5s depending on how big a correction is needed.
   - **Always send the explicit `{"L":0,"R":0}` stop** — motor commands have a 2-5s lifetime and auto-stop, but explicit stop keeps behavior predictable and avoids overshoot between your capture cycles.

4. **Re-capture and re-evaluate.** Iterate until the target fills enough of the frame / drops out of the bottom of the frame (a strong signal you're now right on top of it — the camera's forward FOV no longer covers something directly underneath/in front of the chassis).

## Reading progress signals from the frames

- **Target growing larger across frames** = you're closing distance. Keep going.
- **Target stuck at same size/position for 1-2 iterations** = likely wheel slip on a slick surface (e.g. hardwood floors). Increase pulse magnitude and/or duration rather than repeating the same weak pulse.
- **Target drifting toward one edge** = your heading is off; correct with an asymmetric `L`/`R` pulse toward that side before continuing straight.
- **Target disappearing from the bottom of frame while growing** = arrival. This is the natural end state — the camera's forward-pointing FOV can't see something directly beneath/in front of the chassis. Report success rather than continuing to drive blindly.

## Pitfalls

- Don't trust a single "are we there yet" snapshot — always compare against the previous frame's read to judge actual movement, since fisheye lenses and camera angle make absolute distance hard to judge.
- Don't send long, large motor pulses hoping to cover more ground in one shot — overshoot is hard to correct and you lose the target from frame.
- If using the same output filename for every capture, you risk ffmpeg/vision reading a cached/stale image — increment the filename per iteration.
- If you have pan/tilt gimbal control (`T:133`, X=pan, Y=tilt in degrees), you can use it to re-center a target that's drifted out of frame WITHOUT moving the chassis — useful for fine-tracking before committing to a drive pulse. (Not exercised in this session, but available per the robot's capability set.)

## Before you start: is the service even up?

Don't assume the API is reachable — the Flask server inside the robot's container is **not** auto-started on container boot (the container's entrypoint is just `/bin/sleep INF`; the app must be launched manually each time). If `curl`/`ffmpeg` against `127.0.0.1:5000` returns "Connection refused", walk this ladder:

1. **Confirm nothing is listening**: `ss -tlnp | grep 5000` (or `curl -m5 -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/`, expect `000`).
2. **Check the container** (no plain `docker` CLI here — use `sudo podman ps -a`, filter for `nvidia-jetpack`). If `STATUS` shows `Exited (137)` (SIGKILL/OOM) or similar, it crashed or was stopped.
3. **Restart the container**: `sudo podman start nvidia-jetpack`. This alone is NOT enough — it only brings the container's `sleep` process back; the robot app does not auto-launch inside it.
4. **Launch the app manually inside the container**, detached so it survives your shell exiting:
   ```bash
   sudo podman exec -d nvidia-jetpack sh -c \
     "cd /home/admin/ugv_jetson && setsid nohup ./ugv-env/bin/python ./app.py > /tmp/app_new.log 2>&1 < /dev/null &"
   ```
   Use `setsid nohup ... < /dev/null &` — a bare `nohup ... &` inside `podman exec -d sh -c "..."` does NOT reliably detach; the process dies with the parent shell. `setsid` gives it its own session so it survives.
5. **Wait ~15-20s** for Flask + camera + TFLite model init (you'll see `* Running on http://127.0.0.1:5000` in the log), then verify: `curl -m5 -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/` should return `200`.
6. **Always tail a FRESH log file name** (`/tmp/app_new.log`, not the old `/tmp/app.log`) — the app may have left a stale log from a previous session days old, and reading it will make you think the server "started" when you're actually looking at old output.

Full session transcript of this recovery (commands + log excerpts) is in `references/service-recovery-2026-06-08.md`.

## Robot API reference (Wall-E UGV / Jetson, adapt host/port if different)

- Video stream: `http://127.0.0.1:5000/video_feed` (MJPEG)
- Control endpoint: `POST http://127.0.0.1:5000/send_ctrl` with JSON body
  - Drive: `{"T":1,"L":<m/s>,"R":<m/s>}`
  - Gimbal pan/tilt: `{"T":133,"X":<deg>,"Y":<deg>}`
  - Camera lamp: `{"T":...}` ON=`A:10406`/OFF=`A:10404`; chassis lamp ON=`A:10408`/OFF=`A:10407`
- See memory notes for the fuller command reference (captured 2026-06-08) if you need lamps/lidar/stereo vision details.