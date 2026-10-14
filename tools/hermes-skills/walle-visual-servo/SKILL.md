---
name: walle-visual-servo
description: Find, centre and approach objects with the camera grid.
version: 1.0.0
author: Nicolas
license: MIT
metadata:
  hermes:
    tags: [robotics, ugv, vision, servoing, gimbal]
    related_skills: [walle-ugv-control]
---

# Wall-E visual servoing

## When to Use
Whenever Wall-E must find something, look at it, centre it, say where it is,
or drive to it ("trouve la balle verte", "regarde Nicolas", "va chercher...").

## The tool: look.sh
`/home/admin/ugv_jetson/tools/look.sh [PAN TILT]` points the gimbal (if angles
are given), waits, grabs a FRESH frame and saves it with a grid overlay. It
prints the image path: analyse that image with vision_analyze.

On the image:
- vertical yellow lines are labelled `P<angle>`: the PAN angle (degrees) that
  would put the aim of the camera on that line. Negative = left, positive = right.
- horizontal cyan lines are labelled `T<angle>`: the TILT angle. Positive = up.
- the red cross is where the camera points now; `now P.. T..` is bottom right.

To centre an object: read the P and T labels at the object, then run
`look.sh <P> <T>` with those angles. The lens is a fisheye: labels are exact
near the centre, approximate at the edges. So iterate: look, correct, look
again, until the object is within ~5 degrees of the red cross.

Always use look.sh rather than grabbing /video_feed yourself: the stream
first returns a stale frame from the previous position.

## Loop discipline
At every step, output ONE sentence of observation, then ONE command. Then look
again before deciding the next command. Never chain several moves blind.

## Searching
Scan with `look.sh` at P -90, -45, 0, 45, 90 (T 0, then T -20 for the floor),
and stop at the first frame where the object is visible. The camera can also
look behind (P 180 / -180).

## Approaching
1. Centre the object with the gimbal, note its pan angle P.
2. Turn the body toward it, gimbal back to P0: rotate in short bursts
   (right: `{"T":1,"L":0.2,"R":-0.2}`, left: `{"T":1,"L":-0.2,"R":0.2}`,
   0.5 s then stop), then `look.sh 0 <T>` until the object is near P0.
3. Drive forward in short steps (`{"T":1,"L":0.2,"R":0.2}`, 1 s, then stop),
   looking again after each step. Tilt down as the object gets closer.
4. Stop when the object fills the lower part of the frame (T around -30).
Always send the stop command `{"T":1,"L":0,"R":0}` after each burst.
