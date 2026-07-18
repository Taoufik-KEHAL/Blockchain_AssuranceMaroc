"""
registre.gouvernance

Mécanisme de certification minimal, inspiré du rôle d'une autorité de
certification (CA) dans une PKI classique. Un certificat n'est ici rien de
plus qu'une signature de l'ACAPS sur le couple (organisme_id, clé publique) :
suffisant pour empêcher qu'un acteur malveillant dépose une clé publique en
prétendant qu'elle appartient à un organisme membre (voir rapport, section 5.3).

Le problème du bootstrap de confiance n'est pas résolu ici : la clé publique
de l'ACAPS elle-même doit être distribuée hors ligne à chaque nœud avant son
premier démarrage (limite documentée, pas une lacune de ce module).
"""

from . import identite


def _message_certificat(organisme_id, cle_publique_pem_bytes):
    return "{}|{}".format(organisme_id, cle_publique_pem_bytes.decode("utf-8"))


def certifier_cle_publique(organisme_id, cle_publique_pem_bytes, cle_privee_acaps):
    """
    Signe le couple (organisme_id, clé publique) avec la clé privée de
    l'ACAPS. Retourne le certificat (signature hexadécimale).
    """
    message = _message_certificat(organisme_id, cle_publique_pem_bytes)
    return identite.signer(cle_privee_acaps, message)


def verifier_certificat(organisme_id, cle_publique_pem_bytes, certificat_hex, cle_publique_acaps):
    """
    Vérifie qu'un certificat est une signature ACAPS valide du couple
    (organisme_id, clé publique). Ne lève jamais d'exception.
    """
    message = _message_certificat(organisme_id, cle_publique_pem_bytes)
    return identite.verifier(cle_publique_acaps, message, certificat_hex)
