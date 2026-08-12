# Actions en cours

## Faire fonctionner la carte son

**Statut : RÉSOLU sur RHEL 9.8** (validé bout en bout le 2026-08-12 sur `nmasse@192.168.1.122`, Jetson Orin Nano Developer Kit, kernel `5.14.0-687.5.3.el9_8.aarch64`).

> **Réserve** : ce résultat vaut pour une machine **sans** la stack GPU Nvidia. Installer JetPack par la voie RPM rebascule sur le kernel 9.4 et **recasse l'audio** — voir [Cause racine réelle](#cause-racine-réelle-corrigée). La coexistence GPU + audio dépend de l'image bootc `nvidia-jetpack-for-rhel`, dont l'accès est actuellement bloqué (voir plus bas).

### Ce qui débloque la situation

Le dilemme décrit précédemment (« GPU Nvidia **ou** audio, pas les deux ») **ne s'applique pas à ce projet** : le code n'utilise pas le GPU du tout.

Inventaire complet des imports du projet : `cv2`, `numpy`, `flask`, `flask_socketio`, `aiortc`, `pygame`, `pyttsx3`, `serial`, `netifaces`, `psutil`, `jtop`. Aucun `torch`, `tensorrt`, `pycuda`, ni `mediapipe`. Aucune occurrence de `cv2.dnn`, `setPreferableBackend` / `setPreferableTarget`, ni de la moindre chaîne `cuda`/`CUDA` dans les `.py`. Les modèles présents dans `models/` (MobileNet-SSD Caffe, cascade de Haar) ne sont chargés nulle part — ce sont des reliquats. Le traitement d'image est du OpenCV CPU pur.

Conclusion : on abandonne le kernel 9.4 + `nvidia-jetpack-kmod` et on part sur **RHEL 9.8**, dont le kernel embarque ALSA complet. On perd `nvgpu` (le GPU à `17000000.gpu` reste sans driver), ce qui est sans conséquence ici.

### Cause racine réelle (corrigée)

La version précédente de cette note attribuait l'absence d'ALSA à un kernel « fourni par Nvidia ». **C'est faux, et la nuance est importante.**

Le dépôt L4T ne contient **aucun paquet kernel**. `nvidia-jetpack-kmod` se contente d'exiger le kernel **stock de Red Hat** :

```
$ dnf repoquery --repo=l4t --requires nvidia-jetpack-kmod
kernel-core = 5.14.0-427.42.1.el9_4
kernel-modules = 5.14.0-427.42.1.el9_4
```

C'est donc bien Red Hat — et non Nvidia — qui a construit le kernel 9.4 aarch64 sans ALSA. Vérifié en extrayant la config des RPM officiels :

| Kernel | `CONFIG_SOUND` | `CONFIG_SND` | `CONFIG_SND_USB_AUDIO` |
|---|---|---|---|
| `5.14.0-427.42.1.el9_4` (stock RHEL 9.4) | `m` | **not set** | absent |
| `5.14.0-687.5.3.el9_8` (stock RHEL 9.8) | `m` | `m` | `m` |

Autrement dit **Red Hat a activé ALSA entre 9.4 et 9.8**. Aucun rebuild de kernel n'est nécessaire : il suffit de tourner sur le kernel 9.8.

Corollaire à retenir : `nvidia-jetpack-kmod` **épingle en dur** (`=`) le kernel 9.4. Installer JetPack et booter sur ce kernel, c'est réintroduire mécaniquement la panne audio. Les deux exigences sont mutuellement exclusives tant que Nvidia ne publie pas de build pour un kernel ≥ 9.8.

### Le dépôt Nvidia est bien vivant (correction)

Autre affirmation erronée à corriger : le dépôt L4T pour RHEL **n'a pas disparu**. Un `GET` sur le répertoire renvoie 404 uniquement parce que l'indexation est désactivée, et l'index HTML de `repo.download.nvidia.com/jetson/` ne le référence pas — mais le dépôt répond parfaitement :

