# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

---

## [1.3.0] - 2026-03-30

### Corrigé
- **Opérations fichiers Cowork** — Ajout de pré-autorisations `allow_cowork_file_delete` dans `process-todo`, `todo-processor`, `sort-mails` et `check-inbox` pour corriger les `mv`/`rm` qui échouent silencieusement avec "Operation not permitted" sur les fichiers créés dans une session Cowork antérieure. Ajout de gestion d'erreur avec retry automatique.

---

## [1.2.0] - 2026-03-13

### Ajouté
- **Dashboard — Vue Tâches** — Nouvelle vue complète « Tâches » dans le dashboard avec 3 sections : Suivi consultations (lecture/édition de `consult.md`), Mails à envoyer (gestion des fichiers `to-send/` avec aperçu, copie presse-papier, édition), Travail à faire (gestion des dossiers `to-work/` avec checklist et documents). Suppression inline avec confirmation, modales d'édition, filtres et tris.
- **Format structuré des fichiers `to-send/`** — Les fichiers `.md` générés dans `to-send/` utilisent désormais un frontmatter YAML obligatoire (`to`, `cc`, `subject`, `date`, `ref_mail_id`) pour structurer les mails comme des messages prêts à envoyer.

### Modifié
- **process-todo** — Étape 3f : la mise à jour de `consult.md` inclut désormais les mails `do-other` en plus de `do-consult-and-decide`.
- **todo-processor** — Mode `finalize` : ajout de `finalization.consult_entry` pour la catégorie `do-other`. Spécification du format frontmatter YAML obligatoire pour tous les fichiers `to-send/`.

---

## [1.0.0] - 2026-03-13

Première release stabilisée de TodoMail.

### Ajouté
- **Dashboard v2 — Sauvegarde automatique** — Les fichiers `instructions.json` sont désormais générés et mis à jour automatiquement à chaque action utilisateur. Suppression du bouton « VALIDER LES ORDRES ». Toast de confirmation visuel à chaque sauvegarde.
- **Dashboard v2 — Valeurs par défaut intelligentes** — Action par défaut SUPPRIMER pour la catégorie Corbeille, TRAITER pour toutes les autres catégories. Les décisions existantes dans un `instructions.json` sont rechargées automatiquement au retour dans une catégorie.
- **Dashboard v2 — Menu de navigation** — Menu horizontal dans l'en-tête avec onglets Catégorisation (actif), Mémoire (placeholder) et Tâches (placeholder), préparant l'ajout de futures fonctionnalités.
- **Dashboard v2 — Scrollbar cartes dépliables** — Scrollbar discret dans les zones dépliables pour les synthèses longues.

### Modifié
- **README.md** — Mise à jour de la description du dashboard (auto-sync, défauts, menu nav). Ajout de `todo-processor.md` dans l'arborescence agents.
- **README.dashboard.md** — Documentation des nouvelles fonctionnalités : sauvegarde automatique, valeurs par défaut, menu de navigation principal, scrollbar. Mise à jour de la section instructions.json.

---

## [0.32.1] - 2026-03-12

### Modifié
- **todo-processor** — Passage du modèle Sonnet à Opus pour améliorer la qualité d'analyse et de rédaction.

---

## [0.32.0] - 2026-03-12

### Ajouté
- **Nouvel agent `todo-processor`** — Agent autonome qui traite un mail unique pour process-todo dans un contexte isolé. Trois modes : « autonomous » (traitement complet do-read-long : archivage, classement PJ, nettoyage), « analyze » (Phase 1 d'analyse et production de propositions pour les catégories interactives), « finalize » (Phase 2 d'archivage et finalisation après validation utilisateur). Produit un fichier `_treatment.json` dans le répertoire du mail.

### Modifié
- **process-todo** — Refonte de l'Étape 3. Les traitements « other » complexes sont désormais délégués à l'agent `todo-processor` via `Task` dans des contextes isolés. Phase 1 (analyse) parallélisée sur tous les mails. Les ARRÊTS OBLIGATOIRES restent dans le contexte principal. Phase 2 (finalisation) parallélisée après validation utilisateur. Ajout de `Task` dans les `allowed-tools`. Pré-allocation des numéros `to-send/` pour éviter les conflits entre agents parallèles. Consolidation centralisée de `consult.md` et de la mémoire après collecte de tous les résultats. Production des livrables do-self dans le contexte principal via les skills plateforme.
- **CONNECTORS.md** — Ajout de la colonne `todo-processor` dans le tableau d'utilisation des tools MCP. Mise à jour de la légende pour refléter la délégation process-todo → todo-processor.
- **README.md** — Ajout de `todo-processor` dans la table Agents.
- **memory-management** — Mise à jour de la section Intégration pour refléter la délégation à `todo-processor` et la consolidation mémoire centralisée.

### Optimisé
- **Réduction de la consommation de contexte** — Isolation du traitement de chaque mail dans un agent dédié, éliminant l'accumulation de contexte qui saturait le traitement dès 10-20 mails. Exécution parallèle des analyses (Phase 1) et des finalisations (Phase 2).

---

## [0.31.0] - 2026-03-03

