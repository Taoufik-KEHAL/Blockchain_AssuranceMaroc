"""
registre.noeud

Couche réseau/API : nœud Flask du registre. Chaque nœud représente UN
organisme (CNOPS, CNSS, ASSUREUR_PRIVE) : il possède sa propre identité
cryptographique (secrets/<ORGANISME_ID>.pem) et signe, en son propre nom,
chaque transaction qu'il accepte dans son pool. Contrairement à un système
où chaque utilisateur signerait ses propres transactions, ici c'est
toujours le NŒUD qui signe - le client (l'interface web) ne transmet jamais
que l'empreinte hash_sinistre (voir registre.web.vues).

S'appuie sur registre.chaine pour la structure de données du registre
(Block, Blockchain) et registre.consensus pour la Proof of Authority :
cette couche ne connaît que le "qui suis-je sur ce réseau" (ORGANISME_ID,
ma clé privée, le registre des clés certifiées) et l'expose via une API
REST - la validation des règles elles-mêmes vit dans les couches inférieures.
"""

import os
import re
import threading
import json
import time

from flask import Flask, request
import requests

from . import chemins, identite, gouvernance
from . import consensus as poa
from .chaine import Block, Blockchain

SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


ORGANISME_ID = os.environ.get("ORGANISME_ID")
if not ORGANISME_ID:
    raise RuntimeError(
        "La variable d'environnement ORGANISME_ID est requise (ex: ORGANISME_ID=CNSS)."
    )

_cle_privee_path = os.path.join(chemins.SECRETS_DIR, f"{ORGANISME_ID}.pem")
if not os.path.exists(_cle_privee_path):
    raise RuntimeError(
        f"{_cle_privee_path} introuvable. Exécuter d'abord "
        f"`python -m scripts.generer_cles_noeud {ORGANISME_ID}`."
    )
CLE_PRIVEE_NOEUD = identite.charger_cle_privee_pem(_cle_privee_path)


def charger_registre_cles_publiques():
    """
    Charge toutes les clés publiques présentes dans cles_publiques/, mais
    n'accepte QUE celles accompagnées d'un certificat ACAPS valide - toute
    clé sans certificat (ou avec un certificat falsifié) est ignorée, avec
    un avertissement journalisé, plutôt que d'être acceptée par défaut.

    Ce registre sert aussi de liste des validateurs éligibles pour la Proof
    of Authority (registre.consensus) : identique sur tous les nœuds par
    construction (même autorité, mêmes fichiers distribués hors ligne).
    """
    registre = {}

    cle_publique_acaps_path = os.path.join(chemins.CLES_PUBLIQUES_DIR, "ACAPS.pem")
    if not os.path.exists(cle_publique_acaps_path):
        raise RuntimeError(
            f"{cle_publique_acaps_path} introuvable. La clé publique racine de "
            "l'ACAPS doit être distribuée hors ligne à ce nœud avant son démarrage."
        )
    cle_publique_acaps = identite.charger_cle_publique_pem(cle_publique_acaps_path)

    for nom_fichier in sorted(os.listdir(chemins.CLES_PUBLIQUES_DIR)):
        if not nom_fichier.endswith(".pem") or nom_fichier == "ACAPS.pem":
            continue
        organisme_id = nom_fichier[: -len(".pem")]

        with open(os.path.join(chemins.CLES_PUBLIQUES_DIR, nom_fichier), "rb") as f:
            cle_publique_pem_bytes = f.read()

        certificat_path = os.path.join(chemins.CLES_PUBLIQUES_DIR, f"{organisme_id}.cert")
        if not os.path.exists(certificat_path):
            print(f"[registre] cle publique de {organisme_id} ignoree (aucun certificat ACAPS trouve)")
            continue

        with open(certificat_path) as f:
            certificat = f.read().strip()

        if not gouvernance.verifier_certificat(organisme_id, cle_publique_pem_bytes, certificat, cle_publique_acaps):
            print(f"[registre] cle publique de {organisme_id} ignoree (certificat ACAPS invalide)")
            continue

        registre[organisme_id] = identite.charger_cle_publique_pem(
            os.path.join(chemins.CLES_PUBLIQUES_DIR, nom_fichier)
        )

    return registre


REGISTRE_CLES_PUBLIQUES = charger_registre_cles_publiques()
if ORGANISME_ID not in REGISTRE_CLES_PUBLIQUES:
    print(f"[registre] avertissement : {ORGANISME_ID} n'a pas de certificat ACAPS valide dans son propre registre")


