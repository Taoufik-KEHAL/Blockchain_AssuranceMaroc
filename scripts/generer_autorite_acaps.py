"""
scripts.generer_autorite_acaps

À exécuter UNE SEULE FOIS, uniquement sur la machine de l'ACAPS (autorité de
certification racine du réseau). Génère la paire de clés racine :
  - clé PRIVÉE  -> secrets/ACAPS.pem   (ne jamais distribuer ni committer)
  - clé PUBLIQUE -> cles_publiques/ACAPS.pem (à distribuer, hors ligne, à
    tous les organismes AVANT le premier démarrage de leur nœud — c'est
    cette clé qui sert de racine de confiance pour vérifier tous les
    certificats, voir registre.gouvernance)

Idempotent : ne régénère jamais une clé déjà existante.

Usage (depuis la racine du dépôt) :
    uv run python -m scripts.generer_autorite_acaps
"""

import os

from registre import chemins, identite

CLE_PRIVEE_ACAPS = os.path.join(chemins.SECRETS_DIR, "ACAPS.pem")
CLE_PUBLIQUE_ACAPS = os.path.join(chemins.CLES_PUBLIQUES_DIR, "ACAPS.pem")


def main():
    os.makedirs(chemins.SECRETS_DIR, exist_ok=True)
    os.makedirs(chemins.CLES_PUBLIQUES_DIR, exist_ok=True)

    if os.path.exists(CLE_PRIVEE_ACAPS):
        print(f"[ACAPS] Identité racine déjà existante : {CLE_PRIVEE_ACAPS}")
        return

    cle_privee, cle_publique = identite.generer_paire_cles()

    with open(CLE_PRIVEE_ACAPS, "wb") as f:
        f.write(identite.serialiser_cle_privee_pem(cle_privee))
    os.chmod(CLE_PRIVEE_ACAPS, 0o600)

    with open(CLE_PUBLIQUE_ACAPS, "wb") as f:
        f.write(identite.serialiser_cle_publique_pem(cle_publique))

    print("[ACAPS] Nouvelle identité racine générée.")
    print(f"[ACAPS]   Clé privée -> {CLE_PRIVEE_ACAPS} (ne JAMAIS distribuer)")
    print(f"[ACAPS]   Clé publique -> {CLE_PUBLIQUE_ACAPS} (à distribuer hors ligne à chaque organisme)")


if __name__ == "__main__":
    main()
