---
name: classify-attachment
description: >
  Classement des pièces jointes dans docs/ selon la structure
  canonique AURA/MIN. Garde-fou structurel empêchant la création
  de répertoires parasites hors de la hiérarchie docs/AURA/ et docs/MIN/.
  Ce skill est un document de référence lu par l'agent todo-processor
  lors du classement des pièces jointes (il n'est pas invoqué directement).
version: 1.0.0
---

# Classement des pièces jointes

Ce skill est un document de référence lu par l'agent `todo-processor`
lors du classement des pièces jointes. L'agent lit ce fichier avec `Read`
puis applique l'algorithme ci-dessous.

## Structure canonique de docs/

Le répertoire `docs/` repose sur deux branches exclusives :

- **`docs/AURA/`** : documents liés à l'expérimentation 3DS avec la Région Auvergne-Rhône-Alpes (mise à disposition, conventions 3DS, finances 3DS, COPIL/COTECH/COSTRAT AURA, territoires expérimentés 07/15/43)
- **`docs/MIN/`** : documents liés à l'activité ministérielle traditionnelle de la DIR (RH, finances ministérielles, exploitation, transverse, communication, territoires hors-3DS, etc.)

**Règle absolue :** aucun répertoire ni fichier ne doit exister directement à la racine de `docs/` en dehors de ces deux branches (et `.gitkeep`).

---

## Conventions de nommage des répertoires

- Noms en **MAJUSCULES** et **underscores** uniquement
- **Pas de tirets**, pas de casse mixte, pas d'accents
- Exception : sous-répertoires territoriaux avec numéros de département (07, 12, 15, 34, 43, 48, 63)

| Exemple valide | Exemple INVALIDE |
|---|---|
| `MIN/RH/PROMOTIONS` | `RH-Travail` |
| `AURA/FINANCES/DAC` | `Transition-Ecologique` |
| `MIN/TRANSVERSE/SAGT` | `dossiers/GT-Pilote-DIR` |

---

## Algorithme de classement

Pour classer une pièce jointe, suivre ces étapes dans l'ordre :

### Étape 1 — Déterminer la branche racine (OBLIGATOIRE)

- **`AURA/`** si le document concerne la mise à disposition auprès de la Région AURA : expérimentation 3DS, finances 3DS, conventions 3DS, COPIL/COTECH/COSTRAT 3DS, territoire expérimenté 07/15/43 dans contexte 3DS
- **`MIN/`** pour tout le reste : activité ministérielle traditionnelle (RH, finances, exploitation, transverse, communication, territoires hors-3DS, etc.)

### Étape 2 — Rechercher le sous-répertoire cible via RAG

1. Appeler `search_doc` (MCP) pour rechercher des documents similaires dans la base documentaire
2. **Filtrer** : ne retenir que les résultats dont le chemin commence par `docs/{branche}/` (la branche déterminée en étape 1)
3. Le sous-répertoire cible est celui du résultat le plus pertinent dans la bonne branche

### Étape 3 — Fallback si aucun résultat pertinent dans la bonne branche

1. Lister les sous-répertoires existants de `docs/{branche}/` (profondeur 2) avec `ls`
2. Choisir le sous-répertoire le plus thématiquement proche en s'appuyant sur la table de correspondances ci-dessous
3. Si nécessaire, créer un nouveau sous-répertoire **DANS** la branche appropriée en respectant :
   - La hiérarchie existante (ex: `MIN/RH/NOUVEAU_SUJET`, pas `MIN/NOUVEAU_SUJET` si c'est du RH)
   - Les conventions de nommage ci-dessus

### Étape 4 — Validation du chemin (garde-fou)

- Le chemin cible **DOIT** commencer par `{working_dir}/docs/AURA/` ou `{working_dir}/docs/MIN/`
- Si le chemin ne respecte pas cette contrainte, **REFUSER** le classement : écrire `null` dans `classified_to` et consigner un message d'anomalie
- Ne **JAMAIS** créer de répertoire directement à la racine de `docs/`

---

## Table de correspondances thématiques

Référence pour l'étape 3 (fallback) :

| Thématique | Branche | Chemin type |
|---|---|---|
| RH (effectifs, promotions, recrutement, formation, CREP) | MIN | `MIN/RH/{sous-thème}` |
| Santé-sécurité au travail (SST, amiante, RPS, DUERP) | MIN | `MIN/RH/SST` |
| Finances ministérielles (budget, PLF, contrat gestion) | MIN | `MIN/FINANCES/{sous-thème}` |
| Exploitation (VH, matériel, flotte, CEI, astreintes) | MIN | `MIN/EXPLOITATION/{sous-thème}` |
| GT CEI, GT matériel | MIN | `MIN/TRANSVERSE/GT_MATERIEL_CEI` |
| DGITM, DMR, CODER, réseau DIR | MIN | `MIN/TRANSVERSE/{sous-thème}` |
| SAGT, Sagacité | MIN | `MIN/TRANSVERSE/SAGT` |
| Transition écologique, IRVE, décarbonation, BEGES | MIN | `MIN/TRANSVERSE/TRANSITION_ECOLOGIQUE` |
| CR CODIR | MIN | `MIN/ADMINISTRATIF/CR_CODIR` |
| Management, transformation, CCD | MIN | `MIN/TRANSVERSE/MANAGEMENT` |
| Calendriers de référence | MIN | `MIN/EXPLOITATION/CALENDRIERS` |
| Pilotage, indicateurs, contrat objectifs | MIN | `MIN/TRANSVERSE/INDICATEURS_DIR` |
| Affaires juridiques (litiges, conventions hors-3DS) | MIN | `MIN/TRANSVERSE/CONTENTIEUX` ou `MIN/TRANSVERSE/CONVENTIONS` |
| Informatique DREAL/DIRMC | MIN | `MIN/TRANSVERSE/INFORMATIQUE` |
| Dossier spécifique (RN122, pont, tunnel) | MIN | `MIN/TRANSVERSE/{NOM_DOSSIER}` |
| Finances 3DS (DAC, modernisation AURA) | AURA | `AURA/FINANCES/{sous-thème}` |
| COPIL/COTECH/COSTRAT 3DS | AURA | `AURA/TRANSVERSE/{instance}` |
| Territoire 07/15/43 dans contexte 3DS | AURA | `AURA/TERRITOIRE/{département}` |

---

## Format de stockage dans `_treatment.json`

L'agent `todo-processor` doit écrire le résultat du classement dans le champ `analysis.attachments[]` de `_treatment.json` :

```json
{
  "name": "document.pdf",
  "readable": true,
  "summary": "résumé du contenu",
  "classified_to": "docs/MIN/RH/PROMOTIONS"
}
```

En cas d'anomalie (étape 4 — chemin invalide ou branche indéterminée) :

```json
{
  "name": "document.pdf",
  "readable": true,
  "summary": "résumé du contenu",
  "classified_to": null,
  "classification_anomaly": "Impossible de déterminer la branche (AURA/MIN) pour ce document"
}
```