app = Flask(__name__)
blockchain = Blockchain()
peers = set()


def chercher_organisme_pour_doublon(hash_sinistre, transactions_du_bloc_courant=None, verifier_pool=True):
    """
    Recherche une empreinte identique déjà présente dans le pool en attente,
    dans la chaîne confirmée, ou (pour un bloc en cours de validation) parmi
    les transactions déjà traitées de ce même bloc. Retourne l'organisme
    émetteur déjà associé à cette empreinte, ou None si aucun doublon.

    verifier_pool=False lors de la validation d'un bloc reçu d'un pair
    (/add_block) : notre propre pool peut légitimement contenir une copie de
    la même transaction (reçue par diffusion, voir announce_pending_transaction) -
    ce n'est pas un doublon frauduleux, seule la chaîne CONFIRMÉE fait foi à
    ce moment-là. Le pool est purgé de cette entrée juste après (voir
    verify_and_add_block).
    """
    if verifier_pool:
        for transaction in blockchain.unconfirmed_transactions:
            if transaction.get("hash_sinistre") == hash_sinistre:
                return transaction.get("organisme_emetteur")

    for block in blockchain.chain:
        for transaction in block.transactions:
            if transaction.get("hash_sinistre") == hash_sinistre:
                return transaction.get("organisme_emetteur")

    if transactions_du_bloc_courant:
        for transaction in transactions_du_bloc_courant:
            if transaction.get("hash_sinistre") == hash_sinistre:
                return transaction.get("organisme_emetteur")

    return None


def is_valid_sinistre_transaction(tx_data):
    """Valide la présence et le format des champs fournis par le client. Retourne (bool, message)."""
    hash_sinistre = tx_data.get("hash_sinistre")
    if not hash_sinistre or not isinstance(hash_sinistre, str) or not SHA256_HEX_RE.match(hash_sinistre):
        return False, "Champ 'hash_sinistre' manquant ou mal formé (attendu : 64 caractères hexadécimaux)"

    organisme_emetteur = tx_data.get("organisme_emetteur")
    if not organisme_emetteur or not isinstance(organisme_emetteur, str):
        return False, "Champ 'organisme_emetteur' manquant ou mal formé"

    return True, None


def is_valid_signature(tx_data):
    """Vérifie la signature avec la clé publique certifiée de l'organisme émetteur. Retourne (bool, message)."""
    organisme_emetteur = tx_data.get("organisme_emetteur")
    cle_publique = REGISTRE_CLES_PUBLIQUES.get(organisme_emetteur)
    if cle_publique is None:
        return False, f"Signature invalide pour l'organisme {organisme_emetteur}"

    message = "{}|{}".format(tx_data.get("hash_sinistre"), organisme_emetteur)
    if not identite.verifier(cle_publique, message, tx_data.get("signature")):
        return False, f"Signature invalide pour l'organisme {organisme_emetteur}"

    return True, None


@app.route('/new_transaction', methods=['POST'])
def new_transaction():
    tx_data = request.get_json()
    if not tx_data:
        return "Corps de requête invalide", 400

    hash_sinistre = tx_data.get("hash_sinistre")
    if not hash_sinistre or not isinstance(hash_sinistre, str) or not SHA256_HEX_RE.match(hash_sinistre):
        return "Champ 'hash_sinistre' manquant ou mal formé (attendu : 64 caractères hexadécimaux)", 400

    organisme_existant = chercher_organisme_pour_doublon(hash_sinistre)
    if organisme_existant is not None:
        return f"Sinistre deja enregistre par l'organisme : {organisme_existant}", 409

    message = "{}|{}".format(hash_sinistre, ORGANISME_ID)
    signature = identite.signer(CLE_PRIVEE_NOEUD, message)

    transaction = {
        "hash_sinistre": hash_sinistre,
        "organisme_emetteur": ORGANISME_ID,
        "signature": signature,
        "timestamp": time.time(),
    }
    blockchain.add_new_transaction(transaction)
    announce_pending_transaction(transaction)

    return "Success", 201