```
https://repo.download.nvidia.com/jetson/rhel-9.4/jp6.1/nvidia-l4t.repo      → 200
https://repo.download.nvidia.com/jetson/rhel-9.4/jp6.1/repodata/repomd.xml  → 200
https://repo.download.nvidia.com/jetson/jetson_rpm_prod.pub                 → 200
```

Ne jamais conclure à la mort d'un dépôt sur un 404 de listing : tester `repodata/repomd.xml`.

En revanche, `rhel-9.4/jp6.0`, `jp6.2` et `jp6.2.2` renvoient bien 404 sur `repomd.xml`. Balayage systématique de `rhel-9.{4,5,6,7,8}` × `jp6.{1,2,2.2,3}` / `jp7.{0,1,2}` sur `repodata/repomd.xml` : **une seule combinaison existe, `rhel-9.4/jp6.1`**. La voie RPM est donc définitivement épinglée au kernel 9.4.

### État vérifié du matériel

Le kernel 9.8 charge `snd_usb_audio` automatiquement, sans intervention :

```
$ cat /proc/asound/cards
 0 [Device         ]: USB-Audio - USB PnP Audio Device
                      Solid State System Co.,Ltd. USB PnP Audio Device at usb-3610000.usb-2.1.1, full
$ aplay -l   → card 0, device 0 : USB Audio (playback)
$ arecord -l → card 0, device 0 : USB Audio (capture)
$ amixer -c 0 scontrols → 'Speaker', 'Mic'
```

La lecture **et** la capture fonctionnent. La capture exige `-c 2` (le device refuse le mono : `arecord: set_params: Channels count non available`).

### Installation requise

Le kernel suffit côté noyau ; il ne manquait que l'espace utilisateur.

Repos RHEL officiels (système enregistré, Simple Content Access) :

```bash
sudo subscription-manager repos \
  --enable=rhel-9-for-aarch64-baseos-rpms \
  --enable=rhel-9-for-aarch64-appstream-rpms
```

**Tous les paquets audio nécessaires sont dans `rhel-9-for-aarch64-appstream-rpms`** — y compris `espeak-ng`, qu'on aurait pu croire réservé à EPEL. **EPEL n'est donc pas nécessaire** pour l'audio.

Paquets :

```bash
sudo dnf install -y alsa-utils espeak-ng
python3 -m pip install --user pygame pyttsx3
```

- `alsa-lib` est la seule dépendance stricte à l'exécution (tirée automatiquement) ; `alsa-utils` apporte `aplay`/`amixer`/`alsactl`, utiles pour le volume, le diagnostic et la persistance.
- `espeak-ng` est nécessaire à `pyttsx3` (il fournit `libespeak-ng.so.1`, que pyttsx3 sait charger).
- **Le RPM `SDL2` n'est pas nécessaire** : les wheels `pygame` embarquent leur propre SDL (2.28.4) dans `site-packages/pygame.libs/` et ignorent le SDL système. Vérifié en désinstallant `SDL2` — l'audio continue de fonctionner.

Volume réglé puis persisté (`alsa-restore` le recharge au boot) :

```bash
amixer -c 0 sset Speaker 80% unmute
amixer -c 0 sset Mic 80% cap
sudo alsactl store
```

### Validation effectuée

