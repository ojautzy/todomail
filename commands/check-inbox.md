---
description: Télécharger et trier les mails de la boîte de réception
allowed-tools: Read, Write, Bash(mkdir:*), Bash(mv:*), Bash(ls:*), Bash(python3:*), Glob, Grep, Task, mcp
---

## Vérification préalable

### 1. Répertoires

Vérifier que le répertoire de travail contient le répertoire suivant :
- `inbox/`

Si ce répertoire est manquant :

> **ARRÊT OBLIGATOIRE — Répertoire inadéquat**
> Afficher immédiatement à l'utilisateur la liste des répertoires manquants avec le message :
> "Le répertoire de travail n'est pas configuré correctement. Répertoires manquants : [liste]. Veuillez corriger la structure avant de relancer."
> **Ne pas poursuivre. Attendre.**

### 2. Serveur MCP

Lire `.todomail-config.json` à la racine du répertoire de travail. Appeler le tool MCP `status` et comparer `status.rag_name` avec `expected_rag_name` du fichier de config.

- Si le fichier `.todomail-config.json` n'existe pas : demander à l'utilisateur de lancer `/todomail:start` pour configurer le workspace, puis arrêter.
- Si `status.rag_name != expected_rag_name` :

> **ARRÊT OBLIGATOIRE — Mauvais serveur MCP**
> Afficher : "Le serveur MCP connecté (`<status.rag_name>`) ne correspond pas au serveur attendu pour ce workspace (`<expected_rag_name>`). Vérifier les connexions MCP dans Claude Desktop ou relancer `/todomail:start` pour reconfigurer."
> **Ne pas poursuivre. Attendre.**

Si tout existe et que le serveur correspond, poursuivre.

## Étape 1 — Téléchargement des mails

Appeler le tool MCP `check_inbox` pour télécharger les mails depuis le serveur IMAP.

Ce tool télécharge tous les mails depuis le serveur IMAP et place chacun dans un sous-répertoire de `inbox/` dont le nom est l'horodate du mail.
Dans ce sous-répertoire figure :
- le mail sous format EML
- le mail sous format JSON contenant les métadonnées et le corps du message
- chaque pièce jointe

**Important** : le tool s'exécute en tâche de fond. Attendre la fin de l'exécution avant de passer à l'étape suivante.

## Étape 2 — Tri des mails

Exécuter la skill sort-mails pour trier automatiquement les mails dans les catégories d'action :
- Lire d'abord le fichier SKILL.md de la skill sort-mails : @${CLAUDE_PLUGIN_ROOT}/skills/sort-mails/SKILL.md
- Suivre les étapes décrites dans la skill.

## Étape 3 — Compte-rendu

Présenter à l'utilisateur un compte-rendu complet du traitement effectué :

### Statistiques

- Nombre total de mails téléchargés depuis le serveur IMAP

### Erreurs éventuelles

Si des erreurs ont été rencontrées lors du téléchargement, les lister ici avec le détail du problème.

### Accès au dashboard

Indiquer à l'utilisateur qu'il peut maintenant ouvrir le dashboard interactif dans son navigateur pour valider les décisions sur chaque catégorie de mails. Fournir le lien direct vers le fichier `dashboard.html` situé à la racine du répertoire de travail :

```
file://<chemin_absolu_du_répertoire_de_travail>/dashboard.html
```