@app.route('/receive_pending_transaction', methods=['POST'])
def receive_pending_transaction():
    """
    Reçoit d'un pair une transaction déjà entièrement formée (déjà signée
    par son organisme d'origine - jamais re-signée par ce nœud, contrairement
    à /new_transaction) : diffusion immédiate du pool en attente entre pairs,
    pour réduire la fenêtre entre soumission et scellement pendant laquelle
    un même sinistre pourrait être accepté en parallèle par deux organismes
    n'ayant pas encore vu le pool de l'autre.
    """
    tx = request.get_json()
    if not tx:
        return "Corps de requête invalide", 400

    ok, message = is_valid_sinistre_transaction(tx)
    if not ok:
        return message, 400

    ok, message = is_valid_signature(tx)
    if not ok:
        return message, 400

    organisme_existant = chercher_organisme_pour_doublon(tx["hash_sinistre"])
    if organisme_existant is not None:
        return f"Sinistre deja enregistre par l'organisme : {organisme_existant}", 409

    blockchain.add_new_transaction(tx)
    return "Success", 201


def announce_pending_transaction(transaction):
    """
    Diffusion à un seul saut vers les pairs directement enregistrés (comme
    announce_new_block) : suffisant pour la topologie à maillage complet du
    rapport (3 nœuds), pas une diffusion multi-sauts façon gossip complet.
    Best-effort : un pair injoignable ne bloque pas l'acceptation locale, il
    recevra quand même la transaction confirmée lors du prochain bloc.
    """
    for peer in peers:
        try:
            requests.post("{}receive_pending_transaction".format(peer),
                          json=transaction, timeout=2)
        except requests.RequestException:
            pass


def _block_from_dict(block_data):
    """
    NE PAS assigner block.hash/.validator_organisme/.validator_signature ici :
    add_block() ne les affecte qu'après avoir validé le hash et la PoA sur un
    bloc "propre" (compute_hash() ne doit jamais inclure ces 3 champs, qui en
    dépendent). Le hash et le scellement PoA sont extraits séparément par
    l'appelant et passés en arguments à add_block().
    """
    return Block(block_data["index"],
                block_data["transactions"],
                block_data["timestamp"],
                block_data["previous_hash"])


def create_chain_from_dump(chain_dump):
    generated_blockchain = Blockchain()
    for idx, block_data in enumerate(chain_dump):
        if idx == 0:
            continue  # skip genesis block
        block = _block_from_dict(block_data)
        added = generated_blockchain.add_block(
            block, block_data["hash"],
            block_data.get("validator_organisme"), block_data.get("validator_signature"),
            REGISTRE_CLES_PUBLIQUES,
        )
        if not added:
            raise ValueError("The chain dump is tampered!!")
    return generated_blockchain


@app.route('/chain', methods=['GET'])
def get_chain():
    chain_data = []
    for block in blockchain.chain:
        chain_data.append(block.__dict__)
    return json.dumps({"length": len(chain_data),
                       "chain": chain_data,
                       "peers": list(peers)})


def _sceller_bloc_si_notre_tour():
    """
    S'il y a des transactions en attente ET que c'est le tour de CE nœud
    (ORGANISME_ID, désigné par registre.consensus.validateur_attendu) de
    sceller le prochain bloc, le construit, le signe et l'ajoute à la
    chaîne. Retourne l'index du bloc scellé, ou None sinon (rien en
    attente, ou pas notre tour - pas une erreur, juste "rien à faire
    maintenant"). Décision propre à CE nœud (identité, clé privée) : c'est
    pour cela qu'elle vit ici plutôt que dans registre.chaine.Blockchain,
    qui ne connaît volontairement pas ORGANISME_ID.
    """
    if not blockchain.unconfirmed_transactions:
        return None

    last_block = blockchain.last_block
    new_index = last_block.index + 1

    attendu = poa.validateur_attendu(new_index, REGISTRE_CLES_PUBLIQUES)
    if attendu != ORGANISME_ID:
        return None

    new_block = Block(index=new_index,
                      transactions=blockchain.unconfirmed_transactions,
                      timestamp=time.time(),
                      previous_hash=last_block.hash)
    block_hash = new_block.compute_hash()
    signature = poa.signer_bloc(CLE_PRIVEE_NOEUD, block_hash, ORGANISME_ID)

    added = blockchain.add_block(new_block, block_hash, ORGANISME_ID, signature, REGISTRE_CLES_PUBLIQUES)
    if not added:
        return None

    blockchain.unconfirmed_transactions = []
    return new_block.index


