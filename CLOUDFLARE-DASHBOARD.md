# Mise en service du dashboard sur Internet (Cloudflare Tunnel + Access)

> Procédure **unique** à suivre une fois pour exposer le dashboard TodoMail sur Internet,
> de façon sécurisée et mono-utilisateur. Une fois ces étapes faites, il suffit de lancer
> `/todomail:dashboard` dans Claude Code pour démarrer le serveur, et d'ouvrir l'URL publique
> dans n'importe quel navigateur (Safari, Firefox, Chrome, mobile).

## Architecture en bref

```
Navigateur (n'importe où)
   │  https://todomail.jautzy.com
   ▼
Cloudflare Edge  ──►  Cloudflare Access (OTP email : seul ton email passe)
   │  tunnel chiffré
   ▼
cloudflared (Mac)  ──►  http://localhost:8770  (serveur Python, bind 127.0.0.1)
   │
   ▼
lib/serve_dashboard.py  ──►  workspace (todo/, .todomail/, memory/, …)
```

Le serveur **valide le JWT** injecté par Cloudflare Access sur **chaque** requête `/api/*`.
Un accès direct à `http://127.0.0.1:8770` (sans passer par Cloudflare) renvoie `403` :
**il n'existe qu'un seul point d'entrée authentifié**, l'URL publique.

## A. Prérequis

- `cloudflared` installé et un tunnel déjà opérationnel (ici `~/.cloudflared/config.yml`).
- Le domaine (`jautzy.com`) géré par Cloudflare.
- Accès au dashboard **Cloudflare Zero Trust** : <https://one.dash.cloudflare.com>.
- La dépendance Python du serveur, installée **dans le même interpréteur `python3`** que celui utilisé par Claude Code (utiliser `python3 -m pip` ; `--break-system-packages` est requis sur les Python Homebrew/macOS « externally-managed » (PEP 668), sans effet ailleurs) :
  ```bash
  python3 -m pip install --break-system-packages "PyJWT[crypto]"
  ```
  Vérification : `python3 -c "import jwt; print(jwt.__version__)"`. Le plus fiable est de lancer cette installation **depuis Claude Code** (`/todomail:dashboard` le propose), pour garantir le même interpréteur que le serveur.

## B. Router le hostname vers le tunnel

1. **Trouver l'UUID du tunnel** (champ `tunnel:` en haut du fichier) :
   ```bash
   cat ~/.cloudflared/config.yml
   ```

2. **Créer la route DNS** (CNAME proxifié vers le tunnel) :
   ```bash
   cloudflared tunnel route dns <UUID> todomail.jautzy.com
   ```

3. **Ajouter la règle d'ingress** : éditer `~/.cloudflared/config.yml` et insérer le bloc
   suivant **avant** la règle catch-all `- service: http_status:404` (l'ordre compte,
   premier match gagnant) :
   ```yaml
     - hostname: todomail.jautzy.com
       service: http://localhost:8770
   ```

4. **Redémarrer le tunnel** pour prendre en compte la nouvelle route :
   - s'il tourne en premier plan : arrêter (`Ctrl-C`) puis `cloudflared tunnel run` ;
   - s'il est géré par un LaunchAgent : `launchctl kickstart -k gui/$(id -u)/<label-cloudflared>`.

## C. Créer l'application Cloudflare Access

Dans **Zero Trust → Access → Applications → Add an application → Self-hosted** :

1. **Application domain** : `todomail.jautzy.com`.
2. **Session Duration** : `1 week` (ou `1 month`) — limite la fréquence des codes OTP
   lorsqu'on utilise le dashboard depuis le Mac.
3. **Identity providers** : activer **One-time PIN** (code envoyé par email — aucun IdP
   tiers nécessaire). Si absent : *Settings → Authentication → Login methods → Add → One-time PIN*.
4. **Policy** : une seule règle —
   - *Action* : **Allow**
   - *Include* : **Emails** = `olivier.jautzy@gmail.com`

   (Seule cette adresse pourra s'authentifier ; tout le reste est refusé au edge.)
5. Récupérer l'**Application Audience (AUD) Tag** dans l'onglet *Overview* de l'application :
   c'est la valeur `access_aud` à renseigner dans le plugin.
6. Le **team domain** est le sous-domaine de ton organisation Zero Trust
   (*Settings → Custom Pages*, ou l'URL `https://<team>.cloudflareaccess.com`).
   Exemple : `jautzy` → émetteur `https://jautzy.cloudflareaccess.com`. C'est la valeur
   `team_domain`.

## D. Renseigner le plugin et lancer

Dans Claude Code, lancer :

```
/todomail:dashboard
```

La commande demande (si absents) `port`, `hostname`, `team_domain`, `access_aud`,
les écrit dans `.todomail-config.json` (bloc `dashboard`, `chmod 600`), vérifie PyJWT,
puis démarre le serveur en arrière-plan détaché et affiche l'URL publique.

## E. Tester

1. **Accès autorisé** : ouvrir `https://todomail.jautzy.com` dans Safari (ou sur mobile).
   → challenge Cloudflare Access → saisir le code OTP reçu par email → le dashboard s'affiche.
2. **Bypass direct bloqué** : sur le Mac,
   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8770/api/poll
   ```
   doit afficher `403` (pas de header Access → refus).
3. **Email non autorisé** : tenter la connexion avec une autre adresse → refusé au edge,
   la requête n'atteint jamais le Mac.

## Sécurité — modèle

| Couche | Rôle |
|--------|------|
| Bind `127.0.0.1` | le port n'est joignable que par cloudflared, jamais sur le LAN/WAN |
| Cloudflare Access (OTP) | authentifie l'identité au edge, avant que le trafic n'atteigne le Mac |
| Validation JWT serveur | vérifie signature RS256 + audience + émetteur sur chaque requête `/api/*` ; bloque tout header forgé et tout bypass du tunnel |
| Garde anti-traversée | chaque chemin est résolu en realpath et confiné au workspace (pas d'évasion `../`/symlink) |
| Verrou (`409`) | refuse les écritures pendant qu'un cycle Claude tient le verrou |
| TLS | terminé au edge Cloudflare (certificat managé) ; aucune gestion de certificat sur le Mac |

Mono-utilisateur : aucune gestion de comptes. Le seul « compte » est l'email autorisé dans la
policy Access. Le fichier `.todomail-config.json` (qui contient aussi le mot de passe IMAP) reste
en `chmod 600` et hors Git.

## Toujours actif (optionnel)

Pour que le serveur démarre automatiquement à l'ouverture de session et redémarre après un crash,
installer un LaunchAgent `~/Library/LaunchAgents/com.todomail.dashboard.plist` :

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.todomail.dashboard</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>-m</string>
    <string>lib.serve_dashboard</string>
    <string>--port</string>
    <string>8770</string>
  </array>
  <key>WorkingDirectory</key><string>/chemin/vers/le/workspace</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key><string>/chemin/vers/le/plugin/todomail</string>
    <key>CLAUDE_PROJECT_DIR</key><string>/chemin/vers/le/workspace</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/chemin/vers/le/workspace/.todomail/serve_dashboard.log</string>
  <key>StandardErrorPath</key><string>/chemin/vers/le/workspace/.todomail/serve_dashboard.log</string>
</dict>
</plist>
```

Puis : `launchctl load ~/Library/LaunchAgents/com.todomail.dashboard.plist`. Faire de même pour
`cloudflared` si l'on veut un accès Internet réellement permanent.
