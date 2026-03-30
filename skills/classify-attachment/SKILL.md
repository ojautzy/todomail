# Skill : classify-attachment

> **Version :** 1.0.0
> **Description :** Determine le chemin de classement d'une piece jointe dans docs/ en respectant la structure canonique AURA/MIN
> **Declencheur :** Appele par todo-processor lors du classement des pieces jointes

---

## Structure canonique de docs/

Le repertoire `docs/` repose sur deux branches exclusives :

- **`docs/AURA/`** : documents lies a l'experimentation 3DS avec la Region Auvergne-Rhone-Alpes (mise a disposition, conventions 3DS, finances 3DS, COPIL/COTECH/COSTRAT AURA, territoires experimentes 07/15/43)
- **`docs/MIN/`** : documents lies a l'activite ministerielle traditionnelle de la DIR (RH, finances ministerielles, exploitation, transverse, communication, territoires hors-3DS, etc.)

**Regle absolue :** aucun repertoire ni fichier ne doit exister directement a la racine de `docs/` en dehors de ces deux branches (et `.gitkeep`).

---

## Conventions de nommage des repertoires

- Noms en **MAJUSCULES** et **underscores** uniquement
- **Pas de tirets**, pas de casse mixte, pas d'accents
- Exception : sous-repertoires territoriaux avec numeros de departement (07, 12, 15, 34, 43, 48, 63)

| Exemple valide | Exemple INVALIDE |
|---|---|
| `MIN/RH/PROMOTIONS` | `RH-Travail` |
| `AURA/FINANCES/DAC` | `Transition-Ecologique` |
| `MIN/TRANSVERSE/SAGT` | `dossiers/GT-Pilote-DIR` |

---

## Algorithme de classement

Pour classer une piece jointe, suivre ces etapes dans l'ordre :

### Etape 1 — Determiner la branche racine (OBLIGATOIRE)

- **`AURA/`** si le document concerne la mise a disposition aupres de la Region AURA : experimentation 3DS, finances 3DS, conventions 3DS, COPIL/COTECH/COSTRAT 3DS, territoire experimente 07/15/43 dans contexte 3DS
- **`MIN/`** pour tout le reste : activite ministerielle traditionnelle (RH, finances, exploitation, transverse, communication, territoires hors-3DS, etc.)

### Etape 2 — Rechercher le sous-repertoire cible via RAG

1. Appeler `search_doc` (MCP) pour rechercher des documents similaires dans la base documentaire
2. **Filtrer** : ne retenir que les resultats dont le chemin commence par `docs/{branche}/` (la branche determinee en etape 1)
3. Le sous-repertoire cible est celui du resultat le plus pertinent dans la bonne branche

### Etape 3 — Fallback si aucun resultat pertinent dans la bonne branche

1. Lister les sous-repertoires existants de `docs/{branche}/` (profondeur 2) avec `ls`
2. Choisir le sous-repertoire le plus thematiquement proche en s'appuyant sur la table de correspondances ci-dessous
3. Si necessaire, creer un nouveau sous-repertoire **DANS** la branche appropriee en respectant :
   - La hierarchie existante (ex: `MIN/RH/NOUVEAU_SUJET`, pas `MIN/NOUVEAU_SUJET` si c'est du RH)
   - Les conventions de nommage ci-dessus

### Etape 4 — Validation du chemin (garde-fou)

- Le chemin cible **DOIT** commencer par `{working_dir}/docs/AURA/` ou `{working_dir}/docs/MIN/`
- Si le chemin ne respecte pas cette contrainte, **REFUSER** le classement et retourner `null` avec un message d'anomalie
- Ne **JAMAIS** creer de repertoire directement a la racine de `docs/`

---

## Table de correspondances thematiques

Reference pour l'etape 3 (fallback) :

| Thematique | Branche | Chemin type |
|---|---|---|
| RH (effectifs, promotions, recrutement, formation, CREP) | MIN | `MIN/RH/{sous-theme}` |
| Sante-securite au travail (SST, amiante, RPS, DUERP) | MIN | `MIN/RH/SST` |
| Finances ministerielles (budget, PLF, contrat gestion) | MIN | `MIN/FINANCES/{sous-theme}` |
| Exploitation (VH, materiel, flotte, CEI, astreintes) | MIN | `MIN/EXPLOITATION/{sous-theme}` |
| GT CEI, GT materiel | MIN | `MIN/TRANSVERSE/GT_MATERIEL_CEI` |
| DGITM, DMR, CODER, reseau DIR | MIN | `MIN/TRANSVERSE/{sous-theme}` |
| SAGT, Sagacite | MIN | `MIN/TRANSVERSE/SAGT` |
| Transition ecologique, IRVE, decarbonation, BEGES | MIN | `MIN/TRANSVERSE/TRANSITION_ECOLOGIQUE` |
| CR CODIR | MIN | `MIN/ADMINISTRATIF/CR_CODIR` |
| Management, transformation, CCD | MIN | `MIN/TRANSVERSE/MANAGEMENT` |
| Calendriers de reference | MIN | `MIN/EXPLOITATION/CALENDRIERS` |
| Pilotage, indicateurs, contrat objectifs | MIN | `MIN/TRANSVERSE/INDICATEURS_DIR` |
| Affaires juridiques (litiges, conventions hors-3DS) | MIN | `MIN/TRANSVERSE/CONTENTIEUX` ou `MIN/TRANSVERSE/CONVENTIONS` |
| Informatique DREAL/DIRMC | MIN | `MIN/TRANSVERSE/INFORMATIQUE` |
| Dossier specifique (RN122, pont, tunnel) | MIN | `MIN/TRANSVERSE/{NOM_DOSSIER}` |
| Finances 3DS (DAC, modernisation AURA) | AURA | `AURA/FINANCES/{sous-theme}` |
| COPIL/COTECH/COSTRAT 3DS | AURA | `AURA/TRANSVERSE/{instance}` |
| Territoire 07/15/43 dans contexte 3DS | AURA | `AURA/TERRITOIRE/{departement}` |

---

## Sortie attendue

Le skill retourne pour chaque piece jointe :

```json
{
  "classified_to": "docs/MIN/RH/PROMOTIONS",
  "anomaly": null
}
```

Ou en cas d'anomalie :

```json
{
  "classified_to": null,
  "anomaly": "Impossible de determiner la branche (AURA/MIN) pour ce document"
}
```
