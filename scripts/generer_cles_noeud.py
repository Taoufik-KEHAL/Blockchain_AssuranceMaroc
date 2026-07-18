"""
scripts.generer_cles_noeud <ORGANISME>

À exécuter une fois par organisme membre du réseau (CNOPS, CNSS,
ASSUREUR_PRIVE), sur sa propre machine. Génère sa paire de clés :
  - clé PRIVÉE  -> secrets/<ORGANISME>.pem  (ne quitte jamais cette machine)
  - clé PUBLIQUE -> cles_publiques/<ORGANISME>.pem (à transmettre à l'ACAPS
    pour certification, via scripts.certifier_cle_organisme)

Usage (depuis la racine du dépôt) :
    uv run python -m scripts.generer_cles_noeud CNSS
"""

import argparse
import os

from registre import chemins, identite


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("organisme_id")
    args = parser.parse_args()
    organisme_id = args.organisme_id

    os.makedirs(chemins.SECRETS_DIR, exist_ok=True)
    os.makedirs(chemins.CLES_PUBLIQUES_DIR, exist_ok=True)

    cle_privee_path = os.path.join(chemins.SECRETS_DIR, f"{organisme_id}.pem")
    cle_publique_path = os.path.join(chemins.CLES_PUBLIQUES_DIR, f"{organisme_id}.pem")

    if os.path.exists(cle_privee_path):
        print(f"[{organisme_id}] Identité déjà existante : {cle_privee_path}")
        return

    cle_privee, cle_publique = identite.generer_paire_cles()

    with open(cle_privee_path, "wb") as f:
        f.write(identite.serialiser_cle_privee_pem(cle_privee))
    os.chmod(cle_privee_path, 0o600)

    with open(cle_publique_path, "wb") as f:
        f.write(identite.serialiser_cle_publique_pem(cle_publique))

    print(f"[{organisme_id}] Nouvelle identité générée.")
    print(f"[{organisme_id}]   Clé privée -> {cle_privee_path} (ne JAMAIS distribuer)")
    print(f"[{organisme_id}]   Clé publique -> {cle_publique_path} (à transmettre à l'ACAPS pour certification)")


if __name__ == "__main__":
    main()
