import os, psutil, time
import subprocess, re, netifaces
import threading
from jtop import jtop

curpath = os.path.realpath(__file__)
thisPath = os.path.dirname(curpath)

class SystemInfo(threading.Thread):
    """docstring for SystemInfo"""
    @staticmethod
    def _find_interface(prefixes, exclude_prefixes=()):
        for iface in netifaces.interfaces():
            if iface == 'lo':
                continue
            if any(iface.startswith(p) for p in exclude_prefixes):
                continue
            if any(iface.startswith(p) for p in prefixes):
                return iface
        return None

    def __init__(self):
        self.cpu_load = 0
        self.cpu_temp = 0
        self.ram = 0
        self.wifi_rssi = 0

        self.net_interface = self._find_interface(('wlan', 'wl')) or "wlan0"
        self._eth_interface = self._find_interface(('eth', 'en'), exclude_prefixes=('wlan', 'wl')) or "eth0"
        self.wlan_ip = "None"
        self.eth0_ip = "None"
        self.wifi_mode = "None"

        self.update_interval = 2

        super(SystemInfo, self).__init__()
        self.__flag = threading.Event()
        self.__flag.clear()

    def get_info_jtop(self):
        try:
            with jtop() as jetson:
                if jetson.ok():
                    self.cpu_temp = round(jetson.stats['Temp cpu'], 2)
                    self.ram = round(jetson.memory['RAM']['used']/jetson.memory['RAM']['tot']*100, 2)
                    self.cpu_load = jetson.stats['CPU1']
        except Exception:
            pass

    def get_ip_address(self, interface):
        try:
            interface_info = netifaces.ifaddresses(interface)
            ipv4_info = interface_info.get(netifaces.AF_INET, [{}])
            return ipv4_info[0].get('addr')
        except ValueError:
            print(f"Interface {interface} not found.")
            return None
        except IndexError:
            print(f"No IPv4 address assigned to {interface}.")
            return None

    def get_wifi_mode(self):
        if self.wlan_ip == '192.168.50.5':
            return "AP"
        else:
            return "STA"

    def get_signal_strength(self):
        return 0

    def change_net_interface(self, new_interface):
        self.net_interface = new_interface

    def pause(self):
        self.__flag.clear()

    def resume(self):
        self.__flag.set()

    def run(self):
        self.eth0_ip = self.get_ip_address(self._eth_interface)
        self.wlan_ip = self.get_ip_address(self.net_interface)
        self.wifi_mode = self.get_wifi_mode()
        self.wifi_rssi = self.get_signal_strength()
        while True:
            self.get_info_jtop()
            self.wifi_rssi = self.get_signal_strength()
            time.sleep(0.5)
            self.wifi_mode = self.get_wifi_mode()
            time.sleep(0.5)
            self.wlan_ip = self.get_ip_address(self.net_interface)
            time.sleep(0.5)
            self.eth0_ip = self.get_ip_address(self._eth_interface)
            time.sleep(0.5)
            self.__flag.wait()






if __name__ == "__main__":
    si = SystemInfo()
    # si.update_folder(thisPath)
    si.start()
    si.resume()
    while True:
        # print([si.get_cpu_temperature, si.pictures_size, si.videos_size, si.cpu_load, si.cpu_temp,
        #     si.ram, si.wifi_rssi, si.wifi_mode])
        # print(si.cpu_temp)
        # si.get_memory_percent()

        si.get_signal_strength()

        # with jtop() as jetson:
        #     if jetson.ok():
        #         print(jetson.stats['CPU1'])
        
        time.sleep(3)