# Analyse du binaire `sunny`

**Date d'analyse :** 2026-06-03  
**Fichier analysé :** `/home/admin/ugv_jetson/sunny`  
**Méthode :** Analyse statique uniquement (le binaire n'a pas été exécuté)

---

## Identification

| Propriété | Valeur |
|---|---|
| Type | ELF 64-bit LSB executable, ARM aarch64 |
| Langage | Go (statiquement lié, symboles de debug présents) |
| Taille | 12 Mo (12 118 385 octets) |
| SHA-256 | `c58bebcfcf959579234773289a97c19c5d8a9a21cf07230cd3c1f1c16ed9c612` |
| Date de création | 2026-05-30 15:07 |
| Permissions | `rw-r--r--` (non exécutable par défaut) |
| Présent dans git depuis | Premier commit (`3d363cb`) |

---

## Origine

Les chemins de compilation embarqués dans les symboles de debug révèlent l'origine du code source :

```
/ngrok-online/util/sunnyapi.go
/ngrok-online/client/main.go
```

Le binaire se nomme lui-même **"Sunny-Ngrok"** dans ses chaînes de caractères internes :

```
Sunny-Ngrok www.ngrok.cc
sunny-ngrok is updating
sunny-ngrok has updated: restart sunny-ngrok for the new version
```

Il s'agit d'un **fork/clone du client open-source ngrok**, recompilé pour ARM aarch64 et reconfiguré pour se connecter à l'infrastructure **ngrok.cc** (service tiers chinois) plutôt qu'à l'infrastructure officielle ngrok.io.

**Waveshare** inclut ce binaire dans ses kits robotiques Jetson (UGV, etc.) pour permettre un accès distant au robot sans configuration réseau complexe.

---

## Fonctionnement

`sunny` crée un **tunnel TCP/HTTP sortant** entre le Jetson et les serveurs de ngrok.cc. Ce tunnel expose un port local sur une URL publique, permettant l'accès au robot depuis internet.

### Serveurs contactés

| Rôle | Adresse |
|---|---|
| Serveur de tunnel (relay) | `server.ngrok.cc:4443` |
| API d'authentification | `https://api.ngrok.cc/user` |
| Site de mise à jour | `https://www.ngrok.cc` |
| Interface web locale | `127.0.0.1:4040` |

### Protocole réseau

Le binaire implémente le protocole ngrok complet avec les types de messages suivants (identifiés dans les symboles Go) :

- `AuthResp` — réponse d'authentification
- `RegProxy` — enregistrement du proxy
- `ReqProxy` — demande de proxy
- `ReqTunnel` — demande d'ouverture de tunnel
- `NewTunnel` — confirmation de tunnel établi

### Interface en ligne de commande

```
sunny clientid xxxxx               # démarrer le tunnel
sunny -log=stdout clientid xxxxx   # démarrer avec logs verbeux
sunny version                      # afficher la version
sunny help                         # aide
```

L'authentification se fait via un `clientid` unique, enregistré sur le service ngrok.cc.

---

## Dépendances identifiées

Bibliothèques Go embarquées (statiquement liées) :

- `github.com/gorilla/websocket` — transport WebSocket
- `github.com/inconshreveable/ngrok` — base du client ngrok
- `github.com/alecthomas/log4go` — journalisation
- `github.com/rcrowley/go-metrics` — métriques
- `github.com/nsf/termbox-go` — interface terminal
- `gopkg.in/yaml.v1` — parsing de configuration YAML

---

## Implications de sécurité

### Risques

1. **Bypass de pare-feu / NAT** : le tunnel est initié en sortant (port 4443 vers ngrok.cc), ce qui contourne les règles réseau entrantes. Une fois actif, n'importe qui avec l'URL du tunnel peut atteindre le service exposé sur le Jetson.

2. **Infrastructure tierce** : tout le trafic transite par les serveurs de `ngrok.cc`, une entité commerciale chinoise. Les données échangées (flux caméra, commandes robot, API) passent par cette infrastructure sans contrôle.

3. **Mise à jour automatique non contrôlée** : le binaire vérifie et télécharge des mises à jour depuis `www.ngrok.cc`. Un serveur compromis pourrait pousser du code malveillant.

4. **User-Agent identifiant** : le binaire utilise `Mozilla/5.0 (compatible; ngrok)` — il se présente explicitement comme un client ngrok.

### Utilisation légitime

Dans le contexte Waveshare/UGV, ce binaire est **fourni par le fabricant** pour :
- Permettre un accès distant au robot depuis internet sans configuration réseau
- Faciliter les démonstrations et le support client à distance
- Exposer l'interface web de contrôle du robot

### Recommandations

- **Ne pas lancer `sunny` sur un réseau de production** ou sur un robot contenant des données sensibles.
- Si l'accès distant est nécessaire, préférer une solution VPN (WireGuard, Tailscale) qui maintient le contrôle de l'infrastructure.
- Si `sunny` n'est pas utilisé, le retirer du projet pour éviter toute exécution accidentelle.
- Le binaire n'est pas dans `.gitignore` — vérifier qu'il ne sera pas commité et distribué involontairement.

---

## Conclusion

`sunny` est un outil d'accès distant **légitime fourni par Waveshare** avec ses kits robotiques Jetson, basé sur le protocole ngrok et opéré via le service chinois `ngrok.cc`. Il n'est pas malveillant par nature, mais il représente un **risque de sécurité significatif** sur un système embarqué exposé : tunnel sortant permanent, infrastructure tierce non maîtrisée, et mécanisme de mise à jour automatique. Son utilisation doit être explicitement choisie et encadrée.
