"""
registre.web

Couche interface web : un formulaire de déclaration de sinistre et un
journal d'audit, par organisme. Chaque organisme lance sa propre instance,
connectée exclusivement à son propre nœud (registre.noeud) via la variable
d'environnement NODE_ADDRESS - jamais directement à registre.chaine : le
nœud reste le seul point d'entrée réseau (voir registre.web.vues).
"""

from flask import Flask

app = Flask(__name__)
app.secret_key = "cle-de-session-demo-academique"

from . import vues  # noqa: E402,F401
