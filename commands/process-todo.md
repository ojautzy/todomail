---
description: Exécuter les instructions du dashboard sur les mails triés
allowed-tools: Read, Write, Bash(mkdir:*), Bash(mv:*), Bash(ls:*), Bash(cp:*), Bash(python3:*), Glob, Grep, AskUserQuestion, Task, mcp
---

# Process Todo — Exécution des instructions du dashboard

Lire les fichiers `instructions.json` générés par le dashboard dans les sous-répertoires de `todo/` et exécuter les actions correspondantes pour chaque mail.

> **RÈGLE FONDAMENTALE D'EXÉCUTION :** Ce skill alterne entre phases autonomes et phases interactives. Lors de chaque ARRÊT OBLIGATOIRE, afficher immédiatement le message ou la proposition à l'utilisateur, puis cesser toute exécution et attendre une réponse explicite avant de continuer. Ne jamais enchaîner une phase interactive avec la phase suivante sans réponse reçue.

## Vérification préalable

### 1. Répertoires

Vérifier que le répertoire de travail contient les répertoires suivants :
- `todo/`
- `todo/trash/`
- `todo/do-read-quick/`
- `todo/do-read-long/`
- `todo/do-decide/`
- `todo/do-consult-and-decide/`
- `todo/do-other/`
- `todo/do-self/`
- `to-clean-by-user/`
- `mails/`
- `to-send/`
- `to-work/`
- `docs/`

Si un ou plusieurs de ces répertoires est manquant :

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

## Étape 1 — Collecte des instructions

Parcourir les 7 sous-répertoires de `todo/` :
- `trash`
- `do-read-quick`
- `do-read-long`
- `do-decide`
- `do-consult-and-decide`
- `do-other`
- `do-self`

Pour chacun, vérifier si un fichier `instructions.json` existe. Si oui, lire son contenu (tableau JSON de `{ "id", "action" }`). Conserver pour chaque instruction le répertoire source (la catégorie dans laquelle le mail se trouve actuellement).

Si aucun fichier `instructions.json` n'est trouvé dans aucun sous-répertoire :

> **ARRÊT OBLIGATOIRE — Aucune instruction**
> Afficher immédiatement à l'utilisateur :
> "Aucun fichier instructions.json trouvé. Utilisez d'abord le dashboard pour valider vos décisions sur les mails triés."
> **Ne pas poursuivre. Attendre.**

Une fois les instructions collectées, afficher un résumé de ce qui va être traité :
```
Instructions collectées :
- trash : N mails
- do-read-quick : N mails
- do-read-long : N mails (dont N avec action "other")
- do-decide : N mails (dont N avec action "other")
- do-consult-and-decide : N mails (dont N avec action "other")
- do-other : N mails (dont N avec action "other")
- do-self : N mails (dont N avec action "other")

Passage à l'exécution des actions simples...
```

## Étape 2 — Exécution des actions simples

Traiter les instructions qui ne nécessitent pas d'interaction utilisateur. Pour chaque instruction collectée à l'étape 1 :

### Action `keep`

Ne rien faire. Passer au mail suivant.

### Action `delete`

Déplacer l'ensemble du sous-répertoire `{id}` représentant le mail vers le répertoire `to-clean-by-user/`.

### Actions de déplacement vers une autre catégorie