- `speaker-test -D hw:0,0 -c 2 -t sine -f 440` : OK.
- `arecord -c 2 -d 2` : signal réel capté (amplitude max 2152, pas du silence).
- **Lecture simultanée** `aplay` + `espeak-ng` : OK — `dmix` mixe plusieurs clients, donc un effet sonore et la synthèse vocale peuvent se superposer sans se bloquer.
- `pygame.mixer` en headless, **sans** `SDL_AUDIODRIVER` : SDL détecte ALSA tout seul. Les `.mp3` réels du projet sont lus avec leurs durées correctes (`connected.mp3` 2.01 s, `started.mp3` 2.81 s).
- `pyttsx3` : synthèse vocale OK.
- `audio_ctrl.py` importé tel quel : `usb_connected = True`, `play_audio_thread()` et `play_speech_thread()` s'exécutent sans erreur.
- **Boucle acoustique** (preuve que le son sort réellement du haut-parleur) : enregistrement au micro pendant la lecture d'un 440 Hz. La composante 440 Hz passe de 5114 à 16258 en magnitude FFT (×3,2). L'amplitude brute ne montrait rien car le dongle USB émet un bruit parasite à ~15,4 kHz qui domine le max/RMS.

L'intégralité de ces tests a été rejouée après le basculement sur les paquets RHEL — résultats identiques.

### Horloge (prérequis découvert au passage)

La machine n'avait **ni `chrony` installé ni NTP actif**, et son horloge dérivait d'environ 18 h, ce qui faisait échouer la validation d'entitlement (`The system clock is skewed... Please check your clock settings`). Le Jetson Orin Nano Developer Kit n'a pas de pile RTC : sans NTP, l'horloge repart à zéro à chaque coupure et l'abonnement RHEL casse.

```bash
sudo dnf install -y chrony && sudo systemctl enable --now chronyd
```

### Correctif de code

`audio_ctrl.py` appelait `pactl` sans protection au moment de l'import. Sur une install ALSA pure (pas de PulseAudio/PipeWire), `pactl` est absent et `subprocess.run` lève un `FileNotFoundError` non rattrapé — **le module entier échouait à l'import**, ce qui cassait `app.py`. L'appel est désormais protégé par `try/except OSError` et devient un no-op silencieux quand `pactl` n'existe pas.

### Points d'attention connexes (hors périmètre audio, découverts au passage)

Deux blocages à prévoir pour le déploiement complet sur RHEL 9.8, tous deux **confirmés** sur la machine de test :

