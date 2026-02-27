import cv2
import threading
import datetime, time
import numpy as np
import math
import yaml, os, json, subprocess

log_file_path = "./Mediamtx/mediamtx.log"

with open(log_file_path, "w") as log_file:
    mediamtx_command = [
        './Mediamtx/mediamtx',
        './Mediamtx/mediamtx.yml',
    ]
    mediamtx_process = subprocess.Popen(
        mediamtx_command,
        stdout=log_file,
        stderr=log_file
    )

ffmpeg_command = [
    'ffmpeg',
    '-y',
    '-loglevel', 'quiet',    
    '-f', 'rawvideo',         
    '-vcodec', 'rawvideo',
    '-pix_fmt', 'bgr24',       
    '-s', '640x480',           
    '-r', '30',                
    '-i', '-',                 
    '-c:v', 'libx264',         
    '-b:v', '300k',
    '-crf', '28',             
    '-pix_fmt', 'yuv420p',
    '-preset', 'ultrafast',
    '-tune', 'zerolatency',
    '-f', 'rtsp',              
    'rtsp://localhost:8554/cam'
]

class OpencvFuncs():
    """docstring for OpencvFuncs"""
    def __init__(self):
        self.ffmpeg_process = subprocess.Popen(ffmpeg_command, stdin=subprocess.PIPE)
        self.gst_str = (
          'nvarguscamerasrc sensor-id=%d ! video/x-raw(memory:NVMM), width=%d, height=%d, format=(string)NV12, '
          'framerate=(fraction)%d/1 ! nvvidconv ! video/x-raw, width=(int)%d, height=(int)%d, format=(string)BGRx ! '
          'videoconvert ! appsink' % (0, 640, 480, 30, 640, 480)
        )
        # camera type detection
        self.usb_camera_connected = self.usb_camera_detection()
        self.csi_camera_connected = False
        self.oak_camera_connected = False

        # usb camera init
        if self.usb_camera_connected:
            self.camera = cv2.VideoCapture(0)
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # csi camera init
        if not self.usb_camera_connected:
            try:
                print("Initializing CSI camera...")
                
                self.csi_camera = cv2.VideoCapture(self.gst_str, cv2.CAP_GSTREAMER)
                self.csi_camera_connected = True
                print("CSI camera initialized")
                return
            except Exception as e:
                print(f"CSI init failed: {e}")
                self.csi_camera_connected = False

        #oak camera init 
        if not self.usb_camera_connected and not self.csi_camera_connected:
            try:
                # libraries for oak camera
                import depthai as dai
                self.pipeline = dai.Pipeline()

                self.camRgb = self.pipeline.createColorCamera()
                self.camRgb.setBoardSocket(dai.CameraBoardSocket.RGB)
                self.camRgb.setInterleaved(False)
                # self.camRgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_480_P)
                self.camRgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_720_P)

                self.xout = self.pipeline.createXLinkOut()
                self.xout.setStreamName("video")
                self.camRgb.video.link(self.xout.input)

                self.device = dai.Device(self.pipeline)
                self.output_queue = self.device.getOutputQueue(name="video", maxSize=8, blocking=False)

                self.oak_camera_connected = True
            except Exception as e:
                print(f"[cv_ctrl.frame_process] error: {e}")
                self.oak_camera_connected = False


    def frame_process(self):
        while True:
            try:
                if self.usb_camera_connected:
                    success, input_frame = self.camera.read()
                    if not success:
                        self.camera.release()
                        time.sleep(1)
                        self.camera = cv2.VideoCapture(0)
                elif self.csi_camera_connected:
                    success, input_frame = self.csi_camera.read()
                    if not success or input_frame is None:
                        self.csi_camera.release()
                        time.sleep(1)
                        self.csi_camera = cv2.VideoCapture(self.gst_str, cv2.CAP_GSTREAMER)
                elif self.oak_camera_connected:
                    input_frame = self.output_queue.get().getCvFrame()
                    input_frame = cv2.resize(input_frame, (640, 480))
                else:
                    input_frame = 255 * np.ones((480, 640, 3), dtype=np.uint8)
                    cv2.putText(input_frame, f"camera read failed... \nusb - csi - oak", 
                                (round(0.05*640), round(0.1*640 + 5 * 13)), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.369, (0, 0, 0), 1)
            except Exception as e:
                print(f"[cv_ctrl.frame_process] error: {e}")
                input_frame = 255 * np.ones((480, 640, 3), dtype=np.uint8)
                cv2.putText(input_frame, f"camera read failed... \n{e}", 
                            (round(0.05*640), round(0.1*640 + 5 * 13)), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.369, (0, 0, 0), 1)
        
            # encode frame
            try:
                self.ffmpeg_process.stdin.write(input_frame.tobytes())
            except:
                pass

            # time.sleep(1/30)

    def usb_camera_detection(self):
        lsusb_output = subprocess.check_output(["lsusb"]).decode("utf-8")
        if "Camera" in lsusb_output:
            print("USB Camera connected")
            return True
        else:
            print("USB Camera not connected")
            return False
