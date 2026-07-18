"""
registre.consensus

Mécanisme de consensus alternatif : remplace la preuve de travail du
tutoriel de référence par une Proof of Authority à tour de rôle entre les
organismes déjà certifiés par l'ACAPS (voir registre.gouvernance).

Justification (remplace la preuve de travail, jugée inadaptée à ce
contexte - voir rapport, limites) : le réseau est permissionné, à 3 nœuds
connus et déjà authentifiés hors ligne par une autorité de certification.
Calculer un nonce coûteux n'apporte ici aucune protection réelle contre une
menace crédible (contrairement à un réseau ouvert où n'importe qui pourrait
miner) - seule l'identité déjà établie par l'ACAPS importe. Le validateur
légitime pour le bloc d'indice n est désigné de façon déterministe (tour de
rôle, sans calcul), et scelle le bloc avec sa propre clé.

Contrairement au registre des validateurs du tutoriel PoA classique (souvent
lui-même inscrit sur la chaîne, ce qui pose un problème d'amorçage), le
registre des organismes certifiés ici (REGISTRE_CLES_PUBLIQUES) est chargé
une fois pour toutes depuis les fichiers cles_publiques/ au démarrage de
chaque nœud - identique sur tous les nœuds par construction (même autorité
de certification, mêmes fichiers distribués hors ligne), donc aucun
problème d'amorçage : le tour de rôle est calculable dès le premier bloc.
"""

from . import identite


def validateurs_actifs(registre_cles_publiques):
    """
    Liste triée (donc identique et déterministe sur tous les nœuds) des
    organismes certifiés éligibles à sceller un bloc.
    """
    return sorted(registre_cles_publiques.keys())


def validateur_attendu(index_bloc, registre_cles_publiques):
    """Organisme dont c'est le tour de sceller le bloc d'indice donné."""
    validateurs = validateurs_actifs(registre_cles_publiques)
    if not validateurs:
        raise RuntimeError("Aucun organisme certifié : impossible de désigner un validateur.")
    return validateurs[index_bloc % len(validateurs)]


def signer_bloc(cle_privee, block_hash, organisme_id):
    """Scelle un bloc déjà haché (block_hash) au nom de organisme_id."""
    message = "{}|{}".format(block_hash, organisme_id)
    return identite.signer(cle_privee, message)


def verifier_signature_bloc(block_hash, organisme_id, signature, registre_cles_publiques):
    cle_publique = registre_cles_publiques.get(organisme_id)
    if cle_publique is None:
        return False
    message = "{}|{}".format(block_hash, organisme_id)
    return identite.verifier(cle_publique, message, signature)


def is_valid_poa_block(block_hash, index_bloc, validator_organisme, validator_signature, registre_cles_publiques):
    """
    Vérifie les 3 règles de la PoA pour un bloc (indice != 0, le genesis en
    est exempté par l'appelant) : 1) le validateur annoncé a bien signé ce
    bloc, 2) c'était bien son tour, 3) implicitement, c'est un organisme
    certifié (sinon il n'aurait pas de clé dans le registre pour vérifier).
    """
    if not validator_organisme or not validator_signature:
        return False
    if validator_organisme != validateur_attendu(index_bloc, registre_cles_publiques):
        return False
    return verifier_signature_bloc(block_hash, validator_organisme, validator_signature, registre_cles_publiques)