def sceller_et_propager():
    """
    Cœur du scellement, partagé entre l'endpoint manuel /mine et la boucle
    automatique en arrière-plan (voir _boucle_scellement_automatique) :
    scelle les transactions en attente si c'est notre tour, puis propage le
    bloc aux pairs. Retourne l'index du bloc scellé, ou None si rien n'a été
    scellé (pool vide, ou pas notre tour).
    """
    result = _sceller_bloc_si_notre_tour()
    if not result:
        return None

    chain_length = len(blockchain.chain)
    consensus()
    if chain_length == len(blockchain.chain):
        announce_new_block(blockchain.last_block)
    return blockchain.last_block.index


@app.route('/mine', methods=['GET'])
def mine_unconfirmed_transactions():
    """
    Nom conservé (« /mine ») par continuité avec le tutoriel de référence,
    mais il n'y a plus de calcul de preuve de travail derrière : ce endpoint
    tente un scellement immédiat (seulement si c'est le tour de CE nœud),
    plutôt que d'attendre le prochain passage de la boucle automatique -
    reste utile pour une démonstration, mais n'est plus nécessaire en
    fonctionnement normal (voir SCELLEMENT_AUTO).
    """
    index = sceller_et_propager()
    if index is None:
        return "Aucune transaction en attente à sceller (ou ce n'est pas notre tour)."
    return "Bloc #{} scellé.".format(index)


SCELLEMENT_AUTO = os.environ.get("SCELLEMENT_AUTO", os.environ.get("MINAGE_AUTO", "1")) != "0"
SCELLEMENT_INTERVALLE_SECONDES = float(os.environ.get("SCELLEMENT_INTERVALLE_SECONDES", "3"))


def _boucle_scellement_automatique():
    """
    Avec la diffusion immédiate des transactions en attente entre pairs
    (announce_pending_transaction) et un consensus qui ne coûte plus rien à
    calculer (PoA), attendre un clic manuel sur /mine n'a plus de sens :
    chaque nœud vérifie, à intervalle régulier, si c'est son tour et scelle
    automatiquement s'il y a quelque chose en attente. Désactivable
    (SCELLEMENT_AUTO=0) - utilisé par les scripts de test pour un
    comportement déterministe.
    """
    while True:
        time.sleep(SCELLEMENT_INTERVALLE_SECONDES)
        try:
            sceller_et_propager()
        except Exception as e:
            print(f"[scellement-auto] erreur ignorée : {e}")


if SCELLEMENT_AUTO:
    threading.Thread(target=_boucle_scellement_automatique, daemon=True).start()


def _signer_annonce_maillage(node_address):
    """Preuve de possession de la clé certifiée de CE nœud sur l'adresse annoncée."""
    message = "{}|{}".format(node_address, ORGANISME_ID)
    return identite.signer(CLE_PRIVEE_NOEUD, message)


def _verifier_annonce_maillage(node_address, organisme_id, signature):
    cle_publique = REGISTRE_CLES_PUBLIQUES.get(organisme_id)
    if cle_publique is None:
        return False
    message = "{}|{}".format(node_address, organisme_id)
    return identite.verifier(cle_publique, message, signature)


@app.route('/register_node', methods=['POST'])
def register_new_peers():
    """
    Réseau permissionné : le maillage n'est pas ouvert à n'importe quelle
    adresse (contrairement au tutoriel de référence) - seul un organisme
    déjà certifié par l'ACAPS peut s'annoncer comme pair, en prouvant la
    possession de sa clé certifiée (signature de sa propre adresse), même
    convention que pour signer une transaction ou sceller un bloc.
    """
    data = request.get_json() or {}
    node_address = data.get("node_address")
    organisme_id = data.get("organisme_id")
    signature = data.get("signature")

    if not node_address or not organisme_id or not signature:
        return "Données de maillage invalides (node_address, organisme_id, signature requis)", 400

    if organisme_id not in REGISTRE_CLES_PUBLIQUES:
        return f"Organisme '{organisme_id}' non certifié par l'ACAPS : maillage refusé", 403

    if not _verifier_annonce_maillage(node_address, organisme_id, signature):
        return f"Signature de maillage invalide pour l'organisme {organisme_id}", 401

    peers.add(node_address)
    return get_chain()


