---
description: Lance le serveur du dashboard (Safari, Firefox, mobile, accessible depuis n'importe où via Cloudflare Access)
allowed-tools: Read, Bash(python3:*), Bash(nohup:*), Bash(lsof:*), Bash(curl:*), Bash(grep:*), Bash(cat:*), Bash(pip3:*), Bash(pip:*), AskUserQuestion
---

# Commande Dashboard

> Sert `dashboard.html` via un serveur HTTP local (`lib/serve_dashboard.py`) exposé sur Internet par le **tunnel Cloudflare** déjà en place et protégé par **Cloudflare Access**. Depuis la v2.2.0, le dashboard n'utilise plus la File System Access API : il fonctionne dans **tout navigateur** (Safari, Firefox, mobile) et s'ouvre via l'URL publique, au Mac comme à distance.

> Mise en service initiale du tunnel + Access : voir [CLOUDFLARE-DASHBOARD.md](../CLOUDFLARE-DASHBOARD.md). Cette commande suppose que cette configuration unique a déjà été faite (ou l'indique sinon).

## Préambule — import des helpers lib/

Tout bloc Python qui importe `lib.*` doit résoudre `CLAUDE_PLUGIN_ROOT` côté Python (cf. CLAUDE.md) :

```bash
python3 - <<'PY'
import os, sys
plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if not plugin_root:
    raise RuntimeError("CLAUDE_PLUGIN_ROOT non defini")
sys.path.insert(0, plugin_root)
from lib.state import workspace_dir
from lib.config import get_dashboard_config, save_dashboard_config
# ...
PY
```

## Instructions

### Étape 0. Configuration du dashboard

Lire le bloc `dashboard` de `.todomail-config.json` :

```bash
python3 - <<'PY'
import os, sys, json
plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
sys.path.insert(0, plugin_root)
from lib.state import workspace_dir
from lib.config import get_dashboard_config

cfg = get_dashboard_config(workspace_dir()) or {}
required = {"port", "hostname", "team_domain", "access_aud"}
missing = sorted(required - {k for k, v in cfg.items() if v})
print(json.dumps({"config": cfg, "missing": missing}))
PY
```

- **Si `missing` est vide :** la configuration est complète, passer à l'Étape 1.
- **Si `missing` n'est pas vide :** demander les valeurs manquantes via `AskUserQuestion`, avec ces valeurs par défaut :
  - **port** — port local d'écoute (défaut : `8770`)
  - **hostname** — sous-domaine public (ex. `todomail.jautzy.com`)
  - **team_domain** — sous-domaine de l'équipe Cloudflare Zero Trust (ex. `jautzy` pour `jautzy.cloudflareaccess.com`)
  - **access_aud** — l'**Application Audience (AUD) Tag** de l'application Access (onglet *Overview* de l'app dans le dashboard Zero Trust)

  Puis écrire la config :

```bash
python3 - <<'PY'
import os, sys
plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
sys.path.insert(0, plugin_root)
from lib.state import workspace_dir
from lib.config import save_dashboard_config
# Remplacer par les valeurs collectees aupres de l'utilisateur :
save_dashboard_config(workspace_dir(), port=8770, hostname="todomail.jautzy.com",
                      team_domain="jautzy", access_aud="<AUD_TAG>")
print("OK")
PY
```

  Si l'utilisateur n'a pas encore créé l'application Cloudflare Access (donc pas de `team_domain`/`access_aud`), le lui indiquer et le renvoyer vers `CLOUDFLARE-DASHBOARD.md` (section C). Ne pas lancer le serveur en mode exposé sans ces valeurs (il refuserait de démarrer).

### Étape 1. Vérifier la dépendance PyJWT

Le serveur valide cryptographiquement le JWT Cloudflare Access (RS256), ce qui nécessite `PyJWT[crypto]` :

```bash
python3 -c "import jwt; print('PyJWT OK')" 2>/dev/null || echo "MANQUANT"
```

Si `MANQUANT`, installer la dépendance **dans le même interpréteur `python3`** que celui qui lancera le serveur (sinon l'import échouera au démarrage). Utiliser `python3 -m pip` (et non `pip3` nu) garantit le bon interpréteur ; le flag `--break-system-packages` est requis sur les Python « externally-managed » (Homebrew/macOS, PEP 668) et sans effet ailleurs :

```bash
python3 -m pip install --break-system-packages "PyJWT[crypto]"
```

Vérifier : `python3 -c "import jwt; print(jwt.__version__)"`.

### Étape 2. Le serveur tourne-t-il déjà ? (idempotence)

```bash
PORT=8770   # remplacer par le port configuré
lsof -nP -iTCP:$PORT -sTCP:LISTEN 2>/dev/null && echo "DEJA ACTIF" || echo "INACTIF"
```

- **Si `DEJA ACTIF` :** vérifier la santé (`curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/api/poll` → attendu `403` sans JWT, ce qui prouve que le serveur répond ET que l'auth est active). Sauter le lancement, aller à l'Étape 5.
- **Si `INACTIF` :** passer à l'Étape 3.

### Étape 3. Lancer le serveur détaché

Lancer le serveur en arrière-plan, détaché de la session Claude (survit à la fermeture de Claude Code) :

```bash
PORT=8770   # port configuré
cd "$CLAUDE_PROJECT_DIR"
PYTHONPATH="$CLAUDE_PLUGIN_ROOT" CLAUDE_PROJECT_DIR="$CLAUDE_PROJECT_DIR" \
  nohup python3 -m lib.serve_dashboard --port $PORT \
  >> "$CLAUDE_PROJECT_DIR/.todomail/serve_dashboard.log" 2>&1 &
disown
sleep 1
```

Vérifier le démarrage : `tail -n 5 "$CLAUDE_PROJECT_DIR/.todomail/serve_dashboard.log"` doit afficher la ligne `[todomail] dashboard servi sur http://127.0.0.1:$PORT | auth: Cloudflare Access (JWT)`. Si le log montre une erreur (config Access incomplète ou PyJWT manquant), corriger (Étapes 0/1) et relancer.

### Étape 4. Route Cloudflare (guidée — non automatique)

Le serveur n'écoute qu'en loopback (`127.0.0.1`). Pour l'exposer, le tunnel Cloudflare existant doit avoir une route vers ce port. **Ne pas éditer ni redémarrer le tunnel automatiquement** (il sert d'autres services en production) : afficher à l'utilisateur ce qu'il doit faire si la route manque.

Lire la config du tunnel et son UUID :

```bash
cat ~/.cloudflared/config.yml 2>/dev/null
```

Si aucune ligne `hostname: <hostname>` ne pointe vers `http://localhost:<port>`, afficher à l'utilisateur le patch à appliquer **avant** la ligne `- service: http_status:404` :

```yaml
  - hostname: todomail.jautzy.com
    service: http://localhost:8770
```

Et, si la route DNS n'existe pas encore, la commande à exécuter (remplacer `<UUID>` par le `tunnel:` lu dans le config) :

```
cloudflared tunnel route dns <UUID> todomail.jautzy.com
```

Puis redémarrer le tunnel selon son mode de lancement (`cloudflared tunnel run`, ou `launchctl kickstart` si un LaunchAgent le gère). Renvoyer vers `CLOUDFLARE-DASHBOARD.md` (section B) pour le détail.

### Étape 5. Vérifications de sécurité

- **Bind loopback uniquement :** `lsof -nP -iTCP:$PORT -sTCP:LISTEN` doit montrer `127.0.0.1:$PORT`, jamais `*:$PORT`.
- **Bypass Cloudflare bloqué :** `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/api/poll` doit renvoyer **`403`** (pas de header Access → refus). C'est la preuve qu'un accès direct au port, sans passer par Cloudflare, est rejeté.
- **Edge protégé :** un `curl` de l'URL publique sans session Access doit être redirigé vers le login Access (challenge OTP), jamais servir le dashboard. Si ce n'est pas le cas, l'application Access n'est pas correctement configurée (voir `CLOUDFLARE-DASHBOARD.md` section C).

### Étape 6. Rapport

Afficher :

```
Dashboard servi.
- URL publique : https://todomail.jautzy.com   (à utiliser au Mac comme à distance — authentification Cloudflare Access par code email)
- Local        : http://127.0.0.1:8770          (renvoie 403 en direct : c'est normal, l'accès passe par l'URL publique)
- Auth         : Cloudflare Access (OTP email)
- Log          : .todomail/serve_dashboard.log
- Arrêt        : kill <PID>   (PID visible via : lsof -nP -iTCP:8770 -sTCP:LISTEN)
```

## Notes

- **Un seul point d'entrée.** Le serveur exige le JWT Cloudflare Access sur toutes les requêtes `/api/*`. Un accès direct à `http://127.0.0.1:8770` renvoie `403` : il faut passer par `https://todomail.jautzy.com`, au Mac comme à distance. Le compromis assumé : Internet et le tunnel doivent être actifs même pour un usage local (régler une durée de session Access généreuse, 1 semaine / 1 mois, évite de refaire l'OTP trop souvent).
- **Protocole inchangé.** Le serveur lit/écrit exactement les mêmes fichiers que l'ancien dashboard (`todo/<cat>/instructions.json`, `.todomail/state.json`, fichiers-marqueurs). Aucune modification de `/process-todo`, `/check-inbox` ou des hooks. Pendant qu'un cycle Claude tient le verrou, les écritures du dashboard renvoient `409` et l'UI affiche la bannière « Claude travaille… ».
- **Toujours actif (optionnel).** Pour un serveur permanent (démarrage à l'ouverture de session, redémarrage après crash), installer un LaunchAgent `~/Library/LaunchAgents/com.todomail.dashboard.plist` qui lance `python3 -m lib.serve_dashboard --port 8770` (avec `PYTHONPATH`/`CLAUDE_PROJECT_DIR`). Voir `CLOUDFLARE-DASHBOARD.md`.
