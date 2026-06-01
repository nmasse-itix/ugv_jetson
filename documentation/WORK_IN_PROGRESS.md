# Démo Robotique UGV Jetson

## Installation de RHEL 9.4

[Install Red Hat Device Edge on NVIDIA Jetson Orin and IGX Orin](https://developers.redhat.com/learn/rhel/install-red-hat-device-edge-nvidia-jetson-orin-and-igx-orin)

## Configuration de RHEL

```sh
# Register the system on RHN
sudo subscription-manager register --org 1979710 --activationkey REDACTED

# Enable EPEL
sudo dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
sudo crb enable

# Install misc. tools
sudo dnf install -y bluez pciutils usbutils tcpdump htop stress-ng yq podman-compose tmux iptraf-ng mkpasswd cockpit cockpit-podman cockpit-podman cockpit-files cockpit-ostree cockpit-pcp cockpit-system strace NetworkManager-wifi chromium git python3-pip tio

# Enable services
sudo systemctl enable cockpit.socket sshd.service bluetooth.service

# Disable firewalld
sudo systemctl disable --now firewalld

# Nvidia stuff
curl -s -L https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo | sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo
curl -s -L https://repo.download.nvidia.com/jetson/rhel-9.4/jp6.1/nvidia-l4t.repo | sudo tee /etc/yum.repos.d/nvidia-l4t.repo
sudo dnf -y install nvidia-jetpack-kmod nvidia-jetpack-all nvidia-container-toolkit
sudo usermod -aG video,render $USER
sudo grubby --set-default=/boot/vmlinuz-5.14.0-427.42.1.el9_4.aarch64
sudo ln -sf /etc/nvpmodel/nvpmodel_p3767_0003.conf /etc/nvpmodel.conf
sudo reboot
sudo nvpmodel -m 0
sudo tee /etc/nvidia-container-toolkit/nvidia-cdi-refresh.env <<'EOF'
NVIDIA_CTK_DEBUG=1
NVIDIA_CTK_CDI_OUTPUT_FILE_PATH=/etc/cdi/nvidia.yaml
EOF
sudo systemctl daemon-reload
sudo systemctl restart nvidia-cdi-refresh.service
ls -l /etc/cdi/nvidia.yaml
sudo podman login nvcr.io --username='$oauthtoken' --password='REDACTED'
sudo podman pull nvcr.io/nvidia/l4t-jetpack:r36.3.0
sudo pip3 install jetson-stats
sudo systemctl enable --now jtop.service
sudo /usr/local/bin/jtop

# Disable suspend
sudo systemctl mask suspend.target
sudo systemctl mask hibernate.target

# Install a GUI (KDE) and make it the default environment
sudo dnf groupinstall -y "KDE Plasma Workspaces"
sudo usermod -aG video,render sddm
sudo systemctl set-default graphical.target
sudo tee /etc/sddm.conf.d/20-redhat.conf >/dev/null <<'EOF'
[Autologin]
Relogin=true
Session=plasmax11.desktop
User=admin

[General]
DisplayServer=X11
EOF

# Install rustdesk
sudo dnf install -y https://github.com/rustdesk/rustdesk/releases/download/1.4.6/rustdesk-1.4.6-0.aarch64.rpm

# Free the serial ports
sudo systemctl disable --now serial-getty@ttyTCU0.service
sudo systemctl mask serial-getty@ttyTCU0.service

# Connect to Wifi
sudo nmcli device wifi connect ITIX-LAN --ask

# Allow the user to use serial ports
sudo usermod -aG dialout $USER

# Fetch the demo source code
git clone https://github.com/waveshareteam/ugv_jetson.git
cd ugv_jetson
git remote remove origin
git remote add origin git@github.com:nmasse-itix/ugv_jetson.git
sudo podman run --name nvidia-jetpack -d -e DISPLAY=:0 --net=host --device nvidia.com/gpu=all --cgroups=disabled --group-add keep-groups -v /tmp/.X11-unix/:/tmp/.X11-unix --security-opt label=disable -v ${HOME}:${HOME} --entrypoint /bin/sleep -v /run/user/1000/pulse/native:/tmp/pulse-socket -e PULSE_SERVER=unix:/tmp/pulse-socket -v /home/admin/.config/pulse/cookie:/tmp/pulse-cookie:ro -e PULSE_COOKIE=/tmp/pulse-cookie nvcr.io/nvidia/l4t-jetpack:r36.3.0 INF
sudo podman exec -it nvidia-jetpack /bin/bash
```

## Paramétrage du conteneur Jetpack

```sh
groupadd -g 1000 admin
useradd -M -d /home/admin -g 1000 -u 1000 admin
usermod -aG sudo admin
chsh admin -s /bin/bash
apt install vim sudo python3 apt-file pulseaudio-utils
visudo
sudo -u admin -i
cd ~/ugv_jetson/
chmod 755 *.sh
sudo ./setup.sh
./start_jupyter.sh
~/ugv_jetson/ugv-env/bin/python ~/ugv_jetson/app.py
```