1. **`os_info.py` : `from jtop import jtop` au niveau module.** L'usage est protégé par un `try/except` dans `get_info_jtop()`, mais pas l'import de tête — `ModuleNotFoundError: No module named 'jtop'` vérifié. `app.py` échouerait donc au démarrage. Correctif simple : `pip install jetson-stats` (wheel pur-python `jetson_stats-7.2.1-py3-none-any.whl`, s'installe sans la stack Nvidia). L'import passe alors, et les appels runtime retombent proprement dans le `except` existant faute de daemon `jtop`.

2. **`netifaces` ne s'installe pas sans compilateur** : pas de wheel aarch64, build depuis les sources → `error: command 'gcc' failed: No such file or directory`. Prévoir `sudo dnf install -y gcc python3-devel` (ou remplacer `netifaces`, non maintenu depuis 2021, par `psutil.net_if_addrs()` qui est déjà une dépendance du projet).

### Voie de sortie : l'image bootc `nvidia-jetpack-for-rhel` (RHEL 9.8)

**C'est la piste qui réconcilie GPU et audio.** Red Hat a mis à jour la solution [access.redhat.com/solutions/7140448](https://access.redhat.com/solutions/7140448), dont l'*Environment* est désormais **« Red Hat Enterprise Linux 9.8 (General availability) »**. JetPack pour RHEL n'est plus livré en RPM mais comme **image bootc** :

```
registry.redhat.io/rhel9/nvidia-jetpack-for-rhel:latest
```

Points clés de la solution :

- L'image est « explicitly built on top of `rhel-bootc` », en **image mode** dès l'installation.
- Installation par Kickstart avec `ostreecontainer --url registry.redhat.io/rhel9/nvidia-jetpack-for-rhel:latest`, ISO préparée via `mkksiso` (paquet `lorax`). Le paramètre kernel `pd_ignore_unused` est toujours requis.
- Mises à jour par `bootc upgrade` / `bootc switch` — **plus de cycle `dnf update`**.
- Vérification attendue : `nvidia-smi` → *Driver 540.4.0, CUDA 12.6, GPU Orin (nvgpu)*, plus `tegrastats`. Même génération JetPack que `jp6.1`, mais reconstruite sur 9.8.

#### Statut : BLOQUÉ sur l'accès à l'image (au 2026-08-12)

L'image est **restreinte** : un compte RHN standard ne suffit pas à la tirer. Une demande d'autorisation est en cours en interne chez Red Hat. Tant qu'elle n'aboutit pas, la piste ne peut être ni validée ni écartée.

Ce qui a été tenté, sans succès :

| Tentative | Résultat |
|---|---|
| `skopeo inspect docker://registry.redhat.io/rhel9/nvidia-jetpack-for-rhel:latest` (anonyme) | 401 — *Please login to the Red Hat Registry* |
| API catalogue public, `filter=repository==rhel9/nvidia-jetpack-for-rhel` | `{"data": [], "total": 0}` — non indexée |
| Recherche d'errata public référençant l'image | Rien ; `RHBA-2026:46821` concerne `nvidia/gpu-driver-rhel9` (GPU discrets), pas le Tegra |
| Compte RHN du projet | Accès refusé à l'image |

**Question ouverte, décisive** : le NVR exact du kernel embarqué. Si c'est un `5.14.0-687.*.el9_8` (base `rhel-bootc` 9.8), alors `CONFIG_SND=m` et **on obtient GPU + audio simultanément** — le dilemme disparaît. Si Nvidia y a réintroduit un kernel 9.4, on reste au point de départ.

Indice en faveur de la première hypothèse (déduction, pas preuve) : le KB annonce `nvidia-smi` → *Driver 540.4.0 / CUDA 12.6*, soit la même génération que `jp6.1`, mais republiée sur une base 9.8 — ce qui suppose des kmods recompilés contre le kernel 9.8.

À exécuter **dès que l'accès est débloqué** — une seule commande tranche :

```bash
podman login registry.redhat.io          # Registry Service Account
podman run --rm registry.redhat.io/rhel9/nvidia-jetpack-for-rhel:latest rpm -q kernel-core
```

Si la réponse commence par `kernel-core-5.14.0-687` → feu vert, et l'audio survit à l'installation du GPU.

**Conséquence structurante si on bascule** : en image mode, `/usr` est immuable et les `dnf install` ne persistent pas. Les paquets audio (`alsa-utils`, `espeak-ng`) devront passer dans une couche `Containerfile` (`FROM registry.redhat.io/rhel9/nvidia-jetpack-for-rhel:latest` + `RUN dnf -y install ...`). En revanche les `pip install --user` restent valides : `/home`, `/etc` et `/var` sont préservés à travers les upgrades.

**Sans rapport avec le Jetson** : les annonces publiques Red Hat/Nvidia de janvier 2026 (« Day 0 » pour Vera Rubin, drivers OpenRM et CUDA dans les dépôts RHEL) concernent le **datacenter** (Grace-Hopper / Vera Rubin), pas le Tegra. L'image `registry.redhat.io/nvidia/gpu-driver-rhel9` qui en découle est pour GPU discrets. Elle ne nous sert à rien ici.

## Faire fonctionner l'UART1 du Jetson Orin Nano (pins 8/10 du header 40 pins)

Besoin : le Rover est piloté via une liaison série UART, et le header 40 pins du Jetson Orin Nano expose un port UART1 (TX sur pin 8, RX sur pin 10) qui serait idéal pour cette liaison.
Cependant, ce port est désactivé dans le device tree fourni par l'UEFI de la carte.

Contournement temporaire : utiliser un adaptateur USB-UART qui apparaît comme `ttyUSB0` et fonctionne sans configuration supplémentaire.
Cela permet de faire tourner le projet dans un conteneur Jetpack sans toucher au device tree ni au bootloader.

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
