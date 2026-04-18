#!/bin/sh
# Wrapper d'execution des hooks TodoMail.
#
# Raison d'etre : sur macOS, Claude Desktop (app GUI) herite d'un PATH
# minimal qui ne contient pas /opt/homebrew/bin ni /usr/local/bin.
# Sans ce wrapper, la commande `python3` est introuvable quand les
# hooks sont declenches depuis Claude Desktop (contrairement a Claude
# Code en CLI, ou le PATH utilisateur est herite normalement).
#
# Ce wrapper ajoute les chemins usuels en tete de PATH, puis delegue a
# python3 avec le chemin du hook passe en argument.
#
# Usage : hooks/_run.sh <chemin/vers/hook.py>

PATH="/opt/homebrew/bin:/usr/local/bin:/opt/local/bin:${PATH:-/usr/bin:/bin}"
export PATH

# Si python3 n'est toujours pas trouvable, on sort en 0 pour respecter
# la graceful degradation (on ne veut jamais planter une session).
if ! command -v python3 >/dev/null 2>&1; then
  exit 0
fi

exec python3 "$@"