@app.route('/register_with', methods=['POST'])
def register_with_existing_node():
    node_address = request.get_json()["node_address"]
    if not node_address:
        return "Invalid data", 400

    data = {
        "node_address": request.host_url,
        "organisme_id": ORGANISME_ID,
        "signature": _signer_annonce_maillage(request.host_url),
    }
    headers = {'Content-Type': "application/json"}

    response = requests.post(node_address + "/register_node",
                             data=json.dumps(data), headers=headers)

    if response.status_code == 200:
        global blockchain
        global peers
        chain_dump = response.json()['chain']
        blockchain = create_chain_from_dump(chain_dump)
        peers.update(response.json()['peers'])
        return "Registration successful", 200
    else:
        return response.content, response.status_code


@app.route('/add_block', methods=['POST'])
def verify_and_add_block():
    block_data = request.get_json()
    block = _block_from_dict(block_data)
    block_hash = block_data["hash"]
    validator_organisme = block_data.get("validator_organisme")
    validator_signature = block_data.get("validator_signature")

    transactions_deja_validees = []
    for tx in block.transactions:
        ok, message = is_valid_sinistre_transaction(tx)
        if not ok:
            return f"The block was discarded by the node: {message}", 400

        ok, message = is_valid_signature(tx)
        if not ok:
            return f"The block was discarded by the node: {message}", 400

        organisme_existant = chercher_organisme_pour_doublon(
            tx["hash_sinistre"], transactions_du_bloc_courant=transactions_deja_validees, verifier_pool=False
        )
        if organisme_existant is not None:
            return (f"The block was discarded by the node: Sinistre deja enregistre "
                    f"par l'organisme : {organisme_existant}"), 400
        transactions_deja_validees.append(tx)

    added = blockchain.add_block(block, block_hash, validator_organisme, validator_signature, REGISTRE_CLES_PUBLIQUES)
    if not added:
        return "The block was discarded by the node: chainage ou consensus (PoA) invalide", 400

    # Purge du pool local les transactions désormais confirmées par ce bloc
    # (reçues plus tôt par diffusion depuis announce_pending_transaction) :
    # elles ne sont plus "en attente", et les laisser dans le pool les ferait
    # inclure une seconde fois (déjà-confirmées) dans le prochain bloc scellé.
    hashes_confirmes = {tx["hash_sinistre"] for tx in block.transactions}
    blockchain.unconfirmed_transactions = [
        tx for tx in blockchain.unconfirmed_transactions
        if tx["hash_sinistre"] not in hashes_confirmes
    ]

    return "Block added to the chain", 201


@app.route('/pending_tx')
def get_pending_tx():
    return json.dumps(blockchain.unconfirmed_transactions)


@app.route('/validator_status')
def get_validator_status():
    """Expose l'ordre de passage des validateurs PoA et le tour actuel - pratique pour la démo et le débogage."""
    validateurs = poa.validateurs_actifs(REGISTRE_CLES_PUBLIQUES)
    prochain_index = blockchain.last_block.index + 1
    attendu = validateurs[prochain_index % len(validateurs)] if validateurs else None
    return json.dumps({
        "organisme_id": ORGANISME_ID,
        "validateurs_actifs": validateurs,
        "prochain_bloc": prochain_index,
        "validateur_attendu": attendu,
        "est_notre_tour": attendu == ORGANISME_ID,
    })


def consensus():
    """Si une chaîne plus longue et valide est trouvée chez un pair, elle remplace la nôtre."""
    global blockchain

    longest_chain = None
    current_len = len(blockchain.chain)

    for node in peers:
        response = requests.get('{}chain'.format(node))
        length = response.json()['length']
        chain_dump = response.json()['chain']

        try:
            candidate_blocks = []
            for b in chain_dump:
                block = _block_from_dict(b)
                # check_chain_validity() a besoin de ces champs déjà présents
                block.hash = b["hash"]
                if "validator_organisme" in b:
                    block.validator_organisme = b["validator_organisme"]
                if "validator_signature" in b:
                    block.validator_signature = b["validator_signature"]
                candidate_blocks.append(block)
        except KeyError:
            continue

        if length > current_len and Blockchain.check_chain_validity(candidate_blocks, REGISTRE_CLES_PUBLIQUES):
            current_len = length
            longest_chain = chain_dump

    if longest_chain:
        blockchain = create_chain_from_dump(longest_chain)
        return True

    return False


def announce_new_block(block):
    for peer in peers:
        url = "{}add_block".format(peer)
        headers = {'Content-Type': "application/json"}
        requests.post(url,
                      data=json.dumps(block.__dict__, sort_keys=True),
                      headers=headers)
