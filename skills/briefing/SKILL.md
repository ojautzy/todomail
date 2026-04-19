---
name: briefing
description: >
  Génère des dossiers de préparation pour les réunions à venir.
  This skill should be used when the user asks "prépare-moi la réunion",
  "briefing pour mercredi", "j'ai quoi à préparer demain", "prépare le
  COPIL", "fais-moi un briefing", "prépare la réunion de demain", or
  any natural request to prepare meeting materials from the user's
  calendar.
allowed-tools: Read, Write, Bash, Glob, Grep, Task, mcp
version: 2.0.0
---

# briefing (wrapper) — Déclenchement en langage naturel

Ce skill est un **wrapper léger** autour de la commande slash
`/todomail:briefing`. Il est auto-déclenché lorsque l'utilisateur
formule en langage naturel une demande de préparation de réunion,
sans avoir à taper la commande explicitement.

La logique métier (recherche documentaire, génération des fichiers
`to-brief/<slug>.md`, mise à jour mémoire, verrou dashboard, vérification
MCP) est **entièrement définie dans `commands/briefing.md`**. Ce skill
ne la duplique pas : il se contente de router la demande vers la
commande.

## Déclenchement

Ce skill est mobilisé quand l'utilisateur formule une demande naturelle
comme :

- « Prépare-moi la réunion COPIL de mercredi »
- « Briefing pour demain »
- « J'ai quoi à préparer pour jeudi ? »
- « Fais-moi un briefing sur le point bilatéral de 14h »
- « Prépare la réunion de sécurité de la semaine prochaine »

L'invocation explicite `/todomail:briefing [argument]` reste disponible
et inchangée ; les deux entrées mènent au même comportement.

## Comportement

### 1. Résolution de l'argument

Interpréter la demande de l'utilisateur pour en extraire l'argument qui
sera passé à `/todomail:briefing` :

- **Date implicite « demain », « mercredi », « la semaine prochaine »** →
  résoudre en date ISO (YYYY-MM-DD) à partir de la date courante.
- **Date absolue dans la demande** (« 2026-03-03 », « le 3 mars ») →
  convertir en ISO.
- **Nom de réunion cité entre guillemets ou reconnaissable** (« COPIL »,
  « bilatéral SG », « comité sécurité ») → utiliser le titre entre
  guillemets.
- **Pas d'info temporelle** → date du jour (comportement par défaut de
  la commande sans argument).

Si la demande reste ambiguë (plusieurs dates plausibles, plusieurs
réunions candidates), poser une question de désambiguation via
`AskUserQuestion` avant de lancer la commande.

### 2. Invocation de la commande

Lire `@${CLAUDE_PLUGIN_ROOT}/commands/briefing.md` et suivre ses étapes
avec l'argument résolu à l'étape 1 :

- Vérification préalable (mémoire + serveur MCP alpha.2)
- Warm-up avec `acquire_lock("briefing")`
- Identification des réunions (skill `agenda`)
- Génération en flux (contexte 1M) des fichiers `to-brief/`
- Mise à jour mémoire
- Finalisation avec `release_lock()`

### 3. Pas de duplication

**Ne jamais réécrire la logique de `/briefing` dans ce skill.** Toute
modification de la procédure de briefing (ajout d'une étape, changement
de format de fichier, nouveau filtre) doit être faite dans
`commands/briefing.md` uniquement. Ce wrapper reste un alias en langage
naturel.

## Différence entre commande et wrapper

| Aspect | `/todomail:briefing` | `briefing` (ce skill) |
|--------|----------------------|----------------------|
| Déclenchement | Tapé explicitement par l'utilisateur | Phrase naturelle détectée par Claude |
| Argument | Passé explicitement (date ou titre) | Extrait du langage naturel |
| Logique | Complète (source de vérité) | Délégation à la commande |
| Verrou dashboard | Oui (via la commande) | Oui (hérité de la commande) |

## Notes

- L'utilisateur conserve le contrôle : s'il veut préciser le comportement
  (date exacte, option `--parallel`), il peut toujours taper la commande
  directement.
- La désambiguation avant invocation est critique : une mauvaise date
  déclencherait un cycle complet inutile et un verrou à libérer.
- Les critères d'acceptation d'un briefing réussi (fichiers dans
  `to-brief/`, verrou visible dans le dashboard pendant le cycle,
  libération finale) sont ceux de la commande elle-même.