Si l'action est l'un des noms de catégorie (`do-read-quick`, `do-read-long`, `do-decide`, `do-consult-and-decide`, `do-other`, `do-self`) :
1. Déplacer l'ensemble du sous-répertoire `{id}` vers `todo/{action}/`
2. **Mettre à jour le `pending_emails.json` de la catégorie destination :** Lire le fichier `message.json` du mail déplacé, puis ajouter une nouvelle entrée dans le `pending_emails.json` de `todo/{action}/` avec les champs spécifiques à cette catégorie (selon le format décrit dans le skill `sort-mails`). Si le fichier `pending_emails.json` de destination n'existe pas ou contient `[]`, créer un nouveau tableau avec cette entrée. Si l'entrée source dans le `pending_emails.json` de la catégorie d'origine contenait un champ `agenda-info`, le recopier dans la nouvelle entrée de destination. **OBLIGATION : lire effectivement le fichier `message.json` et les pièces jointes avant de produire les champs descriptifs — appliquer les mêmes règles anti-hallucination et la même table de méthodes de lecture que dans l'Étape 3.**
3. **Enchaîner avec le traitement `other` de la catégorie destination :**
   - **Si la destination est `do-read-quick` :** exécuter immédiatement le traitement `other` dans `do-read-quick` (voir section « Action `other` dans `do-read-quick` » ci-dessous), en opérant dans `todo/do-read-quick/{id}/` après déplacement.
   - **Si la destination est `do-read-long`, `do-decide`, `do-consult-and-decide`, `do-other` ou `do-self` :** ajouter une entrée dans le fichier `todo/_deferred.json` pour traitement différé en Étape 3. Ce fichier est un tableau JSON ; le créer avec `[]` s'il n'existe pas. Chaque entrée a le format : `{"id": "{id}", "destination": "{action}", "source": "{catégorie_source}"}`. Le mail sera traité automatiquement comme une action `other` dans sa catégorie de destination lors de l'Étape 3, évitant ainsi un aller-retour avec le dashboard.

### Action `other` dans `do-read-quick`

1. Dans le sous-répertoire `todo/do-read-quick/{id}/`, renommer le fichier `message.eml` en `{id}.eml`
2. Extraire l'année (AAAA) et le mois (MM) depuis l'identifiant `{id}` (exemple : `2026-02-18_13h24m00_1` → AAAA=`2026`, MM=`02`)
3. Créer le répertoire `mails/AAAA/MM/` s'il n'existe pas
4. Déplacer le fichier `{id}.eml` dans `mails/AAAA/MM/`
5. Déplacer l'ensemble du sous-répertoire `{id}` dans `to-clean-by-user/`

### Mise à jour incrémentale du pending_emails.json

Après chaque action exécutée sur un mail (`delete`, déplacement vers autre catégorie, archivage `do-read-quick`) :
1. Lire le fichier `pending_emails.json` de la catégorie source
2. Retirer l'entrée correspondante (par `id`) du tableau JSON
3. Réécrire le fichier avec le tableau mis à jour (qui peut être `[]` si c'était le dernier mail)

Une fois toutes les actions simples terminées, afficher un bilan intermédiaire :
```
Actions simples terminées :
- Conservés (keep) : N
- Supprimés (delete) : N
- Déplacés et traités immédiatement (vers do-read-quick) : N
- Déplacés pour traitement en Étape 3 : N (détail : N vers do-read-long, N vers do-decide, N vers do-consult-and-decide, N vers do-other, N vers do-self)
- Archivés do-read-quick (action other) : N

Passage au traitement des actions complexes...
```

## Étape 3 — Exécution des actions `other` complexes (via agent `todo-processor`)

Le traitement de chaque mail est délégué à l'agent `todo-processor` via `Task`, dans un contexte isolé. Cela évite l'accumulation de contexte lorsque de nombreux mails sont à traiter. L'agent applique les mêmes règles anti-hallucination (lecture obligatoire des fichiers sources) dans son propre contexte.

Les ARRÊTS OBLIGATOIRES restent dans le contexte principal de `process-todo` : les propositions produites par les agents sont présentées à l'utilisateur ici, et ses validations sont transmises aux agents de finalisation.

### Étape 3a — Constitution de la file de traitement

Constituer la file de traitement en combinant deux sources :
1. **Actions `other` classiques :** les mails dont l'action est `other` dans les `instructions.json`, tels que collectés en Étape 1.
2. **Traitements différés post-déplacement :** lire le fichier `todo/_deferred.json` (s'il existe et n'est pas vide). Pour chaque entrée, le mail se trouve dans `todo/{destination}/{id}/` et doit être traité avec le handler `other` de la catégorie `{destination}`.

Partitionner la file en deux groupes :
- **file_autonome** : mails de catégorie `do-read-long`
- **file_interactive** : mails de catégories `do-decide`, `do-consult-and-decide`, `do-other`, `do-self`

Pour chaque mail de la file interactive, lire l'entrée correspondante dans le `pending_emails.json` de sa catégorie pour extraire le champ `agenda-info` (s'il existe).

