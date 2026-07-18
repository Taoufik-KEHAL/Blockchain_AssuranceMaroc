"""
registre.hachage

Couche de hachage : transforme les données brutes d'un sinistre
(identifiant assuré, code d'acte, date) en une empreinte SHA-256 à sens
unique, avant toute transmission au réseau inter-assurances. Ni
l'identifiant assuré ni le code d'acte ne quittent jamais l'organisme
émetteur : seule cette empreinte de 64 caractères hexadécimaux circule sur
la chaîne (voir registre.noeud).
"""

import hashlib

SEPARATEUR = "|"


def hash_sinistre(identifiant_assure, code_acte, date_acte, sel=""):
    champs = SEPARATEUR.join([
        str(identifiant_assure), str(code_acte), str(date_acte),
    ])
    donnee = "{}{}".format(sel, champs).encode("utf-8")
    return hashlib.sha256(donnee).hexdigest()
