---
name: sort-mails
description: >
  This skill should be used when the user asks to "sort mails",
  "trier les mails", "trier mes messages" or needs
  to sort incoming emails into action categories.
allowed-tools: Read, Write, Bash(mkdir:*), Bash(mv:*), Bash(ls:*), Bash(python3:*), Glob, Grep, Task, mcp
version: 1.0.0
---

## Vérification préalable

Vérifie que le répertoire de travail contient les répertoires suivants :
- `inbox/`
- `todo/`
- `to-clean-by-user/`
- `todo/trash/`
- `todo/do-read-quick/`
- `todo/do-read-long/`
- `todo/do-decide/`
- `todo/do-consult-and-decide/`
- `todo/do-other/`
- `todo/do-self/`

Si un ou plusieurs de ces répertoires est manquant :

> **ARRÊT OBLIGATOIRE — Répertoire inadéquat**
> Afficher immédiatement à l'utilisateur la liste des répertoires manquants avec le message :
> "Le répertoire de travail n'est pas configuré correctement. Répertoires manquants : [liste]. Veuillez corriger la structure avant de relancer."
> **Ne pas poursuivre. Attendre.**

Si tout existe, poursuivre.

## Étape 1 — Analyse parallèle des mails

Si aucun sous-répertoire n'est présent dans `inbox/`, passer directement à l'Étape 3 (Compte-rendu) en indiquant qu'aucun nouveau mail n'a été trouvé. Ne pas exécuter l'Étape 2 : les fichiers `pending_emails.json` existants dans les sous-répertoires de `todo/` doivent être conservés tels quels.

Lister tous les sous-répertoires de `inbox/`. Chacun correspond à un mail téléchargé.

Lancer l'agent `mail-analyzer` en parallèle sur **tous** les mails via l'outil `Task`. Chaque appel `Task` reçoit comme prompt :

```
Analyse le mail situé dans le répertoire <chemin_absolu_du_sous-répertoire>.
Lis le fichier SKILL.md de l'agent : @${CLAUDE_PLUGIN_ROOT}/agents/mail-analyzer.md
Suis les instructions de l'agent pour produire le fichier _analysis.json.
```

**Lancer tous les appels `Task` dans un même tour** pour maximiser le parallélisme. Attendre la fin de tous les agents avant de passer à l'Étape 2.

