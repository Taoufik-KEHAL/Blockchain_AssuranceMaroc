"""
registre.identite

Couche de signature : génération, signature et vérification ECDSA
(SECP256K1 — la même courbe que Bitcoin, choix thématique plutôt que
fonctionnel) pour les nœuds du réseau inter-assurances. Utilise la
bibliothèque `cryptography` plutôt que `ecdsa` : les signatures produites
sont au format DER standard (comme illustré section 5.1.2 du rapport
technique), pas le format brut r||s.

Chaque nœud (un organisme) possède sa propre paire de clés, chargée depuis
secrets/<ORGANISME>.pem (privée, jamais partagée) au démarrage de
registre.noeud.
"""

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature

COURBE = ec.SECP256K1()


def generer_paire_cles():
    """Retourne (cle_privee, cle_publique), objets cryptography."""
    cle_privee = ec.generate_private_key(COURBE)
    return cle_privee, cle_privee.public_key()


def signer(cle_privee, message):
    """Signe `message` (str) avec `cle_privee`. Retourne la signature en hexadécimal (DER)."""
    signature = cle_privee.sign(message.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    return signature.hex()


def verifier(cle_publique, message, signature_hex):
    """
    Vérifie que `signature_hex` est une signature ECDSA valide de `message`
    pour `cle_publique`. Ne lève jamais d'exception : retourne False pour
    toute signature absente, malformée ou invalide.
    """
    if not signature_hex:
        return False
    try:
        signature = bytes.fromhex(signature_hex)
        cle_publique.verify(signature, message.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError):
        return False


def serialiser_cle_publique_pem(cle_publique):
    return cle_publique.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def serialiser_cle_privee_pem(cle_privee):
    return cle_privee.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def charger_cle_privee_pem(chemin):
    with open(chemin, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def charger_cle_publique_pem(chemin):
    with open(chemin, "rb") as f:
        return serialization.load_pem_public_key(f.read())
