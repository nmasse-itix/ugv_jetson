import cv2
import threading
import time
import numpy as np
import yaml, os, json, subprocess
from collections import deque
import textwrap

# config file.
curpath = os.path.realpath(__file__)
thisPath = os.path.dirname(curpath)
with open(thisPath + '/config.yaml', 'r') as yaml_file:
    f = yaml.safe_load(yaml_file)


class OpencvFuncs():
    """docstring for OpencvFuncs"""
    def __init__(self, project_path, base_ctrl):
        self.base_ctrl = base_ctrl

        self.this_path = project_path
        self.frame_scale = 1
        self.overlay = None
        self.scale_rate = 1
        self.video_quality = f['video']['default_quality']

        # cv ctrl info
        self.cv_light_mode = 0
        self.video_fps = 0
        self.fps_start_time = time.time()
        self.fps_count = 0

        # base data
        self.show_base_info_flag = False
        self.recv_deque = deque(maxlen=20)

        # info update
        self.show_info_flag = False
        self.info_update_time = time.time()
        self.info_deque = deque(maxlen=10)
        self.info_scale = 270 / 480
        self.info_bg_color = (0, 0, 0)
        self.info_show_time = 10
        self.recv_line_max = 26

        # mission funcs
        self.mission_flag = False

        # osd settings
        self.add_osd = f['base_config']['add_osd']
        self.show_cmd_info = f['base_config'].get('show_cmd_info', True)

        # camera type detection
        self.usb_camera_connected = True

        # usb camera init
        self.camera = cv2.VideoCapture(-1)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, f['video']['default_res_w'])
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, f['video']['default_res_h'])



    def frame_process(self):
        try:
            success, input_frame = self.camera.read()
            if not success:
                self.camera.release()
                time.sleep(1)
                self.camera = cv2.VideoCapture(0)
        except Exception as e:
            print(f"[cv_ctrl.frame_process] error: {e}")
            input_frame = 255 * np.ones((480, 640, 3), dtype=np.uint8)
            cv2.putText(input_frame, f"camera read failed... \n{e}",
                        (round(0.05*640), round(0.1*640 + 5 * 13)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.369, (0, 0, 0), 1)
            ret, buffer = cv2.imencode('.jpg', input_frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.video_quality])
            input_frame = buffer.tobytes()
            return input_frame

        if self.show_info_flag:
            if time.time() - self.info_update_time > self.info_show_time:
                self.show_info_flag = False
            try:
                self.overlay = input_frame.copy()
                cv2.rectangle(self.overlay, (round((self.info_scale-0.005)*640), round((0.33)*480)),
                                       (round(0.98*640), round((0.78)*480)),
                                       self.info_bg_color, -1)
                cv2.addWeighted(self.overlay, 0.5, input_frame, 0.5, 0, input_frame)
            except Exception as e:
                print(f"[cv_ctrl.frame_process] error: {e}")

            for i in range(0, len(self.info_deque)):
                cv2.putText(input_frame, str(self.info_deque[i]['text']),
                            (round(self.info_scale*640), round(self.info_scale*640 - i * 20)),
                            cv2.FONT_HERSHEY_SIMPLEX, self.info_deque[i]['size'], self.info_deque[i]['color'], 1)

        if self.show_base_info_flag:
            for i in range(0, len(self.recv_deque)):
                cv2.putText(input_frame, str(self.recv_deque[i]),
                        (round(0.05*640), round(0.1*640 + i * 13)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.369, (255, 255, 255), 1)

        # render osd
        input_frame = self.osd_render(input_frame)

        # frame scale
        if self.scale_rate == 1:
            pass
        else:
            img_height, img_width = input_frame.shape[:2]
            img_width_d2  = img_width/2
            img_height_d2 = img_height/2
            x_start = int(img_width_d2 - (img_width_d2//self.scale_rate))
            x_end   = int(img_width_d2 + (img_width_d2//self.scale_rate))
            y_start = int(img_height_d2 - (img_height_d2//self.scale_rate))
            y_end   = int(img_height_d2 + (img_height_d2//self.scale_rate))
            input_frame = input_frame[y_start:y_end, x_start:x_end]

        # encode frame
        try:
            ret, buffer = cv2.imencode('.jpg', input_frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.video_quality])
            input_frame = buffer.tobytes()
        except:
            pass

        # get fps
        self.fps_count += 1
        if time.time() - self.fps_start_time >= 2:
            self.video_fps = self.fps_count/2
            self.fps_count = 0
            self.fps_start_time = time.time()

        # output frame
        return input_frame



    def usb_camera_detection(self):
        lsusb_output = subprocess.check_output(["lsusb"]).decode("utf-8")
        if "Camera" in lsusb_output:
            print("USB Camera connected")
            return True
        else:
            print("USB Camera not connected")
            return False


    def osd_render(self, osd_frame):
        if not self.add_osd:
            return osd_frame

        # add your osd info here
        # cv2.putText(overlay_buffer, 'OSD_TEST', (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        # render lidar data
        lidar_points = []
        for lidar_angle, lidar_distance in zip(self.base_ctrl.rl.lidar_angles_show, self.base_ctrl.rl.lidar_distances_show):
            lidar_x = int(lidar_distance * np.cos(lidar_angle) * 0.05) + 320
            lidar_y = int(lidar_distance * np.sin(lidar_angle) * 0.05) + 240
            lidar_points.append((lidar_x, lidar_y))

        for lidar_point in lidar_points:
            cv2.circle(osd_frame, lidar_point, 3, (255, 0, 0), -1)

        # render sensor data
        sensor_index = 0
        for sensor_line in self.base_ctrl.rl.sensor_data:
            cv2.putText(osd_frame, sensor_line,
                        (100, 50 + sensor_index * 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
            sensor_index = sensor_index + 1

        return osd_frame

    def scale_ctrl(self, input_rate):
        if input_rate < 1:
            self.scale_rate = 1
        else:
            self.scale_rate = input_rate

    def set_video_quality(self, input_quality):
        if input_quality < 1:
            self.video_quality = 1
        elif input_quality > 100:
            self.video_quality = 100
        else:
            self.video_quality = int(input_quality)

    def info_update(self, megs, color, size):
        if not self.show_cmd_info:
            return
        if megs == -1:
            self.info_update_time = time.time()
            self.show_info_flag = True
            return
        wrapped_lines = textwrap.wrap(megs, self.recv_line_max)
        for line in wrapped_lines:
            self.info_deque.appendleft({'text':line,'color':color,'size':size})
        self.info_update_time = time.time()
        self.show_info_flag = True

    def commandline_ctrl(self, args_str):
        return

    def show_recv_info(self, input_cmd):
        if input_cmd == True:
            self.show_base_info_flag = True
        else:
            self.show_base_info_flag = False
        print(self.show_base_info_flag)

    def format_json_numbers(self, obj):
        if isinstance(obj, dict):
            return {k: self.format_json_numbers(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.format_json_numbers(elem) for elem in obj]
        elif isinstance(obj, float):
            return round(obj, 2)
        return obj

    def update_base_data(self, input_data):
        if not input_data:
            return
        try:
            if self.show_base_info_flag:
                self.recv_deque.appendleft(json.dumps(self.format_json_numbers(input_data)))
            if input_data.get('T') == 1003:
                self.info_deque.appendleft({'text':json.dumps(input_data['mac']),'color':(16,64,255),'size':0.5})
                wrapped_lines = textwrap.wrap(json.dumps(input_data['megs']), self.recv_line_max)
                for line in wrapped_lines:
                    self.info_deque.appendleft({'text':line,'color':(255,255,255),'size':0.5})
                self.info_update_time = time.time()
                self.show_info_flag = True
        except Exception as e:
            print(f"[cv_ctrl.update_base_data] error: {e}")

    def head_light_ctrl(self, input_mode):
        self.cv_light_mode = input_mode
        if input_mode == 0:
            self.base_ctrl.lights_ctrl(self.base_ctrl.base_light_status, 0)
            self.cv_light_mode = input_mode
        elif input_mode == 2:
            self.base_ctrl.lights_ctrl(self.base_ctrl.base_light_status, 255)
            self.cv_light_mode = input_mode
        elif input_mode == 3:
            if self.cv_light_mode == 1:
                return
            elif self.base_ctrl.head_light_status == 0:
                self.cv_light_mode = 2
                self.base_ctrl.lights_ctrl(self.base_ctrl.base_light_status, 255)
            elif self.base_ctrl.head_light_status != 0:
                self.cv_light_mode = 0
                self.base_ctrl.lights_ctrl(self.base_ctrl.base_light_status, 0)

    def timelapse(self, input_speed, input_time, input_interval, input_loop_times):
        self.mission_flag = True
        for i in range(0, input_loop_times):
            if not self.mission_flag:
                self.mission_flag = False
                break
            self.base_ctrl.base_json_ctrl({"T":1,"L":input_speed,"R":input_speed})
            time.sleep(input_time)
            self.base_ctrl.base_json_ctrl({"T":1,"L":0,"R":0})
            time.sleep(input_interval/2)
            self.base_ctrl.lights_ctrl(255, 255)
            time.sleep(0.01)
            self.base_ctrl.lights_ctrl(0, 0)
            time.sleep(input_interval/2)
            if not self.mission_flag:
                self.mission_flag = False
                break

    def mission_stop(self):
        self.mission_flag = False