Après la fin de tous les agents, vérifier que chaque sous-répertoire de `inbox/` contient bien un fichier `_analysis.json`. Si un `_analysis.json` est manquant (échec d'un agent), consigner l'erreur et exclure ce mail du traitement — il restera dans `inbox/` pour un traitement ultérieur.

## Étape 2 — Tri et génération des pending_emails.json

### 2a. Purge préalable

Écraser tous les fichiers `pending_emails.json` existants dans les 7 sous-répertoires de `todo/` en y écrivant un tableau JSON vide `[]` :
- `todo/trash/pending_emails.json`
- `todo/do-read-quick/pending_emails.json`
- `todo/do-read-long/pending_emails.json`
- `todo/do-decide/pending_emails.json`
- `todo/do-consult-and-decide/pending_emails.json`
- `todo/do-other/pending_emails.json`
- `todo/do-self/pending_emails.json`

Cela garantit qu'aucun résidu d'un cycle précédent ne persiste.

### Pré-autorisation des opérations fichiers

Avant de déplacer les mails, appeler l'outil `allow_cowork_file_delete` avec le chemin du répertoire `inbox/` pour pré-autoriser les opérations de déplacement. Cette étape est nécessaire pour les mails téléchargés dans une session Cowork précédente.

### 2b. Lecture des analyses et tri

Pour chaque sous-répertoire de `inbox/` contenant un `_analysis.json` :

1. Lire le fichier `_analysis.json` avec l'outil `Read`
2. Extraire le champ `category` qui détermine le sous-répertoire de destination
3. Déplacer le répertoire complet du mail (avec toutes ses pièces jointes, le `_analysis.json` inclus) de `inbox/` vers `todo/<category>/`

### 2c. Génération des pending_emails.json

Pour chaque sous-répertoire de `todo/` contenant des mails (sous-répertoires non vides), générer le fichier `pending_emails.json` à partir des `_analysis.json` des mails qui s'y trouvent.

Pour chaque mail, lire son `_analysis.json` et extraire les champs appropriés selon la catégorie :

**todo/trash/pending_emails.json :**

| Champ | Source dans `_analysis.json` |
|-------|----------------------------|
| `id` | `id` |
| `sender` | `sender` |
| `date` | `date` |
| `summary` | `summary` |

**todo/do-read-quick/pending_emails.json :**

| Champ | Source dans `_analysis.json` |
|-------|----------------------------|
| `id` | `id` |
| `sender` | `sender` |
| `date` | `date` |
| `synth` | `synth` |

**todo/do-read-long/pending_emails.json :**

| Champ | Source dans `_analysis.json` |
|-------|----------------------------|
| `id` | `id` |
| `sender` | `sender` |
| `date` | `date` |
| `detailed-synth` | `detailed-synth` |

**todo/do-decide/pending_emails.json :**

| Champ | Source dans `_analysis.json` |
|-------|----------------------------|
| `id` | `id` |
| `sender` | `sender` |
| `date` | `date` |
| `choose-points` | `choose-points` |

**todo/do-consult-and-decide/pending_emails.json :**

| Champ | Source dans `_analysis.json` |
|-------|----------------------------|
| `id` | `id` |
| `sender` | `sender` |
| `date` | `date` |
| `choose-points` | `choose-points` |
| `transmit` | `transmit` |

**todo/do-other/pending_emails.json :**

| Champ | Source dans `_analysis.json` |
|-------|----------------------------|
| `id` | `id` |
| `sender` | `sender` |
| `date` | `date` |
| `synth` | `synth` |
| `transmit` | `transmit` |

**todo/do-self/pending_emails.json :**

| Champ | Source dans `_analysis.json` |
|-------|----------------------------|
| `id` | `id` |
| `sender` | `sender` |
| `date` | `date` |
| `synth` | `detailed-synth` |

### Champ optionnel `agenda-info` (toutes catégories)

Pour chaque mail dont le `_analysis.json` contient `"agenda-detected": true`, ajouter le champ `agenda-info` à l'entrée du `pending_emails.json`, quelle que soit la catégorie. Recopier directement l'objet `agenda-info` du `_analysis.json`.

### Format de sortie

Chaque fichier `pending_emails.json` est un tableau JSON :
```json
[
  {
    "id": "2026-02-18_13h24m00_1",
    "sender": "Nom de l'expéditeur",
    "date": "18 Fév",
    "...": "...champs spécifiques à la catégorie...",
    "agenda-info": "...optionnel, uniquement pour les mails liés à l'agenda..."
  }
]
```

Si un sous-répertoire de `todo/` est vide (ne contient aucun sous-répertoire de mail), ne pas créer de fichier `pending_emails.json` pour celui-ci (le fichier vide `[]` écrit lors de la purge suffit).

## Étape 3 — Compte-rendu

Présenter à l'utilisateur un compte-rendu complet du traitement effectué :

### Statistiques

- Répartition par catégorie sous forme de tableau :

| Catégorie | Nombre de mails |
|-----------|-----------------|
| Corbeille (`trash`) | ... |
| A lire - rapide (`do-read-quick`) | ... |
| A lire - long (`do-read-long`) | ... |
| Arbitrages rapides (`do-decide`) | ... |
| Arbitrages après consultation (`do-consult-and-decide`) | ... |
| A déléguer (`do-other`) | ... |
| A faire (`do-self`) | ... |

### Détail des mails triés

| Expéditeur | Objet | Catégorie |
|------------|-------|-----------|
| ... | ... | ... |

### Erreurs éventuelles

Si des erreurs ont été rencontrées (agents en échec, `_analysis.json` manquants, mails restés dans `inbox/`), les lister ici avec le détail du problème.