### Étape 3b — Lancement parallèle Phase 1

Lancer l'agent `todo-processor` en parallèle sur **tous** les mails des deux files via l'outil `Task`. Chaque appel `Task` reçoit comme prompt :

**Pour les mails de la file_autonome :**
```
Traite le mail situé dans le répertoire <chemin_absolu_du_sous-répertoire>.
Mode : autonomous
Catégorie : do-read-long
Répertoire de travail : <chemin_absolu_du_répertoire_de_travail>
Chemin du script read-odf : ${CLAUDE_PLUGIN_ROOT}/skills/read-odf/scripts/read_odf.py
Agenda-info : <objet JSON agenda-info ou null>
Lis le fichier de l'agent : @${CLAUDE_PLUGIN_ROOT}/agents/todo-processor.md
Suis les instructions de l'agent pour produire le fichier _treatment.json.
```

**Pour les mails de la file_interactive :**
```
Traite le mail situé dans le répertoire <chemin_absolu_du_sous-répertoire>.
Mode : analyze
Catégorie : <catégorie>
Répertoire de travail : <chemin_absolu_du_répertoire_de_travail>
Chemin du script read-odf : ${CLAUDE_PLUGIN_ROOT}/skills/read-odf/scripts/read_odf.py
Agenda-info : <objet JSON agenda-info ou null>
Lis le fichier de l'agent : @${CLAUDE_PLUGIN_ROOT}/agents/todo-processor.md
Suis les instructions de l'agent pour produire le fichier _treatment.json.
```

**Lancer tous les appels `Task` dans un même tour** pour maximiser le parallélisme. Attendre la fin de tous les agents avant de poursuivre.

