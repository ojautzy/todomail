---
description: Telecharger et trier les mails de la boite de reception
allowed-tools: Read, Write, Bash(mkdir:*), Bash(mv:*), Bash(ls:*), Bash(python3:*), Bash(pip:*), Glob, Grep, Task, mcp
argument-hint: "[--strict] [--retry]"
---

## Parsing des arguments

Les arguments passes a la commande sont disponibles dans la variable `$ARGUMENTS`.
Le parsing est effectue en lisant semantiquement cette variable (pas de parseur
externe).

Flags supportes :
- `--strict` : active le mode strict (`ErrorHandler(mode="strict")`) — arret
  immediat a la premiere erreur avec demande utilisateur.
- `--retry` : **saute le telechargement IMAP**, lit `lib.state.get_pending_errors()`
  et retraite uniquement les mails inscrits dans `state.errors[]`. Le mode reste
  `lenient` quelle que soit la combinaison de flags.

Regle de priorite :
1. Si `$ARGUMENTS` contient `--retry` → mode retry (Etape 1 sautee, analyse ciblee
   sur les mails en echec, chaque retry reussi retire l'entree via
   `lib.state.clear_error(mail_id)`).
2. Sinon si `$ARGUMENTS` contient `--strict` → `ErrorHandler(mode="strict")`,
   cycle complet.
3. Sinon → mode par defaut (`lenient`, cycle complet).

## Verification prealable

### 1. Repertoires

Verifier que le repertoire de travail contient `inbox/`. Absence → **ARRET
OBLIGATOIRE — Repertoire inadequat** (message clair, attendre).

### 2. Serveur MCP (desambiguation alpha.2 — **ne jamais supprimer**)

Lire `.todomail-config.json` a la racine du repertoire de travail. Appeler le
tool MCP `status` et comparer `status.rag_name` avec `expected_rag_name` du
fichier de config.

- Si `.todomail-config.json` n'existe pas : demander a l'utilisateur de lancer
  `/todomail:start` pour configurer le workspace, puis arreter.
- Si `status.rag_name != expected_rag_name` :

> **ARRET OBLIGATOIRE — Mauvais serveur MCP**
> Afficher : « Le serveur MCP connecte (`<status.rag_name>`) ne correspond pas
> au serveur attendu pour ce workspace (`<expected_rag_name>`). Verifier les
> connexions MCP dans Claude Desktop ou relancer `/todomail:start` pour
> reconfigurer. »

Cette verification est **obligatoire** et s'execute **avant** toute autre etape.
Elle couvre tous les composants en aval (sort-mails, analyse, etc.), qui n'ont
donc pas a la refaire.

## Etape 1 — Telechargement des mails (sautee si `--retry`)

Appeler le tool MCP `check_inbox` pour telecharger les mails depuis le serveur
IMAP. Chaque mail est place dans un sous-repertoire de `inbox/` dont le nom est
l'horodate du mail. Le sous-repertoire contient :
- le mail au format EML
- un `message.json` (metadonnees + corps)
- chaque piece jointe

**Important** : le tool s'execute en tache de fond. Attendre la fin avant de
passer a l'etape suivante.

## Etape 2 — Tri des mails (skill sort-mails)

Lire `@${CLAUDE_PLUGIN_ROOT}/skills/sort-mails/SKILL.md` et suivre ses etapes.

**Transmission des flags** : transmettre le mode d'erreur (`lenient` / `strict`)
au skill via l'`ErrorHandler` deja instancie dans l'environnement de session.

**Mode `--retry`** : au lieu de lister `inbox/`, lister les `mail_id` retournes
par `lib.state.get_pending_errors()`. Pour chaque `mail_id`, localiser son
repertoire source (dans `inbox/` ou deja dans `todo/<categorie>/` selon ou il
est reste) et relancer uniquement l'Etape 2 de sort-mails sur ce mail. A chaque
retry reussi : `lib.state.clear_error(mail_id)`. Les `pending_emails.json` sont
re-fusionnes en consequence.

## Etape 3 — Compte-rendu

### Statistiques

- Nombre total de mails telecharges (cycle complet) **ou** nombre de mails
  retraites (`--retry`).
- Stats pre-filtrage Haiku et cache RAG (heritees du skill sort-mails).
- Repartition par categorie.

### Erreurs eventuelles

Lister les erreurs persistantes de `state.errors[]` avec, pour chacune :
`mail_id`, `phase`, `error_type`, `retry_count`, `permanent_failure`.

Si au moins une erreur est non resolue :

> Relancer `/todomail:check-inbox --retry` pour retraiter uniquement les mails
> en echec.

### Acces au dashboard

Indiquer a l'utilisateur qu'il peut ouvrir le dashboard interactif dans son
navigateur :

```
file://<chemin_absolu_du_repertoire_de_travail>/dashboard.html
```
