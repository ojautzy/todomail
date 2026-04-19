---
name: check-agenda
description: >
  Audite la cohérence et la faisabilité de l'agenda sur une période.
  This skill should be used when the user asks "audite mon agenda",
  "est-ce que mon agenda est cohérent", "regarde ma semaine", "vérifie
  mon planning", "y a-t-il des problèmes dans mon agenda", "passe en
  revue ma semaine", or any natural request to check schedule
  consistency and detect conflicts.
allowed-tools: Read, Write, Bash, Glob, Grep, mcp
version: 2.0.0
---

# check-agenda (wrapper) — Déclenchement en langage naturel

Ce skill est un **wrapper léger** autour de la commande slash
`/todomail:check-agenda`. Il est auto-déclenché lorsque l'utilisateur
formule en langage naturel une demande d'audit agenda, sans avoir à
taper la commande explicitement.

La logique métier (chargement des événements, détection des conflits,
enrichissement contextuel, propositions de créneaux alternatifs,
vérification MCP, verrou dashboard) est **entièrement définie dans
`commands/check-agenda.md`**. Ce skill ne la duplique pas : il se
contente de router la demande vers la commande.

## Déclenchement

Ce skill est mobilisé quand l'utilisateur formule une demande naturelle
comme :

- « Audite mon agenda »
- « Est-ce que mon agenda est cohérent ? »
- « Regarde ma semaine »
- « Vérifie mon planning de la semaine prochaine »
- « Y a-t-il des problèmes dans mon agenda ? »
- « Passe en revue mon mois de mars »

L'invocation explicite `/todomail:check-agenda [période]` reste
disponible et inchangée ; les deux entrées mènent au même comportement.

## Comportement

### 1. Résolution de la période

Interpréter la demande de l'utilisateur pour en extraire l'argument qui
sera passé à `/todomail:check-agenda` :

- **« ma semaine », « cette semaine »** → pas d'argument (défaut :
  semaine courante lundi-vendredi).
- **« la semaine prochaine »** → calculer la plage lundi-vendredi
  suivante et la passer comme `YYYY-MM-DD YYYY-MM-DD`.
- **« mon mois », « ce mois-ci »** → `mois`.
- **Mois ou plage explicite** (« du 1er au 15 mars », « mars 2026 ») →
  convertir en deux dates ISO.

Si la demande reste ambiguë (plusieurs semaines plausibles, plusieurs
mois candidats), poser une question de désambiguation via
`AskUserQuestion` avant de lancer la commande.

### 2. Invocation de la commande

Lire `@${CLAUDE_PLUGIN_ROOT}/commands/check-agenda.md` et suivre ses
étapes avec l'argument résolu à l'étape 1 :

- Vérification préalable (mémoire + serveur MCP alpha.2)
- Warm-up avec `acquire_lock("check-agenda")`
- Chargement des événements (skill `agenda`)
- Détection des problèmes (skill `detection-conflits`)
- Analyse contextuelle (temps de déplacement, nuitées, créneaux
  alternatifs via `disponibilites`)
- Génération du rapport structuré
- Mise à jour mémoire
- Finalisation avec `release_lock()`

### 3. Pas de duplication

**Ne jamais réécrire la logique de `/check-agenda` dans ce skill.**
Toute modification de la procédure d'audit (ajout d'un contrôle,
changement de format de rapport, nouveau niveau de sévérité) doit être
faite dans `commands/check-agenda.md` uniquement. Ce wrapper reste un
alias en langage naturel.

## Différence entre commande et wrapper

| Aspect | `/todomail:check-agenda` | `check-agenda` (ce skill) |
|--------|--------------------------|--------------------------|
| Déclenchement | Tapé explicitement par l'utilisateur | Phrase naturelle détectée par Claude |
| Argument | Passé explicitement (mois ou plage ISO) | Extrait du langage naturel |
| Logique | Complète (source de vérité) | Délégation à la commande |
| Verrou dashboard | Oui (via la commande) | Oui (hérité de la commande) |

## Notes

- L'utilisateur conserve le contrôle : s'il veut préciser une plage
  exacte, il peut toujours taper la commande directement.
- La désambiguation avant invocation est critique : une mauvaise période
  déclencherait un cycle complet inutile et un verrou à libérer.
- Les critères d'acceptation d'un audit réussi (rapport en conversation,
  verrou visible dans le dashboard pendant le cycle, libération finale)
  sont ceux de la commande elle-même.
