"""
lancer_noeud.py <port>

Lance le nœud de l'organisme désigné par la variable d'environnement
ORGANISME_ID sur le port donné.

Usage :
    ORGANISME_ID=CNSS python lancer_noeud.py 8001
"""

import sys

from registre import noeud

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    noeud.app.run(port=port)
