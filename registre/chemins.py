"""
registre.chemins

Emplacements partagés par tout le projet (nœud, scripts de gouvernance,
tests) : racine du dépôt et dossiers de clés. Centralisé ici pour que
chaque module n'ait pas à recalculer son propre chemin relatif.
"""

import os

RACINE_PROJET = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS_DIR = os.path.join(RACINE_PROJET, "secrets")
CLES_PUBLIQUES_DIR = os.path.join(RACINE_PROJET, "cles_publiques")
