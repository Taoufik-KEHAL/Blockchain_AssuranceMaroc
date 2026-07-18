"""
registre.chaine

Couche « on-chain » : structure de données du registre lui-même (Block,
Blockchain) et ses règles de validation (chaînage SHA-256 + consensus PoA).
Volontairement ignorante de Flask, du réseau et de l'identité du nœud qui
l'exécute (ORGANISME_ID, clé privée) - ce sont des préoccupations de la
couche nœud (registre.noeud), pas de la structure de données elle-même :
add_block()/check_chain_validity() reçoivent le registre des validateurs en
paramètre plutôt que de le lire dans une variable globale.

Classe Block reprise du tutoriel de référence (satwikkansal/python_blockchain_app,
branche ibm_blockchain_post) : chaînage SHA-256.
"""

import json
from hashlib import sha256

from . import consensus


class Block:
    def __init__(self, index, transactions, timestamp, previous_hash):
        self.index = index
        self.transactions = transactions
        self.timestamp = timestamp
        self.previous_hash = previous_hash
        # hash, validator_organisme, validator_signature ajoutés après
        # scellement - jamais présents au moment de compute_hash() (voir
        # Blockchain.add_block : ils dépendent du hash, donc ne peuvent pas
        # eux-mêmes faire partie du contenu haché).

    def compute_hash(self):
        block_string = json.dumps(self.__dict__, sort_keys=True)
        return sha256(block_string.encode()).hexdigest()


class Blockchain:
    def __init__(self, chain=None):
        self.unconfirmed_transactions = []
        self.chain = chain
        if self.chain is None:
            self.chain = []
            self.create_genesis_block()

    def create_genesis_block(self):
        genesis_block = Block(0, [], 0, "0")
        genesis_block.hash = genesis_block.compute_hash()
        self.chain.append(genesis_block)

    @property
    def last_block(self):
        return self.chain[-1]

    def add_block(self, block, block_hash, validator_organisme, validator_signature, registre_cles_publiques):
        """
        block ne doit PAS encore porter .hash/.validator_organisme/
        .validator_signature au moment de cet appel (voir Block.__init__) :
        ces 3 valeurs sont vérifiées comme arguments séparés, puis assignées
        au bloc seulement après succès de toutes les vérifications.
        """
        if self.last_block.hash != block.previous_hash:
            return False
        if block.compute_hash() != block_hash:
            return False
        if block.index != 0 and not consensus.is_valid_poa_block(
            block_hash, block.index, validator_organisme, validator_signature, registre_cles_publiques
        ):
            return False

        block.hash = block_hash
        block.validator_organisme = validator_organisme
        block.validator_signature = validator_signature
        self.chain.append(block)
        return True

    def add_new_transaction(self, transaction):
        self.unconfirmed_transactions.append(transaction)

    @classmethod
    def check_chain_validity(cls, chain, registre_cles_publiques):
        """
        Revalide toute la chaîne : chaînage SHA-256 + règles PoA (sauf pour
        le genesis). Contrairement à add_block(), ici les blocs portent déjà
        leurs attributs hash/validator_* (dump JSON complet d'une chaîne
        existante) - on les retire temporairement pour recalculer le hash du
        contenu seul, exactement comme add_block() le fait en ne les
        assignant jamais avant la vérification.
        """
        result = True
        previous_hash = "0"

        for block in chain:
            block_hash = block.hash
            validator_organisme = getattr(block, "validator_organisme", None)
            validator_signature = getattr(block, "validator_signature", None)

            delattr(block, "hash")
            if validator_organisme is not None:
                delattr(block, "validator_organisme")
            if validator_signature is not None:
                delattr(block, "validator_signature")

            recomputed_hash = block.compute_hash()

            block.hash = block_hash
            if validator_organisme is not None:
                block.validator_organisme = validator_organisme
            if validator_signature is not None:
                block.validator_signature = validator_signature

            if recomputed_hash != block_hash or previous_hash != block.previous_hash:
                result = False
                break

            if block.index != 0 and not consensus.is_valid_poa_block(
                block_hash, block.index, validator_organisme, validator_signature, registre_cles_publiques
            ):
                result = False
                break

            previous_hash = block_hash

        return result
