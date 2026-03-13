# **Documentation Technique : Claude Cowork \- Mail Dashboard**

Ce document détaille le fonctionnement, la structure des données et les fonctionnalités du tableau de bord interactif de gestion des mails de Claude Cowork.

## **1\. Vue d'Ensemble**

L'application est une interface **"Human-in-the-loop"** (l'humain dans la boucle). Elle sert de pont décisionnel entre Claude Cowork (l'Agent IA) et l'utilisateur final pour **l'ensemble des 7 catégories de mails triés**.

* **Claude Cowork** prépare le travail en triant les mails et en générant des synthèses JSON adaptées à chaque catégorie.
* **Le Dashboard** présente ces informations de manière ergonomique avec une navigation par catégorie.
* **L'Utilisateur** navigue entre les catégories, consulte les synthèses contextuelles et ajuste les actions si nécessaire.
* **Claude Cowork** exécute les décisions via le skill `process-todo` basé sur les fichiers `instructions.json` générés automatiquement par le dashboard.

## **2\. Prérequis**

* **Navigateur :** Chrome, Edge ou Opera (moteurs Chromium) requis pour le support de l'API *File System Access*.
* **Environnement :** Accès en lecture/écriture accordé par l'utilisateur sur le répertoire racine du projet lors de la connexion initiale (une seule autorisation pour toutes les catégories).
* **Technologies :** React 18, Tailwind CSS, Lucide Icons (chargés via CDN pour une portabilité totale sans installation).

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

Chaque fichier `pending_emails.json` est généré par Claude Cowork (étape 2 du skill `sort-mails`) et contient les champs communs `id`, `sender`, `date` plus des champs spécifiques à la catégorie :

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

**Comportement automatique (v1.0.0+) :**
- Au chargement d'une catégorie, le dashboard lit un `instructions.json` existant ou en génère un avec les valeurs par défaut
- Chaque changement de sélection dans un dropdown met à jour immédiatement le fichier
- Les actions en masse (bulk action) mettent également à jour le fichier immédiatement
- Un indicateur visuel (toast) confirme chaque sauvegarde

**Valeurs par défaut :**
- Catégorie `trash` : `delete` (SUPPRIMER)
- Autres catégories : `other` (TRAITER)

```json
[{ "id": "2026-02-18_13h24m00_1", "action": "other" }]
```

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
* **Mémoire** : placeholder pour la future visualisation/édition de la mémoire
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

## **7\. Principes de Sécurité**

* **Sandboxing :** L'application n'accède qu'au dossier explicitement sélectionné par l'utilisateur.
* **Zéro Cloud :** Aucune donnée ne quitte la machine de l'utilisateur. Les fichiers sont lus et écrits localement par le navigateur.