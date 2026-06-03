# Interface Web — Contrôles Vision par Ordinateur (CV)

Ce document décrit le fonctionnement des groupes de boutons liés à la vision dans l'interface web du UGV Jetson.

## Architecture commune

Tous ces boutons partagent le même flux de communication :

```
Clic bouton HTML
  → cmdSend() / steadyCtrl() / lookAhead()  (control.js)
  → Message WebSocket (namespace /ctrl)
  → handle_socket_cmd()  (app.py)
  → Dictionnaire cmd_actions  (app.py)
  → Méthode cv_ctrl  (cv_ctrl.py : set_cv_mode, set_detection_reaction, …)
  → cv_process() dans un thread séparé (contrôlé par cv_event — un seul thread actif à la fois)
  → Retour d'état vers l'UI toutes les 5 s via socketio.emit('update')
```

Le traitement vidéo est géré par la méthode `opencv_threading()` qui utilise un `threading.Event` (`cv_event`) pour garantir qu'un seul thread de traitement CV est actif simultanément, même si la caméra produit des frames plus vite que le traitement.

Les modèles de détection sont stockés dans le sous-dossier `models/` du projet (`haarcascade_frontalface_default.xml`, `deploy.prototxt`, `mobilenet_iter_73000.caffemodel`).

---

## 1. PT Steady/Ahead

**Fichiers :** `templates/index.html`, `templates/control.js`, `base_ctrl.py`

Contrôle la stabilisation et la position du gimbal (pan-tilt).

| Bouton | Commande | Effet |
|--------|----------|-------|
| OFF | `cmd_gimbal_steady` (T=137), s=0 | Désactive la stabilisation |
| ON  | `cmd_gimbal_steady` (T=137), s=1 | Active la stabilisation — le gimbal compense les mouvements du châssis |
| Ahead | — | Remet le pan-tilt à sa position "droit devant" (`arm_default_z/r/e`) |

Le biais vertical `inputBias` est automatiquement calculé depuis la position courante du joystick (`stickSendY * -0.4`).

---

## 2. Simple Detection Type

**Fichiers :** `templates/index.html`, `app.py`, `cv_ctrl.py`

Choisit l'algorithme de détection OpenCV actif. Le mode est stocké dans `cvf.cv_mode`.

| Bouton | Code | Fonction appelée | Algorithme |
|--------|------|-----------------|------------|
| None   | 10301 | — | Désactive toute détection |
| Motion | 10302 | `cv_detect_movition()` | Différence de frames (`cv2.accumulateWeighted` + seuillage). Dessine des rectangles verts sur les zones mobiles > 2 000 px² (seuil codé en dur, non configurable via l'UI) |
| Faces  | 10303 | `cv_detect_faces()` | Haar Cascade (`cv2.CascadeClassifier`, fichier `models/haarcascade_frontalface_default.xml`). Suit le visage le plus grand avec le gimbal via `gimbal_track()` |

---

## 3. Simple Detection Reaction

**Fichiers :** `templates/index.html`, `app.py`, `cv_ctrl.py`

Définit l'action déclenchée lorsqu'une détection est positive. Le mode est stocké dans `cvf.detection_reaction_mode`.

| Bouton  | Code  | Effet |
|---------|-------|-------|
| None    | 10401 | Affichage seul, aucune action |
| Capture | 10402 | Capture automatique d'une photo à la détection |
| Record  | 10403 | Enregistrement vidéo pendant la détection |

L'état courant est retourné à l'UI via le champ `detect_react` du message `update`.

---

## 4. Advance CV Ctrl

**Fichiers :** `templates/index.html`, `app.py`, `cv_ctrl.py`

Contrôles transversaux pour la vision et le suivi.

| Bouton    | Code  | Fonction | Effet |
|-----------|-------|----------|-------|
| LOCK      | 10501 | `set_movtion_lock(True)` | Bloque le suivi gimbal et la conduite autonome : la détection continue mais la caméra ne bouge plus et le châssis reste immobile |
| UNLOCK    | 10502 | `set_movtion_lock(False)` | Réactive le suivi gimbal (remet `pan_angle` et `tilt_angle` à 0) et autorise les commandes de déplacement (AUTODRIVE, suivi couleur) |
| AUTODRIVE | 10307 | `cv_auto_drive()` | Mode conduite autonome (suivi de ligne) |

> **État initial :** `cv_movtion_lock = True` (LOCKED) au démarrage. Il faut appuyer sur UNLOCK pour activer le suivi gimbal ou la conduite autonome.

L'état du verrou est exposé à l'UI via le champ `cv_movtion_mode` du message `update`.

---

## 5. Advance CV Funcs

**Fichiers :** `templates/index.html`, `app.py`, `cv_ctrl.py`

Algorithmes de détection avancés, tous dispatchés par `cv_process()`.

| Bouton   | Code  | Fonction | Algorithme |
|----------|-------|----------|------------|
| OBJECTS  | 10304 | `cv_detect_objects()` | Détection d'objets via **MobileNet SSD (Caffe)** — modèles `models/deploy.prototxt` + `models/mobilenet_iter_73000.caffemodel`. Détecte 20 catégories : background, aeroplane, bicycle, bird, boat, bottle, bus, car, cat, chair, cow, diningtable, dog, horse, motorbike, person, pottedplant, sheep, sofa, train, tvmonitor. Seuil de confiance : 0.2 |
| COLOR    | 10305 | `cv_detect_color()` | Détection et suivi d'une couleur cible par plage HSV. Couleurs prédéfinies : **rouge**, **vert**, **bleu** (défaut selon `config.yaml : default_color: "blue"`). Plage configurable via commande. Trace un cercle sur la plus grande forme correspondante, suit sa position avec le gimbal (si UNLOCK). Affiche les valeurs HSV courantes de la zone centrale (`sampling_rad = 25 px`) |
| HAND GS  | 10306 | `mp_detect_hand()` | Reconnaissance de gestes de la main via MediaPipe (`max_num_hands=1`). Suit le bout de l'index (`INDEX_FINGER_TIP`) avec le gimbal (si UNLOCK). Geste reconnu — **LED Control** (auriculaire + majeur étendus) : l'écartement entre le pouce et l'index contrôle la luminosité des LEDs (0–128 PWM). Annote les 21 articulations sur l'overlay |

---

## 6. MediaPipe Funcs

**Fichiers :** `templates/index.html`, `app.py`, `cv_ctrl.py`

Détections spécifiques à la bibliothèque MediaPipe de Google, plus précises que les équivalents OpenCV classiques. Ces modes n'utilisent pas le suivi gimbal (pas d'appel à `gimbal_track`).

