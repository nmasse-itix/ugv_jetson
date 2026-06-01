# Actions en cours

## Debug du port série UART1

```
[admin@localhost ugv_jetson]$ sudo dmesg | grep -E 'serial|tty'
[    0.000386] printk: console [tty0] enabled
[    0.033759] 31d0000.serial: ttyAMA0 at MMIO 0x31d0000 (irq = 15, base_baud = 0) is a SBSA
[    1.491410] printk: console [ttyTCU0] enabled
[    1.713829] usbcore: registered new interface driver usbserial_generic
[    1.719000] usbserial: USB Serial support registered for generic
[   10.649635] systemd[1]: Created slice Slice /system/getty.
[   10.651701] systemd[1]: Created slice Slice /system/serial-getty.
[   11.724255] cdc_acm 1-2.1.2:1.0: ttyACM0: USB ACM device

[admin@localhost ugv_jetson]$ ls -l /dev/tty* | grep -E '/dev/tty[A-Za-z]+[0-9]+'
crw-rw----. 1 root dialout 166,  0 31 mai   15:39 /dev/ttyACM0
crw-rw----. 1 root dialout 204, 64 31 mai   15:39 /dev/ttyAMA0
crw-rw----. 1 root dialout   4, 64 31 mai   15:39 /dev/ttyS0
crw-rw----. 1 root dialout   4, 65 31 mai   15:39 /dev/ttyS1
crw-rw----. 1 root dialout   4, 66 31 mai   15:39 /dev/ttyS2
crw-rw----. 1 root dialout   4, 67 31 mai   15:39 /dev/ttyS3
crw--w----. 1 root tty     244,  0 31 mai   15:39 /dev/ttyTCU0

[admin@localhost ugv_jetson]$  for n in /sys/class/tty/ttyS* /sys/class/tty/ttyTHS*; do
    [ -e "$n" ] || continue
    echo "$(basename $n) -> $(readlink -f $n/device)"
  done
ttyS0 -> /sys/devices/platform/serial8250
ttyS1 -> /sys/devices/platform/serial8250
ttyS2 -> /sys/devices/platform/serial8250
ttyS3 -> /sys/devices/platform/serial8250

[admin@localhost ugv_jetson]$ for d in /proc/device-tree/serial@* /proc/device-tree/*/serial@*; do
    [ -e "$d" ] || continue
    echo "$(basename $d): status=$(tr -d '\0' < $d/status 2>/dev/null)"
  done
serial@3100000: status=disabled
serial@3110000: status=disabled
serial@3140000: status=disabled
serial@31d0000: status=okay

[admin@localhost ugv_jetson]$ ls -d /sys/bus/platform/devices/*serial* 2>/dev/null
/sys/bus/platform/devices/31d0000.serial  /sys/bus/platform/devices/serial  /sys/bus/platform/devices/serial8250

[admin@localhost ugv_jetson]$ sudo dmesg | grep -iE 'serial-tegra|tegra.*uart|ttyTHS|3100000'
```

Résumé de session — identification et activation d'un port série sur Jetson Orin Nano (RHEL 9.4).

Contexte : Jetson Orin Nano Developer Kit sous RHEL 9.4 (kernel `5.14.0-427.42.1.el9_4.aarch64` + `nvidia-jetpack-kmod`, boot UEFI + GRUB/BLS), objectif faire tourner le code Waveshare `ugv_jetson` dans un conteneur `nvcr.io/nvidia/l4t-jetpack:r36.3.0`. Besoin initial : trouver le bon port série correspondant au header 40 pins.

Inventaire des ttys observés : `ttyTCU0` = Tegra Combined UART (console de debug firmware/UEFI/kernel/getty), `ttyAMA0` = UART SBSA à `0x31d0000` (status okay), `ttyACM0` = périphérique USB ACM (candidat probable pour la carte du robot connectée en USB), `ttyS0`–`ttyS3` = emplacements 8250 « fantômes » non câblés (tous pointent vers `/sys/devices/platform/serial8250`, à ignorer). Aucun `ttyTHS*` présent.

État des UART dans le device tree : `serial@3100000` (UART1, pins 8 TX / 10 RX du header 40 pins) = disabled ; `serial@3110000` (UART2) = disabled ; `serial@3140000` = disabled ; `serial@31d0000` (SBSA / ttyAMA0) = okay.

Constat clé sur le boot et le device tree : `jetson-io` n'est pas packagé pour RHEL (`dnf provides` ne trouve rien). Le device tree est fourni par l'UEFI (le nœud `chosen/` contient `linux,uefi-mmap-*` et `linux,uefi-system-table`, aucune ligne `devicetree` dans les entrées BLS, et le modèle qui tourne « Orin Nano Developer Kit » ne correspond à aucun `.dtb` de `/boot/dtb/nvidia/`, qui ne contient que des DTB AGX/Xavier de la distro). Donc l'UART1 est désactivé dans le DTB chargé depuis la partition firmware QSPI, et les outils L4T habituels ne peuvent pas le modifier sur cette install.

Vérifications faites : aucun `tegra234-p376*.dtb` ni aucun `.dtbo` sur le disque, pas de support d'overlay configfs à chaud (`/sys/kernel/config/device-tree/overlays/` absent), mais `/sys/firmware/fdt` (DTB live, ~245 Ko) est lisible par root.

Piste écartée — réserver `ttyTCU0` : techniquement possible au runtime (retirer la console kernel via grubby `console=tty0` + retrait de `earlycon`/`console=ttyTCU0`, getty déjà masqué dans l'install), mais le firmware (MB1/MB2/BPMP/UEFI) et l'early kernel écrivent sur ce port à chaque boot et on ne peut pas les faire taire depuis Linux (ça nécessiterait un reflash). Décision : abandonner cette piste.

Piste à creuser en premier (la moins coûteuse) : vérifier si la carte « General Driver for Robots » du kit est en fait connectée en USB et énumère comme `ttyACM0` (via `udevadm info -q property -n /dev/ttyACM0` + test débranchement/rebranchement sous `dmesg -w`). Si oui, pointer simplement la conf du soft sur `/dev/ttyACM0` et l'activation de l'UART du header devient inutile.

Solution retenue si le header 40 pins est réellement nécessaire : override GRUB. Dériver un DTB depuis `/sys/firmware/fdt`, y passer `serial@3100000` en `status="okay"` (et corriger le pinmux des pads pins 8/10 si elles sont en GPIO et non en fonction UART), recompiler avec `dtc`, le déposer dans `/boot/dtb-custom/`, puis créer une nouvelle entrée BLS (sans toucher l'actuelle, gardée en filet de sécurité) avec une directive `devicetree /dtb-custom/orin-uart1.dtb`. Risque : charger un DTB via GRUB remplace celui de l'UEFI — partir du DTB live limite le risque (carveouts/fixups présents) mais il faut conserver l'entrée d'origine pour rebooter dessus en cas de régression GPU/nvgpu.

Prochaine étape en attente : installer `dtc`, dumper `/sys/firmware/fdt`, le décompiler, puis fournir les sorties de `grep -n -A20 'serial@3100000' /tmp/current.dts` et `grep -in 'uart1' /tmp/current.dts` pour déterminer les éditions exactes (statut du nœud + pinmux) avant recompilation.
