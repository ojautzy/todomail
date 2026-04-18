# **Documentation Technique : TodoMail Dashboard**

Ce document détaille le fonctionnement, la structure des données et les fonctionnalités du tableau de bord interactif de gestion des mails de TodoMail.

## **1\. Vue d'Ensemble**

L'application est une interface **"Human-in-the-loop"** (l'humain dans la boucle). Elle sert de pont décisionnel entre Claude (l'Agent IA) et l'utilisateur final pour **l'ensemble des 7 catégories de mails triés**.

* **Claude** prépare le travail en triant les mails et en générant des synthèses JSON adaptées à chaque catégorie.
* **Le Dashboard** présente ces informations de manière ergonomique avec une navigation par catégorie.
* **L'Utilisateur** navigue entre les catégories, consulte les synthèses contextuelles et ajuste les actions si nécessaire.
* **Claude** exécute les décisions via le skill `process-todo` basé sur les fichiers `instructions.json` générés automatiquement par le dashboard.

## **2\. Prérequis**

### Navigateurs supportés

Le dashboard utilise l'API **File System Access** pour lire et écrire directement dans le dossier de travail sans serveur backend. Cette API n'est disponible que dans les moteurs Chromium.

| Navigateur | Support |
|---|---|
| Google Chrome, Microsoft Edge, Arc, DIA, Opera, Brave, Vivaldi | ✅ supporté |
| Safari, Orion (moteurs WebKit — Apple refuse l'API) | ❌ non supporté |
| Firefox | ❌ non supporté |

Les navigateurs non supportés affichent un écran d'avertissement au chargement.

Un **mode compatible universel** basé sur un micro-serveur HTTP local (commande plugin dédiée) est suivi dans l'issue *Phase 5.5* et permettra d'utiliser le dashboard dans Safari/Firefox à terme.

### Environnement

* **Accès en lecture/écriture** accordé par l'utilisateur sur le répertoire racine du projet lors de la connexion initiale (une seule autorisation pour toutes les catégories).
* **Reconnexion automatique (alpha.8+)** : le `DirectoryHandle` est persisté via IndexedDB. Au prochain chargement du dashboard, si la permission n'a pas expiré côté navigateur, la connexion se refait silencieusement sans picker. Si elle a expiré, un bouton « Reprendre la connexion » permet de ré-autoriser en un clic, sans re-sélectionner le dossier.
* **Bouton « Oublier ce projet »** à côté de l'indicateur « Projet connecté » pour invalider le handle persisté (utile si tu changes de workspace).

### Technologies

React 18, Tailwind CSS, Lucide Icons (chargés via CDN pour une portabilité totale sans installation).

## **3\. Structure du Répertoire de Travail**

L'application s'attend à trouver l'arborescence suivante relative au fichier dashboard.html :

```
/PROJET_RACINE
│   dashboard.html
└── todo/
    ├── trash/
    │   ├── pending_emails.json
    │   ├── instructions.json
    │   └── [ID_MAIL_TIMESTAMP]/
    │       ├── message.eml
    │       ├── message.json
    │       └── [PIECES_JOINTES]
    ├── do-read-quick/
    │   ├── pending_emails.json
    │   ├── instructions.json
    │   └── [ID_MAIL_TIMESTAMP]/...
    ├── do-read-long/
    │   ├── pending_emails.json
    │   ├── instructions.json
    │   └── [ID_MAIL_TIMESTAMP]/...
    ├── do-decide/
    │   ├── pending_emails.json
    │   ├── instructions.json
    │   └── [ID_MAIL_TIMESTAMP]/...
    ├── do-consult-and-decide/
    │   ├── pending_emails.json
    │   ├── instructions.json
    │   └── [ID_MAIL_TIMESTAMP]/...
    ├── do-other/
    │   ├── pending_emails.json
    │   ├── instructions.json
    │   └── [ID_MAIL_TIMESTAMP]/...
    └── do-self/
        ├── pending_emails.json
        ├── instructions.json
        └── [ID_MAIL_TIMESTAMP]/...
```

Chaque sous-répertoire de `todo/` contient son propre `pending_emails.json` (entrée) et `instructions.json` (sortie).

**Note :** Un fichier `pending_emails.json` contenant un tableau vide `[]` est fonctionnellement équivalent à l'absence du fichier : le dashboard affiche un compteur à 0 et le message "Aucun mail dans cette catégorie". Cette propriété est exploitée par les skills pour purger les données sans suppression de fichier.

## **4\. Formats des Fichiers JSON**

### **A. pending\_emails.json (par catégorie)**

Chaque fichier `pending_emails.json` est généré par Claude (étape 3 du skill `sort-mails` v2.0.0) et contient les champs communs `id`, `sender`, `date` plus des champs spécifiques à la catégorie.

**Deux formats coexistent** depuis la version 2.0.0-alpha.3 :

- **v1 (legacy, jusqu'à la v1.4.1)** : tableau brut — `[ { ... }, { ... } ]`.
- **v2 (alpha.3+)** : wrapper `{ "_meta": { "schema_version": 2, "session_id": "...", "generated_at": "..." }, "emails": [ ... ] }`.

Le dashboard lit les deux formats de manière transparente (fonction `extractEmails(data)` qui renvoie toujours un tableau, et `extractEmailsAndMeta(data)` qui renvoie aussi le bloc `_meta` pour le banner de fraîcheur introduit en alpha.8). Il continue à écrire le format v1 dans les `instructions.json` ; la helper `extractInstructionsAndMeta(data)` permet de relire indifféremment v1 et v2.

Les exemples ci-dessous présentent le contenu d'une entrée du tableau `emails` (v2) ou d'une entrée du tableau racine (v1) — les champs sont identiques :

**trash :**
```json
[{ "id": "2026-02-18_13h24m00_1", "sender": "Nom", "date": "18 Fév", "summary": "Résumé court de l'objet et du corps" }]
```

**do-read-quick :**
```json
[{ "id": "...", "sender": "...", "date": "...", "synth": "Synthèse détaillée de l'objet et du corps" }]
```

**do-read-long :**
```json
[{ "id": "...", "sender": "...", "date": "...", "detailed-synth": "Synthèse détaillée incluant les pièces jointes" }]
```

**do-decide :**
```json
[{ "id": "...", "sender": "...", "date": "...", "choose-points": "Points d'arbitrage et enjeux" }]
```

**do-consult-and-decide :**
```json
[{ "id": "...", "sender": "...", "date": "...", "choose-points": "Points d'arbitrage", "transmit": "Personne à consulter" }]
```

**do-other :**
```json
[{ "id": "...", "sender": "...", "date": "...", "synth": "Synthèse courte de la demande", "transmit": "Personne à qui déléguer" }]
```

**do-self :**
```json
[{ "id": "...", "sender": "...", "date": "...", "synth": "Synthèse détaillée incluant ce qui est attendu" }]
```

### **A bis. Champ optionnel `agenda-info` (toutes catégories)**

Les mails détectés comme liés à l'agenda par le skill `sort-mails` contiennent un champ supplémentaire `agenda-info`. Ce champ est un objet JSON avec la structure suivante :

```json
{
  "agenda-info": {
    "type": "demande-rdv | invitation | changement | annulation | proposition-creneau | rappel",
    "dates-proposees": ["2026-03-03T14:00:00"],
    "disponibilite": "disponible | conflit | possiblement libre",
    "conflit-detail": "Description de l'événement en conflit (si applicable)",
    "creneaux-alternatifs": ["2026-03-03 10:00 - 11:00", "2026-03-04 09:00 - 10:00"],
    "coherence": "cohérent | description des écarts (si réunion déjà dans l'agenda)"
  }
}
```

Le dashboard affiche ces informations de deux manières :

* **Badge compact** dans la ligne principale de la carte mail : icône calendrier + type de lien agenda + statut de disponibilité, coloré selon le statut (rouge pour conflit, ambre pour possiblement libre, vert pour disponible)
* **Panneau détaillé** dans la section dépliable de la carte : dates proposées, détail du conflit, créneaux alternatifs et cohérence, avec bordure colorée selon la disponibilité

Ce champ est absent pour les mails qui ne sont pas liés à l'agenda. Le dashboard gère gracieusement son absence.

### **B. message.json (Détail par mail)**

Situé dans chaque sous-répertoire d'ID, il contient le contenu complet du mail (format identique pour toutes les catégories) :
```json
{
  "subject": "Objet du mail",
  "from": "Expéditeur <email@domain.com>",
  "body_text": "Corps complet du message texte...",
  "attachments": []
}
```

*Note : Les pièces jointes sont également détectées dynamiquement par le Dashboard en scannant le dossier, indépendamment de la balise attachments.*

### **C. instructions.json (Sortie du Dashboard)**

Fichier généré et mis à jour automatiquement par le dashboard. Un fichier `instructions.json` est écrit dans le sous-répertoire de chaque catégorie contenant des mails. Ces fichiers sont ensuite consommés par le skill `process-todo` (commande `/todomail:process-todo`) qui exécute les actions correspondantes.

**Comportement automatique (v2.0.0-alpha.8+) :**
- Au chargement d'une catégorie, le dashboard lit un `instructions.json` existant si présent (aucune auto-écriture de valeurs par défaut — changement alpha.8 par rapport aux versions antérieures).
- La première action utilisateur (changement de dropdown ou bulk action) déclenche la première écriture avec toutes les décisions en cours.
- Chaque changement ultérieur met à jour immédiatement le fichier.
- Un indicateur visuel (toast) confirme chaque sauvegarde.

**Valeurs par défaut :**
- Catégorie `trash` : `delete` (SUPPRIMER)
- Autres catégories : `other` (TRAITER)

```json
[{ "id": "2026-02-18_13h24m00_1", "action": "other" }]
```

**Formats supportés en lecture** (depuis 2.0.0-alpha.3) : v1 = tableau brut (comme ci-dessus), v2 = `{ "_meta": { ... }, "instructions": [ ... ] }`. Le dashboard écrit encore en v1 ; `process-todo` (Phase 3) produira du v2.

Valeurs possibles pour la balise `action` :

| Valeur | Description | Contexte |
|----------|-------------|----------|
| `keep` | Conserver le mail dans la catégorie actuelle | Toutes catégories |
| `other` | Marquer le mail comme traité | Toutes catégories sauf `trash` |
| `delete` | Déplacer vers le dossier de nettoyage `to-clean-by-user/` (depuis toutes catégories, y compris `trash`) | Toutes catégories |
| `do-read-quick` | Déplacer le mail vers cette catégorie | Toutes sauf celle-ci |
| `do-read-long` | Déplacer le mail vers cette catégorie | Toutes sauf celle-ci |
| `do-decide` | Déplacer le mail vers cette catégorie | Toutes sauf celle-ci |
| `do-consult-and-decide` | Déplacer le mail vers cette catégorie | Toutes sauf celle-ci |
| `do-other` | Déplacer le mail vers cette catégorie | Toutes sauf celle-ci |
| `do-self` | Déplacer le mail vers cette catégorie | Toutes sauf celle-ci |

*Note : L'option de déplacement vers la corbeille (`trash`) n'est pas proposée comme destination séparée. Depuis les catégories non-trash, l'action "METTRE A LA CORBEILLE" est l'action `delete`. Depuis `trash`, l'action `delete` déplace également le mail vers `to-clean-by-user/` (la suppression effective est laissée à l'utilisateur).*

*Note (v0.30.0+) : Les actions de déplacement vers une autre catégorie sont désormais automatiquement suivies du traitement `other` dans la catégorie de destination par `process-todo`. L'utilisateur n'a plus besoin de retourner dans le dashboard pour déclencher le traitement du mail reclassé.*

## **5\. Fonctionnalités Clés**

### Menu de navigation principal

Le dashboard dispose d'un menu de navigation dans l'en-tête avec des onglets pour les différentes fonctionnalités :
* **Catégorisation** : gestion des mails triés (vue par défaut)
* **Mémoire** : visualisation et édition des fichiers de mémoire à long terme (activé en alpha.8)
* **Tâches** : gestionnaire de tâches en 3 sections (consultations, mails à envoyer, travail à faire)

### Navigation multi-catégories

* **Sidebar verticale :** Panneau de navigation fixe sur la gauche, affichant les 7 catégories avec icônes et labels complets, toujours visibles.
* **Chargement dynamique :** Chaque catégorie charge ses propres données depuis son `pending_emails.json`.
* **Autorisation unique :** L'utilisateur n'a besoin d'autoriser l'accès au répertoire qu'une seule fois au démarrage.
* **Affichage contextuel :** Les champs affichés dans les cartes d'email s'adaptent automatiquement à la catégorie sélectionnée.
* **Badge compteur :** Chaque catégorie affiche le nombre de mails qu'elle contient dans la sidebar (style accentué pour la catégorie active, style discret pour les autres). Les compteurs sont chargés au démarrage pour toutes les catégories et mis à jour dynamiquement lors de la navigation.
* **Carte dépliable :** Chaque carte mail dispose d'un bouton de déploiement (chevron) qui affiche l'intégralité du texte des champs générés sans ouvrir le mail complet. Un scrollbar apparaît automatiquement si le contenu dépasse la zone dépliable.

### Sauvegarde automatique des instructions

* **Auto-sync :** Les fichiers `instructions.json` sont générés et mis à jour automatiquement, sans bouton de validation.
* **Valeurs par défaut intelligentes :** SUPPRIMER pour la catégorie Corbeille, TRAITER pour toutes les autres catégories.
* **Persistance :** Les décisions précédemment enregistrées dans un `instructions.json` existant sont rechargées automatiquement au retour dans une catégorie.
* **Feedback visuel :** Un toast de confirmation apparaît à chaque sauvegarde (vert pour succès, rouge pour erreur).

| Catégorie | Label | Champ affiché |
|-----------|-------|---------------|
| `trash` | Corbeille | `summary` |
| `do-read-quick` | A lire (rapide) | `synth` |
| `do-read-long` | A lire (long) | `detailed-synth` |
| `do-decide` | Arbitrages rapides | `choose-points` |
| `do-consult-and-decide` | Arbitrages après consultation | `choose-points` + `transmit` |
| `do-other` | A déléguer | `synth` + `transmit` |
| `do-self` | A faire | `synth` |

### Gestion du Système de Fichiers

* **Accès Direct :** Utilise window.showDirectoryPicker() pour manipuler les fichiers sans serveur backend.
* **Visualisation de Documents :** Ouverture des pièces jointes via des *Blob URLs* éphémères dans de nouveaux onglets.

### Navigation et Filtres

* **Recherche Temps Réel :** Filtrage instantané par mot-clé sur l'expéditeur et les champs spécifiques de la catégorie active.
* **Tri Rapide (Bulk Action) :** Fonction "Zap" permettant d'appliquer une action (ex: Supprimer) à tous les mails d'un même expéditeur en un clic.

### Interface (UI/UX)

* **Design Pro :** Utilisation de Tailwind CSS (Shadows, Glassmorphism, Transitions).
* **Mode Sombre :** Bascule dynamique via un état React persistant sur la session.
* **Modal de Détail :** Affichage riche avec police monospace pour le corps du mail et détection automatique des assets locaux.
* **Actions contextuelles :** Le dropdown d'actions propose dynamiquement les catégories de destination (toutes sauf la catégorie active et trash). L'action par défaut est SUPPRIMER pour la Corbeille et TRAITER pour les autres catégories.

## **6\. Vue Tâches**

La vue Tâches est accessible via le menu de navigation principal. Elle dispose de sa propre sidebar avec 3 sections, chacune connectée à une source de données distincte.

### Sidebar Tâches

| Section | Icône | Source | Description |
|---------|-------|--------|-------------|
| Suivi consultations | `eye` | `consult.md` | Registre des consultations en cours à suivre |
| Mails à envoyer | `send` | `to-send/*.md` | Projets de mails prêts à envoyer |
| Travail à faire | `clipboard-list` | `to-work/*/` | Dossiers de travail avec checklists et documents |

Chaque section affiche un badge compteur dans la sidebar.

### Section « Suivi consultations »

Lit et parse le fichier `consult.md` à la racine du répertoire de travail (table markdown avec colonnes : ID, Date, Destinataire, Résumé).

* **Carte par entrée** : affiche ID, date, destinataire et résumé
* **Filtre texte** : recherche sur tous les champs
* **Suppression** : checkbox avec confirmation inline (icônes check/x) — retire la ligne de `consult.md` et réécrit le fichier
* **Toast** de confirmation après suppression

### Section « Mails à envoyer »

Liste les fichiers `.md` dans le répertoire `to-send/`. Chaque fichier utilise un frontmatter YAML structuré :

```markdown
---
to: prenom.nom@email.com
cc: autre.personne@email.com
subject: Objet du mail
date: 2026-03-13
ref_mail_id: id_du_mail_source
---

Corps du mail en markdown...
```

* **Carte par fichier** : nom du destinataire (déduit du nom de fichier), objet du mail (extrait du frontmatter `subject`)
* **Flyover** (carte dépliable) : affiche `to`, `cc`, `subject`, aperçu du corps, boutons copier destinataire(s) et copier corps dans le presse-papier (feedback visuel temporaire)
* **Édition** : bouton ouvrant une modale textarea avec le contenu markdown complet, sauvegarde dans le fichier
* **Suppression** : checkbox avec confirmation inline — supprime le fichier `.md`
* **Filtre/tri** par destinataire

### Section « Travail à faire »

Liste les sous-répertoires de `to-work/`. Chaque répertoire représente une tâche.

* **Carte par répertoire** : nom du répertoire = nom de la tâche
* **Flyover** (carte dépliable) : contenu de `checklist.md` avec rendu des checkboxes markdown, liste des documents présents (tout fichier sauf `checklist.md`) avec ouverture via Blob URL
* **Édition** : bouton ouvrant une modale textarea pour éditer `checklist.md`
* **Suppression** : checkbox avec confirmation inline — supprime récursivement le répertoire (`removeEntry` avec `{ recursive: true }`)

### Patterns UX communs (vue Tâches)

* **Confirmation inline** : pas de `window.confirm()`, les suppressions utilisent un pattern check/x avec timeout d'annulation
* **Copie presse-papier** : `navigator.clipboard.writeText()` avec changement d'icône temporaire (clipboard-copy → check-circle)
* **Modale d'édition** : backdrop-blur, textarea monospace, boutons Annuler/Sauvegarder
* **Design** : même design system que la vue Catégorisation (Tailwind, dark mode, glassmorphism, animations slide-up, toasts)

## **7\. Vue Mémoire** *(alpha.8+)*

La vue Mémoire permet de consulter et d'éditer les fichiers de mémoire à long terme du projet depuis le dashboard, sans passer par un éditeur texte externe.

### Sidebar Mémoire

| Section | Source | Description |
|---------|--------|-------------|
| CLAUDE.md | `CLAUDE.md` (racine) | Mémoire de travail principale du projet |
| Personnes | `memory/people/*.md` | Fiches individuelles des interlocuteurs |
| Sujets | `memory/projects/*.md` | Dossiers thématiques et projets en cours |
| Contexte | `memory/context/*.md` | Référentiel partagé (lieux, réunions récurrentes, etc.) |

Chaque section affiche un compteur dans la sidebar.

### Patterns UX

* **Carte par fichier** : nom du fichier en monospace, aperçu de 240 caractères.
* **Carte dépliable** : affiche le contenu complet en monospace (whitespace préservé).
* **Édition** : modale textarea identique à la vue Tâches, sauvegarde directement dans le fichier.
* **Suppression** : confirmation inline check/x (désactivée pour CLAUDE.md).
* **Filtre texte** : recherche sur le nom et le contenu de tous les fichiers de la section active.

## **8\. Watch & versioning** *(alpha.8+)*

Le dashboard détecte automatiquement les modifications produites par Claude (via les commandes `/todomail:check-inbox`, `/todomail:process-todo`, etc.) grâce à un mécanisme de polling local, sans WebSocket ni modification du serveur MCP.

### Fichiers de surveillance (racine du workspace)

| Fichier | Écrit par | Rôle |
|---------|-----------|------|
| `dashboard_invalidate.txt` | Hook `PostToolUse` (`hooks/invalidate_dashboard_cache.py`) après chaque `mv`/`rm` sur `todo/`, `inbox/` ou `mails/` | Signal d'invalidation générique — son `lastModified` change à chaque modif. |
| `.todomail-state.json` | `lib/state.py.save_state()` (mirror du state canonique `${CLAUDE_PLUGIN_DATA}/state.json`) | Expose au dashboard le `session_id`, `active_lock` et `errors[]` courants. |

Le dashboard lit ces deux fichiers toutes les 3 secondes et déclenche un rafraîchissement si :
- `dashboard_invalidate.txt` a changé (Claude a bougé des fichiers),
- Le `session_id` du workspace a changé (nouveau cycle),
- Le verrou vient d'être libéré (fin de cycle),
- La liste des erreurs a changé.

### Banner de fraîcheur

Si le `_meta.session_id` du `pending_emails.json` courant ne correspond plus à la session active du workspace, un banner ambre apparaît en haut de la vue Catégorisation avec un bouton « Recharger ».

### Verrou pendant écriture Claude

Si `.todomail-state.json.active_lock` n'est pas `null` (un `sort-mails` ou `process-todo` est en cours), un banner bleu « Claude travaille… » s'affiche, les dropdowns de décision et les boutons bulk sont grisés. La libération du verrou au tick suivant déclenche un rafraîchissement automatique.

### Panneau d'erreurs et reprise

Si `state.errors[]` contient des entrées, un panneau rouge déployable liste les mails en échec avec leur phase, type d'erreur, compteur de tentatives et message. Deux actions :

* **Retry tous** : écrit `retry_request.txt` (liste des `mail_id` à relancer) à la racine du workspace. Consommé par `hooks/session_start.py` au prochain démarrage de commande (marque `retry_requested: true` sur les entrées correspondantes pour que `/process-todo --retry` les traite en priorité).
* **Ignorer** (par erreur) : écrit `errors_dismiss.txt` (un `mail_id` par ligne). Consommé par `hooks/session_start.py` qui retire les entrées correspondantes de `state.errors[]`.

Ces fichiers-marqueurs sont supprimés après consommation. L'architecture évite toute écriture concurrente du `state.json` entre le navigateur et les processus Python.

## **9\. Principes de Sécurité**

* **Sandboxing :** L'application n'accède qu'au dossier explicitement sélectionné par l'utilisateur.
* **Zéro Cloud :** Aucune donnée ne quitte la machine de l'utilisateur. Les fichiers sont lus et écrits localement par le navigateur.