| Bouton  | Code  | Fonction | Algorithme |
|---------|-------|----------|------------|
| MP FACE | 10308 | `mediaPipe_faces()` | Détection de visage MediaPipe (`FaceDetection`, `model_selection=0`, `min_detection_confidence=0.5`). Plus robuste que le Haar cascade, dessine les landmarks et la bounding box sur l'overlay |
| MP POSE | 10309 | `mediaPipe_pose()` | Estimation de la pose corporelle complète via `mp_pose.Pose` (`model_complexity=1`, `smooth_landmarks=True`, `min_detection_confidence=0.5`, `min_tracking_confidence=0.5`). Dessine le squelette 33 points (`POSE_CONNECTIONS`) sur l'overlay |

---

## 7. Conduite autonome (AUTODRIVE) — détail

**Fichier :** `cv_ctrl.py` → `cv_auto_drive()`

Mode de suivi de ligne par filtre couleur HSV. Le robot ne se déplace que si UNLOCK est actif.

| Paramètre | Valeur par défaut | Rôle |
|-----------|-------------------|------|
| `line_lower` | `[25, 150, 70]` | Borne basse HSV (ligne jaune) |
| `line_upper` | `[42, 255, 255]` | Borne haute HSV (ligne jaune) |
| `sampling_line_1` | 0.6 | Position de la ligne de détection haute (60 % de la hauteur) |
| `sampling_line_2` | 0.9 | Position de la ligne de détection basse (90 % de la hauteur) |
| `line_track_speed` | 0.3 | Vitesse de croisière |
| `slope_impact` | 1.5 | Poids de la pente sur la direction |
| `base_impact` | 0.005 | Poids de l'offset latéral sur la direction |
| `slope_on_speed` | 0.1 | Réduction de vitesse en virage |

Comportement selon l'état des deux lignes de sampling :
- Les deux détectées → avance en suivant la pente calculée entre les deux centres
- Seulement basse → stop, correction latérale seule
- Seulement haute → avance lentement, tout droit
- Aucune → recule légèrement

---

## Référence des codes de commande (config.yaml)

| Constante | Code  | Catégorie |
|-----------|-------|-----------|
| cv_none   | 10301 | Détection |
| cv_moti   | 10302 | Détection |
| cv_face   | 10303 | Détection |
| cv_objs   | 10304 | Détection |
| cv_clor   | 10305 | Détection |
| mp_hand   | 10306 | Détection |
| cv_auto   | 10307 | Détection |
| mp_face   | 10308 | Détection |
| mp_pose   | 10309 | Détection |
| re_none   | 10401 | Réaction  |
| re_capt   | 10402 | Réaction  |
| re_reco   | 10403 | Réaction  |
| mc_lock   | 10501 | Contrôle  |
| mc_unlo   | 10502 | Contrôle  |
