---
description: Exécuter les instructions du dashboard sur les mails triés
allowed-tools: Read, Write, Bash(mkdir:*), Bash(mv:*), Bash(ls:*), Bash(cp:*), Bash(python3:*), Glob, Grep, AskUserQuestion, mcp
---

# Process Todo — Exécution des instructions du dashboard

Lire les fichiers `instructions.json` générés par le dashboard dans les sous-répertoires de `todo/` et exécuter les actions correspondantes pour chaque mail.

> **RÈGLE FONDAMENTALE D'EXÉCUTION :** Ce skill alterne entre phases autonomes et phases interactives. Lors de chaque ARRÊT OBLIGATOIRE, afficher immédiatement le message ou la proposition à l'utilisateur, puis cesser toute exécution et attendre une réponse explicite avant de continuer. Ne jamais enchaîner une phase interactive avec la phase suivante sans réponse reçue.

## Vérification préalable

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

Si tout existe, poursuivre.

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

## Étape 3 — Exécution des actions `other` complexes

### Constitution de la file de traitement

Constituer la file de traitement en combinant deux sources :
1. **Actions `other` classiques :** les mails dont l'action est `other` dans les `instructions.json`, tels que collectés en Étape 1.
2. **Traitements différés post-déplacement :** lire le fichier `todo/_deferred.json` (s'il existe et n'est pas vide). Pour chaque entrée, le mail se trouve dans `todo/{destination}/{id}/` et doit être traité avec le handler `other` de la catégorie `{destination}`.