### Ajouté
- **Nouvel agent `mail-analyzer`** — Agent autonome qui analyse un mail unique dans un contexte isolé : lecture du mail et de toutes les pièces jointes, contextualisation RAG, classification, détection agenda avec vérification de disponibilité et de conflits, production de synthèses multi-niveaux. Produit un fichier `_analysis.json` dans le répertoire du mail.

### Modifié
- **sort-mails v1.0.0** — Refonte complète du flux de tri. Les mails sont désormais analysés en parallèle par des agents `mail-analyzer` indépendants (un par mail), puis triés et les `pending_emails.json` générés exclusivement à partir des `_analysis.json`. Suppression de la triple lecture des mails. Suppression de la vérification par sondage (rendue inutile par l'isolation des contextes). Ajout de `Task` dans les `allowed-tools`.
- **Gains de performance** — Réduction drastique de la consommation de contexte, exécution parallèle des analyses, élimination des compressions de contexte en cours d'exécution.
- **README.md** — Ajout de la section Agents dans l'architecture, mise à jour de l'arborescence, cycle de vie des `pending_emails.json`.

---

## [0.30.0] - 2026-02-28

### Modifié
- **process-todo** — Traitement automatique après déplacement inter-catégories : lorsqu'un mail est reclassé via le dashboard vers une autre catégorie, il est désormais automatiquement traité comme une action `other` dans la catégorie de destination. Les déplacements vers `do-read-quick` sont traités immédiatement (archivage). Les déplacements vers les autres catégories sont mis en file d'attente via `todo/_deferred.json`. Le champ `agenda-info` est explicitement recopié lors des déplacements inter-catégories.

---

## [0.29.0] - 2026-02-25

### Corrigé
- Correction du nommage `/check_agenda` → `/check-agenda` dans tous les fichiers (cohérence kebab-case).
- Ajout de `AskUserQuestion` dans les `allowed-tools` du skill `agenda`.
- Correction du skill `disponibilites` : ajout d'un appel `fetch_calendar_events` (étape 1b) pour calculer les buffers de déplacement.
- Harmonisation de la taille cible de CLAUDE.md à ~250 lignes dans le skill `memory-management`.

### Modifié
- **dashboard.html** — Affichage des informations `agenda-info` : badge compact dans la carte principale et panneau détaillé dans la section dépliable.
- **process-todo** — Exploitation du champ `agenda-info` dans les 4 handlers d'actions complexes.
- **start** — Ajout de la création de `memory/context/preferences-agenda.md` lors du bootstrap calendrier.
- **/briefing** — Ajout d'une étape de mise à jour de la mémoire. Ajout de `Task` dans les `allowed-tools`.
- **/check-agenda** — Ajout d'une étape de mise à jour de la mémoire.
- **CONNECTORS.md** — Refonte du tableau d'utilisation des tools.

### Optimisé
- **sort-mails** — Pré-chargement calendrier unique sur 14 jours au lieu d'appels redondants par mail.
- Externalisation de la géographie : remplacement des données codées en dur par des références à la mémoire.

---

## [0.28.0] - 2026-02-22

### Ajouté
- **Skill `agenda` v1.0.0** — Connaissance du programme de l'utilisateur (consultation calendrier, enrichissement contextuel, détection conflits, signalement déplacements).
- **Skill `disponibilites` v1.0.0** — Connaissance des créneaux libres avec filtres contextuels.
- **Skill `detection-conflits` v1.0.0** — Détection des conflits, superpositions, temps de déplacement insuffisant et surcharge.
- **Commande `/briefing`** — Génération de dossiers de préparation pour les réunions.
- **Commande `/check-agenda`** — Audit de cohérence et faisabilité de l'agenda avec rapport structuré.
- **sort-mails v0.15.0** — Détection des mails liés à l'agenda. Enrichissement automatique avec vérification de disponibilité et détection de conflits. Ajout du champ optionnel `agenda-info`.
- **memory-management v0.3.0** — Ajout des sections mémoire calendrier : réunions récurrentes, lieux fréquents, préférences agenda.
- **start** — Ajout du répertoire `to-brief/`, bootstrap calendriers, nouvelles sections CLAUDE.md.
- **CONNECTORS.md** — Ajout des tools calendrier et du tableau d'utilisation par composant.

---

## [0.27.0] - 2026-02-18

### Modifié
- **sort-mails v0.14.0** — Si inbox est vide, ne plus purger ni régénérer les `pending_emails.json` existants (préservation des synthèses).
- **process-todo** — Mise à jour du `pending_emails.json` de la catégorie destination lors des déplacements inter-catégories. Remplacement de la suppression des `instructions.json` par un écrasement avec `[]`.
- **memory-management v0.2.0** — Enrichissement de la description avec des phrases de déclenchement. Ajout de `process-todo` dans la section intégration.

### Corrigé
- **README.dashboard.md** — Correction du libellé de l'action `delete`.

---

## [0.26.0] - 2026-02-15

### Modifié
- **sort-mails v0.13.0** — Ajout d'une purge préalable des `pending_emails.json` en début d'Étape 2.
- **process-todo** — Mise à jour incrémentale des `pending_emails.json` au fil de l'eau au lieu d'une régénération complète en Étape 4.
