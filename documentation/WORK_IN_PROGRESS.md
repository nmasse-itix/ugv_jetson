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
sudo dnf install -y bluez pciutils usbutils tcpdump htop stress-ng yq podman-compose tmux iptraf-ng mkpasswd cockpit cockpit-podman cockpit-podman cockpit-files cockpit-ostree cockpit-pcp cockpit-system strace NetworkManager-wifi chromium git python3-pip tio pulseaudio-utils

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

# Switch to PulseAudio
#sudo dnf remove -y pipewire pipewire-pulseaudio
#systemctl --user mask pipewire-pulse.socket pipewire-pulse.service
#sudo dnf install pulseaudio pulseaudio-utils
#systemctl --user enable --now pulseaudio.socket pulseaudio.service

# Fetch the demo source code
git clone https://github.com/waveshareteam/ugv_jetson.git
cd ugv_jetson
git remote remove origin
git remote add origin git@github.com:nmasse-itix/ugv_jetson.git
```

Préparer le conteneur Nvidia Jetpack:

```sh
declare -a podman_args=(
  --name nvidia-jetpack
  # Use the host's network stack
  --net=host
  # Fix sudo warning message about audit subsystem not being available
  --cap-add=AUDIT_WRITE
  # Mount the project source code to run setup.sh
  -v $HOME/ugv_jetson:$HOME/ugv_jetson
  # Run bash
  --entrypoint /bin/bash
)
IMAGE=nvcr.io/nvidia/l4t-jetpack:r36.3.0
sudo podman run "${podman_args[@]}" $IMAGE
```

## Paramétrage du conteneur Jetpack

Dans le conteneur:

```sh
groupadd -g 1000 admin
useradd -M -d /home/admin -g 1000 -u 1000 admin
usermod -aG sudo admin
chsh admin -s /bin/bash
apt update
apt install vim sudo python3 apt-file pulseaudio-utils strace espeak-ng espeak-ng-data
# Fix HMAC mismatch: RHEL Python 3.9 uses SHA-256 for multiprocessing auth, Ubuntu Python 3.10 defaults to MD5
sed -i "s/hmac.new(authkey, message, 'md5')/hmac.new(authkey, message, 'sha256')/g" \
  /usr/lib/python3.10/multiprocessing/connection.py
sudo tee /etc/sudoers.d/admin >/dev/null <<'EOF'
admin ALL=(ALL) NOPASSWD:ALL
EOF
sudo -u admin -EH /bin/bash
echo "PS1='\u@jetpack-container:\w\\\$ '" >> ~/.bashrc
cd ~/ugv_jetson/
chmod 755 *.sh
sudo ./setup.sh
sudo pip3 install jetson-stats
mkdir -p ~/.config/pulse
```

Prendre un instantané du conteneur:

```sh
sudo podman commit nvidia-jetpack nvidia-jetpack:$(date -Idate)
IMAGE=nvidia-jetpack:$(date -Idate)
sudo podman stop nvidia-jetpack
sudo podman rm nvidia-jetpack
```

## Utiliser le conteneur Jetpack

```sh
declare -a podman_args=(
  --name nvidia-jetpack
  # Run the container in privileged mode to allow access to the GPU and serial ports
  --privileged
  # Run the container in detached mode
  -d
  # Allow the container to access the host's display server
  -e DISPLAY=:0
  -v /tmp/.X11-unix/:/tmp/.X11-unix
  # Use the host's network stack
  --net=host
  # Allow the container to access the GPU
  --device nvidia.com/gpu=all
  # Disable cgroups because Podman fails at inserting the device filter eBPF program
  --cgroups=disabled
  # Copy the group membership of the current user to the container so it can access the GPU, camera and serial ports
  --group-add $(getent group video | cut -d: -f3)
  --group-add $(getent group render | cut -d: -f3)
  --group-add $(getent group dialout | cut -d: -f3)
  --group-add $(getent group jtop | cut -d: -f3)
  # Disable security labels because they prevent the container from accessing the GPU
  --security-opt label=disable
  # Mount the project source code to the container so we can easily edit files from the host and run scripts from the container
  -v $HOME/ugv_jetson:$HOME/ugv_jetson
  # Pass through all V4L2 camera devices
  $(for d in /dev/video*; do [[ -c "$d" ]] && echo "--device $d"; done)
  # Allow the container to access the host's audio server
  -v /run/user/1000/pulse/native:/tmp/pulse-socket
  -e PULSE_SERVER=unix:/tmp/pulse-socket
  -v /home/admin/.config/pulse/cookie:/tmp/pulse-cookie:ro
  -e PULSE_COOKIE=/tmp/pulse-cookie
  # Allow the container to access jtop.service (Jetson stats daemon) via its Unix socket
  -v /run/jtop.sock:/run/jtop.sock
  --group-add $(getent group jtop | cut -d: -f3)
  # Set the entrypoint to sleep infinity so the container doesn't exit immediately and we can exec into it
  --entrypoint /bin/sleep
  # Run the container as the current user so files created by the container are owned by the current user
  --user $(id -u):$(id -g)
  # Set the working directory to the project source code
  --workdir $HOME/ugv_jetson
)
sudo podman run "${podman_args[@]}" $IMAGE INF
sudo podman exec -it nvidia-jetpack /bin/bash
```

## Utiliser la démo

```sh
./start_jupyter.sh &
~/ugv_jetson/ugv-env/bin/python ~/ugv_jetson/app.py
```