Ordre de traitement recommandé :
1. D'abord les traitements **autonomes** (actions `other` de `do-read-long`, qu'elles soient classiques ou différées) — pas d'interaction requise.
2. Puis les traitements **interactifs** (actions `other` de `do-decide`, `do-consult-and-decide`, `do-other`, `do-self`, qu'ils soient classiques ou différés) — séquentiellement, avec les ARRÊTS OBLIGATOIRES habituels.

Traiter **séquentiellement**, **un mail à la fois**, les mails de la file de traitement.

> **OBLIGATION DE LECTURE DIRECTE — ANTI-HALLUCINATION**
>
> **Il est formellement interdit de produire un arbitrage, une synthèse, un plan d'action, un livrable ou tout contenu dérivé d'un mail sans avoir effectivement lu le fichier source avec un outil (`Read` ou `Bash`) au cours de cette étape.**
>
> - Pour chaque mail traité, **lire effectivement** le fichier `message.json` et **lire effectivement chaque pièce jointe** avant de procéder à l'analyse ou à la rédaction.
> - **Ne pas utiliser de sous-agents (`Task`)** pour cette étape. Tout le travail doit être réalisé dans le contexte principal.
> - Si une pièce jointe ne peut pas être lue (format inconnu, fichier corrompu), le mentionner explicitement comme « pièce jointe non lisible : [nom du fichier] ».
>
> **Méthodes de lecture par format de pièce jointe :**
>
> | Format | Méthode |
> |--------|---------|
> | `.json`, `.txt`, `.md`, `.html`, `.csv` | `Read` directement |
> | `.pdf` | `Read` directement (rendu natif) |
> | `.docx` | Utiliser le skill **docx** (section « Reading Content ») |
> | `.xlsx` | Utiliser le skill **xlsx** (section « Reading and analyzing data ») |
> | `.pptx` | Utiliser le skill **pptx** (section « Reading Content ») |
> | `.odt`, `.ods`, `.odp` | Utiliser le skill **read-odf** du plugin |
> | Autres formats binaires | Ignorer, mentionner comme « pièce jointe non lisible : [nom] » |

Pour chaque mail traité dans cette étape, afficher en début de traitement :
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Traitement mail {N}/{total} — {id}
Catégorie : {catégorie}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```
Pour les mails issus d'un déplacement (traitements différés), enrichir le bandeau :
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Traitement mail {N}/{total} — {id}
Catégorie : {destination} (reclassé depuis {source})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Action `other` dans `do-read-long`

1. **Archiver le mail :** Renommer `message.eml` en `{id}.eml`, extraire AAAA/MM depuis l'id, créer `mails/AAAA/MM/` si nécessaire, déplacer le fichier renommé dans `mails/AAAA/MM/`
2. **Classer les pièces jointes :** Lire chaque pièce jointe du sous-répertoire `{id}/`. Pour chacune, utiliser le tool MCP `search_doc` de `~~todomail-mcp` pour rechercher des documents similaires dans la base documentaire. Déterminer dans quel répertoire de `docs/` la pièce jointe devrait être stockée (en se basant sur les résultats de la recherche : même thématique, même type de document). Déplacer la pièce jointe dans le répertoire identifié.
3. **Nettoyer :** Déplacer l'ensemble du sous-répertoire `{id}` dans `to-clean-by-user/`
4. **Mettre à jour la mémoire :** Utiliser le skill `memory-management` pour mettre à jour la mémoire si de nouvelles connaissances pertinentes ont été identifiées (nouveau sujet, nouveau collaborateur, nouvelle thématique) et pour mettre à jour les préférences ou habitudes de l'utilisateur (en particulier sur les décisions prises)
5. **Mettre à jour le pending_emails.json :** Lire le fichier `pending_emails.json` de la catégorie source, retirer l'entrée correspondante (par `id`), et réécrire le fichier avec le tableau mis à jour (qui peut être `[]` si c'était le dernier mail)

### Action `other` dans `do-decide`

**Phase 1 — Analyse et rédaction** (exécution autonome)

1. **Analyser :** Lire le corps du message (`message.json`) et les pièces jointes éventuelles
2. **Contextualiser :** Utiliser le skill `memory-management` (lookup flow complet : CLAUDE.md → memory/ → MCP `~~todomail-mcp` via `search_all`) pour rechercher toutes connaissances utiles sur le dossier, le sujet ou la thématique sur laquelle il est demandé d'arbitrer
3. **Exploiter `agenda-info` (si présent) :** Si l'entrée du mail dans le `pending_emails.json` contient un champ `agenda-info`, intégrer ces informations dans l'analyse :
   - Si `disponibilite` = "disponible" : mentionner la disponibilité confirmée dans le projet d'arbitrage
   - Si `disponibilite` = "conflit" : intégrer le détail du conflit (`conflit-detail`) et les créneaux alternatifs (`creneaux-alternatifs`) comme éléments de contexte dans l'arbitrage
   - Si `coherence` signale des écarts : les mentionner comme point d'attention
4. **Rédiger un projet d'arbitrage :** Produire un document markdown structuré contenant :
   - Le contexte du dossier
   - La demande d'arbitrage
   - Les options identifiées avec avantages et inconvénients
   - La recommandation argumentée

---

> **ARRÊT OBLIGATOIRE — Validation du projet d'arbitrage**
> Afficher immédiatement le projet d'arbitrage complet à l'utilisateur.
> Poser la question suivante de manière visible :
>
> **"Projet d'arbitrage pour le mail {id} ({expéditeur}) — Validez-vous ce projet ?**
> **Répondez OUI pour valider et enregistrer, ou indiquez vos modifications."**
>
> **NE PAS passer à la Phase 2 avant d'avoir reçu une réponse explicite de l'utilisateur.**
> **Cesser toute exécution. Attendre.**

---

**Phase 2 — Enregistrement et finalisation** (après réception de la validation)

4. **Enregistrer :** Sauvegarder le projet d'arbitrage validé dans `to-send/{nom_destinataire}_{numéro_ordre}.md`. Le nom du destinataire est déduit du mail original (l'expéditeur de la demande d'arbitrage). Le numéro d'ordre est incrémenté pour éviter les doublons (vérifier les fichiers existants dans `to-send/` commençant par le même nom de destinataire).
5. **Finaliser :** Exécuter les mêmes actions que pour `other` dans `do-read-long` (archiver .eml, classer pièces jointes, nettoyer, mettre à jour la mémoire, mettre à jour le pending_emails.json)

### Action `other` dans `do-consult-and-decide`

**Phase 1 — Analyse et identification** (exécution autonome)

1. **Analyser :** Lire le corps du message et les pièces jointes éventuelles
2. **Exploiter `agenda-info` (si présent) :** Si l'entrée du mail dans le `pending_emails.json` contient un champ `agenda-info`, intégrer ces informations dans la transmission au collaborateur consulté (disponibilité, conflit éventuel, créneaux alternatifs)
3. **Identifier le destinataire :** Utiliser le skill `memory-management` pour déterminer à quel collaborateur transmettre le message pour consultation

---

> **ARRÊT OBLIGATOIRE — Validation du destinataire**
> Afficher immédiatement à l'utilisateur le résumé du mail et le destinataire identifié.
> Poser la question suivante de manière visible :
>
> **"Mail {id} ({expéditeur}) — Pour consultation avant arbitrage, j'ai identifié : {nom_destinataire}.**
> **Est-ce le bon destinataire ? Répondez OUI pour confirmer, ou indiquez le destinataire correct."**
>
> **NE PAS passer à la Phase 2 avant d'avoir reçu une réponse explicite de l'utilisateur.**
> **Cesser toute exécution. Attendre.**

---

**Phase 2 — Rédaction et enregistrement** (après confirmation du destinataire)

3. **Rédiger le mail de transmission :** Rédiger un mail de transmission demandant les éléments d'analyse avant d'arbitrer. L'enregistrer au format markdown dans `to-send/{nom_destinataire}_{numéro_ordre}.md` (incrémenter le numéro d'ordre pour éviter les doublons).
4. **Mettre à jour le registre de consultation :** Ajouter une ligne dans le fichier `consult.md` situé à la racine du répertoire de travail (créer le fichier s'il n'existe pas, avec un en-tête de tableau markdown). La ligne contient :
   - `id` du message
   - Date du jour
   - Nom du destinataire
   - Résumé du message et de ses pièces jointes

   Format du fichier `consult.md` :
   ```markdown
   # Registre des consultations

   | ID | Date | Destinataire | Résumé |
   |----|------|-------------|--------|
   | {id} | {date_du_jour} | {nom_destinataire} | {résumé} |
   ```
5. **Finaliser :** Exécuter les mêmes actions que pour `other` dans `do-read-long` (archiver .eml, classer pièces jointes, nettoyer, mettre à jour la mémoire, mettre à jour le pending_emails.json)

### Action `other` dans `do-other`

**Phase 1 — Analyse et identification** (exécution autonome)

1. **Analyser :** Lire le corps du message et les pièces jointes éventuelles
2. **Exploiter `agenda-info` (si présent) :** Si l'entrée du mail dans le `pending_emails.json` contient un champ `agenda-info`, intégrer ces informations dans le mail de transmission (disponibilité, conflit éventuel, créneaux alternatifs proposés)
3. **Identifier le destinataire :** Utiliser le skill `memory-management` pour déterminer à quel collaborateur transmettre le message pour qu'il le traite.

---

> **ARRÊT OBLIGATOIRE — Validation du destinataire**
> Afficher immédiatement à l'utilisateur le résumé du mail et le destinataire identifié.
> Poser la question suivante de manière visible :
>
> **"Mail {id} ({expéditeur}) — Pour transmission avec suite à donner, j'ai identifié : {nom_destinataire}.**
> **Est-ce le bon destinataire ? Répondez OUI pour confirmer, ou indiquez le destinataire correct."**
>
> **NE PAS passer à la Phase 2 avant d'avoir reçu une réponse explicite de l'utilisateur.**
> **Cesser toute exécution. Attendre.**

---

**Phase 2 — Rédaction et finalisation** (après confirmation du destinataire)

3. **Rédiger le mail de transmission :** Rédiger un mail de transmission pour suite à donner. L'enregistrer au format markdown dans `to-send/{nom_destinataire}_{numéro_ordre}.md` (incrémenter le numéro d'ordre pour éviter les doublons).
4. **Finaliser :** Exécuter les mêmes actions que pour `other` dans `do-read-long` (archiver .eml, classer pièces jointes, nettoyer, mettre à jour la mémoire, mettre à jour le pending_emails.json)

### Action `other` dans `do-self`

**Phase 1 — Analyse et préparation** (exécution autonome)

1. **Analyser :** Lire le corps du message et les pièces jointes éventuelles
2. **Contextualiser :** Utiliser le skill `memory-management` (lookup flow complet) pour rechercher toutes connaissances utiles sur le dossier, le sujet ou la thématique
3. **Exploiter `agenda-info` (si présent) :** Si l'entrée du mail dans le `pending_emails.json` contient un champ `agenda-info`, intégrer ces informations dans le plan d'action :
   - Si `disponibilite` = "disponible" : inclure le créneau comme échéance dans la checklist
   - Si `disponibilite` = "conflit" : proposer les créneaux alternatifs (`creneaux-alternatifs`) et mentionner le conflit à résoudre
   - Si des `dates-proposees` existent : les intégrer comme jalons dans le plan d'action
4. **Préparer la proposition :** Élaborer :
   - Un plan d'action structuré intégrant des échéances structuré sous forme d'un fichier `checklist.md`
   
Format du fichier `checklist.md` :
   ```markdown
   # Plan d'action {objet du mail}
   
   **Contexte:** {Résumé de la demande}
   
   **Contact:**
   	{expéditeur}
   	
   	## A FAIRE
   	- [ ]  {Tache 1} pour le {échéance 1} 
   	- [ ]  {Tache 2} pour le {échéance 2} 
   	- ...
   ```
      
      - La liste des livrables proposés (note, graphique, tableau Excel, présentation PowerPoint) avec une description de ce que chacun contiendrait

---

> **ARRÊT OBLIGATOIRE — Validation du plan et des livrables**
> Afficher immédiatement à l'utilisateur le plan d'action et la liste des livrables proposés.
> Poser la question suivante de manière visible :
>
> **"Mail {id} ({expéditeur}) — Voici le plan d'action et les livrables proposés.**
> **Validez-vous cette proposition ? Répondez OUI pour lancer la préparation, ou indiquez vos modifications."**
>
> **NE PAS passer à la Phase 2 avant d'avoir reçu une réponse explicite de l'utilisateur.**
> **Cesser toute exécution. Attendre.**

---

**Phase 2 — Production et stockage** (après validation de la proposition)

3. **Rédiger un projet de mail de réponse** : indiquer que la demande a bien été prise en compte et qu'une réponse complète sera apportée à {échéance}. A enregistrer dans `to-send/`
4. **Produire les livrables :** Créer les projets de livrables (note, graphique, tableau Excel, présentation PowerPoint)
5. **Stocker :** Enregistrer le fichier checklist.md, une copie des documents à signer s'il y en a, une copie des documents à relire s'il y en a et l'ensemble des documents préparés dans un sous-répertoire de `to-work/` nommé de façon descriptive (par exemple : `to-work/arbitrage-budget-2026/`)
6. **Finaliser :** Exécuter les mêmes actions que pour `other` dans `do-read-long` (archiver .eml, classer pièces jointes, nettoyer, mettre à jour la mémoire, mettre à jour le pending_emails.json)

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
| Traités (`other` complexes) | ... |
| Reclassés et traités (`other` après déplacement) | ... |

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

- Ce skill fait référence au skill `memory-management` pour le lookup flow et les mises à jour de la mémoire. Consulter `@${CLAUDE_PLUGIN_ROOT}/skills/memory-management/SKILL.md` pour les détails du fonctionnement de la mémoire.
- Les actions `other` complexes (do-decide, do-consult-and-decide, do-other, do-self) nécessitent des interactions obligatoires avec l'utilisateur. Elles sont traitées séquentiellement, un mail à la fois. Chaque ARRÊT OBLIGATOIRE doit être respecté : afficher le contenu, poser la question, attendre la réponse.
- **Traitement automatique après déplacement inter-catégories :** Lorsque l'utilisateur reclasse un mail via le dashboard (action = nom de catégorie), le mail est déplacé puis automatiquement traité comme une action `other` dans la catégorie de destination. Le fichier `todo/_deferred.json` sert de file d'attente persistante entre l'Étape 2 (déplacement) et l'Étape 3 (traitement). Ce mécanisme évite un aller-retour avec le dashboard. Le fichier est écrasé avec `[]` en Étape 4.
- Le numéro d'ordre dans les noms de fichiers `to-send/` est déterminé en listant les fichiers existants commençant par le même préfixe de destinataire et en prenant le prochain numéro disponible (format : `{nom_destinataire}_{NN}.md` avec NN sur 2 chiffres).
- L'extraction AAAA/MM pour l'archivage se fait depuis l'identifiant du mail (les 10 premiers caractères de l'id, format `AAAA-MM-JJ`).
