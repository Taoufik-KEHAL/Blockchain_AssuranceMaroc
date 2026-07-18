"""
run_app.py

Lance l'interface web d'un organisme, connectée à son propre nœud via la
variable d'environnement NODE_ADDRESS.

Usage :
    NODE_ADDRESS=http://127.0.0.1:8001 APP_PORT=5001 python run_app.py
"""

import os

from registre.web import app

if __name__ == "__main__":
    port = int(os.environ.get("APP_PORT", 5000))
    app.run(port=port)