Après la fin de tous les agents, vérifier que chaque sous-répertoire de mail contient bien un fichier `_treatment.json`. Si un `_treatment.json` est manquant (échec d'un agent), consigner l'erreur et exclure ce mail du traitement — il restera dans sa catégorie pour un traitement ultérieur.

### Étape 3c — Collecte des résultats autonomes

Pour chaque mail de la file_autonome dont le `_treatment.json` existe :
1. Lire le fichier `_treatment.json`
2. Si `status` est `"success"` : retirer l'entrée correspondante (par `id`) du `pending_emails.json` de la catégorie source et réécrire le fichier
3. Si `status` est `"error"` : consigner l'erreur, le mail reste en place

Afficher un résumé des traitements autonomes :
```
Traitements autonomes (do-read-long) : N succès, N erreurs
```

### Étape 3d — Validation séquentielle des propositions (ARRÊTS OBLIGATOIRES)

Traiter **séquentiellement**, **un mail à la fois**, les mails de la file_interactive dont le `_treatment.json` existe, dans l'ordre suivant : d'abord `do-decide`, puis `do-consult-and-decide`, puis `do-other`, puis `do-self`.

Pour chaque mail, afficher en début de traitement :
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Validation mail {N}/{total} — {id}
Catégorie : {catégorie}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```
Pour les mails issus d'un déplacement (traitements différés), enrichir le bandeau :
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Validation mail {N}/{total} — {id}
Catégorie : {destination} (reclassé depuis {source})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Puis lire le `_treatment.json` et présenter la proposition selon la catégorie :

#### do-decide

Afficher le projet d'arbitrage contenu dans `proposal.draft`.

> **ARRÊT OBLIGATOIRE — Validation du projet d'arbitrage**
> Afficher immédiatement le projet d'arbitrage complet à l'utilisateur.
> Poser la question suivante de manière visible :
>
> **"Projet d'arbitrage pour le mail {id} ({analysis.sender}) — Validez-vous ce projet ?**
> **Répondez OUI pour valider et enregistrer, ou indiquez vos modifications."**
>
> **NE PAS poursuivre avant d'avoir reçu une réponse explicite de l'utilisateur.**
> **Cesser toute exécution. Attendre.**

Conserver la réponse de l'utilisateur (validation ou contenu modifié) pour l'étape 3e.

#### do-consult-and-decide

Afficher le résumé du mail (`proposal.mail_summary`) et le consultant identifié (`proposal.consultant`).

> **ARRÊT OBLIGATOIRE — Validation du destinataire**
> Afficher immédiatement à l'utilisateur le résumé du mail et le destinataire identifié.
> Poser la question suivante de manière visible :
>
> **"Mail {id} ({analysis.sender}) — Pour consultation avant arbitrage, j'ai identifié : {proposal.consultant}.**
> **Est-ce le bon destinataire ? Répondez OUI pour confirmer, ou indiquez le destinataire correct."**
>
> **NE PAS poursuivre avant d'avoir reçu une réponse explicite de l'utilisateur.**
> **Cesser toute exécution. Attendre.**

Conserver la réponse de l'utilisateur (confirmation ou destinataire corrigé) pour l'étape 3e.

#### do-other

Afficher le résumé du mail (`proposal.mail_summary`) et le destinataire identifié (`proposal.handler`).

> **ARRÊT OBLIGATOIRE — Validation du destinataire**
> Afficher immédiatement à l'utilisateur le résumé du mail et le destinataire identifié.
> Poser la question suivante de manière visible :
>
> **"Mail {id} ({analysis.sender}) — Pour transmission avec suite à donner, j'ai identifié : {proposal.handler}.**
> **Est-ce le bon destinataire ? Répondez OUI pour confirmer, ou indiquez le destinataire correct."**
>
> **NE PAS poursuivre avant d'avoir reçu une réponse explicite de l'utilisateur.**
> **Cesser toute exécution. Attendre.**

Conserver la réponse de l'utilisateur (confirmation ou destinataire corrigé) pour l'étape 3e.

#### do-self

Afficher le plan d'action (`proposal.checklist`) et la liste des livrables proposés (`proposal.deliverables`).

> **ARRÊT OBLIGATOIRE — Validation du plan et des livrables**
> Afficher immédiatement à l'utilisateur le plan d'action et la liste des livrables proposés.
> Poser la question suivante de manière visible :
>
> **"Mail {id} ({analysis.sender}) — Voici le plan d'action et les livrables proposés.**
> **Validez-vous cette proposition ? Répondez OUI pour lancer la préparation, ou indiquez vos modifications."**
>
> **NE PAS poursuivre avant d'avoir reçu une réponse explicite de l'utilisateur.**
> **Cesser toute exécution. Attendre.**

Conserver la réponse de l'utilisateur (validation ou modifications) pour l'étape 3e.

### Étape 3e — Lancement parallèle Phase 2 (finalisation)

**Pré-allocation des numéros `to-send/` :** Avant de lancer les agents, lister les fichiers existants dans `to-send/`. Pour chaque mail validé, déterminer le destinataire final (confirmé ou corrigé par l'utilisateur) et allouer le prochain numéro disponible pour ce destinataire. Passer ce numéro à l'agent via le prompt.

Lancer l'agent `todo-processor` en parallèle pour **tous** les mails validés. Chaque appel `Task` reçoit comme prompt :

```
Traite le mail situé dans le répertoire <chemin_absolu_du_sous-répertoire>.
Mode : finalize
Catégorie : <catégorie>
Répertoire de travail : <chemin_absolu_du_répertoire_de_travail>
Chemin du script read-odf : ${CLAUDE_PLUGIN_ROOT}/skills/read-odf/scripts/read_odf.py

Contenu validé :
<contenu validé par l'utilisateur — projet d'arbitrage modifié, ou "validé sans modification">

Destinataire validé : <nom du destinataire confirmé ou corrigé>
Numéro to-send pré-alloué : <NN>

Lis le fichier de l'agent : @${CLAUDE_PLUGIN_ROOT}/agents/todo-processor.md
Suis les instructions de l'agent pour finaliser le traitement et mettre à jour le _treatment.json.
```

**Lancer tous les appels `Task` dans un même tour** pour maximiser le parallélisme. Attendre la fin de tous les agents.

### Étape 3f — Collecte des résultats de finalisation

Pour chaque mail finalisé :
1. Lire le `_treatment.json` mis à jour (dans `to-clean-by-user/{id}/`)
2. Si `status` est `"success"` : retirer l'entrée correspondante (par `id`) du `pending_emails.json` de la catégorie source et réécrire le fichier
3. Si `status` est `"error"` : consigner l'erreur

**Mise à jour de `consult.md` :** Pour chaque mail de catégorie `do-consult-and-decide` **ou `do-other`** dont le `_treatment.json` contient un champ `finalization.consult_entry` non null, ajouter cette ligne dans le fichier `consult.md` à la racine du répertoire de travail. Créer le fichier s'il n'existe pas, avec l'en-tête :
```markdown
# Registre des consultations

| ID | Date | Destinataire | Résumé |
|----|------|-------------|--------|
```

### Étape 3g — Production des livrables do-self

Pour chaque mail de catégorie `do-self` dont la finalisation est réussie :
1. Lire les spécifications des livrables dans `_treatment.json` (`proposal.deliverables`)
2. Produire les livrables dans le répertoire `to-work/` créé par l'agent (chemin dans `finalization.to_work_dir`) :
   - **Note** : créer le document via le skill plateforme **docx**
   - **Tableau Excel** : créer le classeur via le skill plateforme **xlsx**
   - **Présentation PowerPoint** : créer la présentation via le skill plateforme **pptx**
   - **Graphique** : créer via `Bash(python3:*)` avec matplotlib
3. Les spécifications dans `proposal.deliverables` et le contexte dans `analysis.summary` fournissent les éléments de contenu nécessaires sans relire le mail original

### Étape 3h — Consolidation mémoire

Collecter les champs `memory_updates` de **tous** les `_treatment.json` produits (files autonome et interactive confondues).

Pour chaque type de mise à jour :

1. **Nouveaux collaborateurs** (`new_people`) : pour chaque personne non déjà présente dans CLAUDE.md, créer ou mettre à jour `memory/people/{nom}.md` et évaluer si elle doit être ajoutée à CLAUDE.md (contact fréquent)
2. **Nouveaux sujets/dossiers** (`new_projects`) : pour chaque sujet non déjà présent, créer ou mettre à jour `memory/projects/{nom}.md` et évaluer si le sujet est actif (auquel cas l'ajouter à CLAUDE.md)
3. **Nouveaux termes** (`new_terms`) : pour chaque terme non déjà présent dans CLAUDE.md, l'ajouter à la section Termes
4. **Préférences** (`preferences`) : compléter ou amender la section Preferences de CLAUDE.md

Appliquer les conventions du skill `memory-management` : consulter `@${CLAUDE_PLUGIN_ROOT}/skills/memory-management/SKILL.md` pour les formats et conventions.

## Étape 4 — Nettoyage et compte-rendu

### Nettoyage

- Écraser les fichiers `instructions.json` traités avec un tableau vide `[]`
- Écraser le fichier `todo/_deferred.json` avec un tableau vide `[]` (s'il existe)
- **Vérification de cohérence des pending_emails.json :** Pour chaque sous-répertoire de `todo/`, lire le `pending_emails.json` s'il existe et vérifier que chaque entrée (par `id`) correspond à un sous-répertoire de mail effectivement présent dans la catégorie. Retirer toute entrée orpheline et réécrire le fichier. Si le tableau résultant est vide, écrire `[]`.

### Vérification de cohérence des pending_emails.json

La vérification de cohérence effectuée à l'étape de nettoyage est purement structurelle (correspondance `id` ↔ répertoires présents). Les contenus des synthèses ne sont pas modifiés : ils ont été générés par le skill `sort-mails` et n'ont pas besoin d'être régénérés.

### Compte-rendu final

Présenter à l'utilisateur un compte-rendu complet du traitement :

| Action | Nombre |
|--------|--------|
| Conservés (`keep`) | ... |
| Supprimés (`delete`) | ... |
| Déplacés et traités immédiatement (`do-read-quick`) | ... |
| Archivés (`do-read-quick` action `other`) | ... |
| Traités autonomes (`do-read-long` other) | ... |
| Traités interactifs (`other` complexes) | ... |
| Reclassés et traités (`other` après déplacement) | ... |

**Statistiques de traitement parallèle :**
```
Phase 1 (analyse parallèle) : N agents lancés, N succès, N erreurs
Phase 2 (finalisation parallèle) : N agents lancés, N succès, N erreurs
```

Si des fichiers ont été créés dans `to-send/`, les lister :
```
Fichiers à envoyer :
- to-send/jean-martin_01.md
- to-send/sarah-gestin_01.md
```

Si des répertoires ont été créés dans `to-work/`, les lister :
```
Dossiers à travailler :
- to-work/arbitrage-budget-2026/
```

**Vérification de cohérence :**
- Nombre d'entrées orphelines détectées et retirées des `pending_emails.json` (le cas échéant)

Si des erreurs ont été rencontrées, les lister avec le détail du problème.

## Notes

- Le traitement de chaque mail dans l'Étape 3 est délégué à l'agent `todo-processor` via `Task`, dans un contexte isolé. L'agent applique les mêmes règles anti-hallucination (lecture obligatoire des fichiers sources) et produit un `_treatment.json` servant de contrat structuré. Consulter `@${CLAUDE_PLUGIN_ROOT}/agents/todo-processor.md` pour les détails de l'agent.
- Ce skill fait référence au skill `memory-management` pour le lookup flow et les mises à jour de la mémoire (consolidation en étape 3h). Consulter `@${CLAUDE_PLUGIN_ROOT}/skills/memory-management/SKILL.md` pour les détails du fonctionnement de la mémoire.
- Les actions `other` complexes (do-decide, do-consult-and-decide, do-other, do-self) nécessitent des interactions obligatoires avec l'utilisateur. Les ARRÊTS OBLIGATOIRES sont gérés dans le contexte principal de process-todo (étape 3d), pas dans les agents. Chaque ARRÊT OBLIGATOIRE doit être respecté : afficher le contenu, poser la question, attendre la réponse.
- **Traitement automatique après déplacement inter-catégories :** Lorsque l'utilisateur reclasse un mail via le dashboard (action = nom de catégorie), le mail est déplacé puis automatiquement traité comme une action `other` dans la catégorie de destination. Le fichier `todo/_deferred.json` sert de file d'attente persistante entre l'Étape 2 (déplacement) et l'Étape 3 (traitement). Ce mécanisme évite un aller-retour avec le dashboard. Le fichier est écrasé avec `[]` en Étape 4.
- **Pré-allocation des numéros `to-send/` :** Les numéros d'ordre dans les noms de fichiers `to-send/` sont pré-alloués par process-todo avant le lancement des agents de finalisation (étape 3e), pour éviter les conflits de numérotation entre agents parallèles. Le format reste `{nom_destinataire}_{NN}.md` avec NN sur 2 chiffres.
- **Consolidation `consult.md` :** Les entrées du registre de consultation sont collectées depuis les `_treatment.json` et écrites séquentiellement par process-todo (étape 3f), pour éviter les écritures concurrentes.
- **Consolidation mémoire :** Les mises à jour mémoire sont collectées depuis tous les `_treatment.json` et appliquées en une seule passe par process-todo (étape 3h), pour éviter les conflits d'écriture sur CLAUDE.md et les fichiers memory/.
- L'extraction AAAA/MM pour l'archivage se fait depuis l'identifiant du mail (les 10 premiers caractères de l'id, format `AAAA-MM-JJ`).
