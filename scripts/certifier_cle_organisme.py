"""
scripts.certifier_cle_organisme <ORGANISME>

À exécuter UNIQUEMENT par l'ACAPS (nécessite secrets/ACAPS.pem). Lit la clé
publique de l'organisme (déjà transmise hors ligne, cles_publiques/<ORGANISME>.pem)
et produit son certificat : cles_publiques/<ORGANISME>.cert

Le couple (<ORGANISME>.pem, <ORGANISME>.cert) est ensuite distribué à tous
les nœuds du réseau — chaque nœud vérifie ce certificat avec la clé publique
racine de l'ACAPS avant d'accepter la clé (voir registre.noeud,
charger_registre_cles_publiques).

Usage (depuis la racine du dépôt) :
    uv run python -m scripts.certifier_cle_organisme CNSS
"""

import argparse
import os

from registre import chemins, identite, gouvernance

CLE_PRIVEE_ACAPS = os.path.join(chemins.SECRETS_DIR, "ACAPS.pem")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("organisme_id")
    args = parser.parse_args()
    organisme_id = args.organisme_id

    if not os.path.exists(CLE_PRIVEE_ACAPS):
        raise RuntimeError(
            f"{CLE_PRIVEE_ACAPS} introuvable. Ce script ne peut être exécuté "
            "que sur la machine de l'ACAPS, après scripts.generer_autorite_acaps."
        )

    cle_publique_path = os.path.join(chemins.CLES_PUBLIQUES_DIR, f"{organisme_id}.pem")
    if not os.path.exists(cle_publique_path):
        raise RuntimeError(
            f"{cle_publique_path} introuvable. L'organisme doit d'abord "
            "exécuter scripts.generer_cles_noeud et transmettre sa clé publique."
        )

    cle_privee_acaps = identite.charger_cle_privee_pem(CLE_PRIVEE_ACAPS)
    with open(cle_publique_path, "rb") as f:
        cle_publique_pem_bytes = f.read()

    certificat = gouvernance.certifier_cle_publique(organisme_id, cle_publique_pem_bytes, cle_privee_acaps)

    certificat_path = os.path.join(chemins.CLES_PUBLIQUES_DIR, f"{organisme_id}.cert")
    with open(certificat_path, "w") as f:
        f.write(certificat)

    print(f"[ACAPS] Certificat émis pour {organisme_id} -> {certificat_path}")
    print(f"[ACAPS] Distribuer {cle_publique_path} + {certificat_path} à tous les nœuds du réseau.")


if __name__ == "__main__":
    main()
