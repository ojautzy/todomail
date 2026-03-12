---
name: read-odf
description: >
  Extraction de texte depuis les fichiers OpenDocument (.odt, .ods, .odp).
  Ce skill fournit un script Python qui extrait le contenu texte des pièces
  jointes au format OpenDocument. Il est utilisé automatiquement par les
  autres skills lorsqu'ils rencontrent des fichiers ODF qu'ils ne peuvent
  pas lire directement.
version: 1.1.0
---

# Lecture des fichiers OpenDocument

Ce skill n'a pas de commande dédiée. Il est utilisé comme référence par les autres skills du plugin lorsqu'ils rencontrent des fichiers OpenDocument (.odt, .ods, .odp) que Claude ne peut pas lire nativement.

## Quand utiliser ce skill

Lorsqu'un fichier avec l'extension `.odt`, `.ods` ou `.odp` doit être lu (pièce jointe d'un mail, document de la base documentaire), utiliser le script Python fourni pour en extraire le contenu texte.

Les cas typiques :
- **agent `mail-analyzer`** : lecture des pièces jointes ODF pour analyser un mail et produire les synthèses dans `_analysis.json`
- **process-todo** : lecture des pièces jointes pour produire des projets d'arbitrage, des synthèses détaillées ou des livrables

## Comment utiliser le script

Invoquer via Bash :

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/read-odf/scripts/read_odf.py" "<chemin_du_fichier>"
```

Le texte extrait est affiché sur stdout. Les erreurs sont affichées sur stderr.

## Formats de sortie

**`.odt` (document texte) :** titres et paragraphes, un par ligne.

**`.ods` (tableur) :** structuré par feuille avec cellules séparées par `|` :
```
[Feuille1]
cellule1 | cellule2 | cellule3
cellule4 | cellule5 | cellule6
[Feuille2]
...
```

**`.odp` (présentation) :** structuré par diapositive :
```
--- Diapositive 1 ---
Titre de la diapositive
Contenu texte
--- Diapositive 2 ---
...
```

## Gestion des erreurs

| Code de sortie | Signification |
|----------------|---------------|
| 0 | Extraction réussie |
| 1 | Fichier introuvable ou extension non supportée |
| 2 | Bibliothèque `odfpy` non installée |
| 3 | Fichier corrompu ou illisible |

Si le code de sortie est 2, installer la dépendance puis relancer :

```bash
pip install odfpy
```

## Dépendance

Le script nécessite la bibliothèque Python `odfpy` (déclarée dans `requirements.txt`). L'installer avec `pip install odfpy` si elle est absente.
