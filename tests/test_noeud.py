"""
tests.test_noeud

Test d'intégration via registre.noeud.app.test_client() (sans lancer de
vrai serveur réseau) : scénario nominal, détection de doublon (pool ET
chaîne confirmée), rejet de format invalide, diffusion des transactions en
attente, rejet de blocs frauduleux (signature de validateur falsifiée,
validateur hors tour), et maillage réseau permissionné.

Nécessite les clés déjà générées (voir README.md) : au moins les 3
organismes + ACAPS dans secrets/ et cles_publiques/.

Usage (depuis la racine du dépôt) :
    uv run python -m tests.test_noeud
"""

import json
import os
from hashlib import sha256

from registre import chemins
from registre import consensus as poa

ORGANISMES_CERTIFIES = [
    f[: -len(".cert")] for f in os.listdir(chemins.CLES_PUBLIQUES_DIR) if f.endswith(".cert")
]

# Le nœud de ce test doit être celui dont c'est le tour de sceller le
# premier bloc (index 1) - calculé dynamiquement plutôt que supposé fixe,
# pour ne pas dépendre de l'ordre alphabétique exact des organismes déjà
# certifiés (même principe que test_poa_consensus.py du projet précédent :
# un test qui suppose un validateur fixe casse silencieusement si l'ordre change).
_registre_fictif = {org: None for org in ORGANISMES_CERTIFIES}
ORGANISME_TEST = poa.validateur_attendu(1, _registre_fictif)

os.environ["ORGANISME_ID"] = ORGANISME_TEST
os.environ["SCELLEMENT_AUTO"] = "0"  # scellement déterministe (manuel, via /mine) pendant les tests

from registre import noeud  # déclenche le chargement des clés au moment de l'import
from registre import identite

client = noeud.app.test_client()
results = []


def check(label, response, expected_status):
    ok = response.status_code == expected_status
    results.append(ok)
    print(f"[{'OK ' if ok else 'FAIL'}] {label} -> status={response.status_code} (attendu={expected_status})")


def post(endpoint, payload):
    return client.post(endpoint, data=json.dumps(payload), content_type="application/json")


HASH_1 = "41abeb0690bc1d84a506c09ca0590c6c7b94244af2503bc7e236469ad633b2c0"
HASH_2 = "a" * 64

print(f"Organisme de ce nœud de test : {ORGANISME_TEST} (validateur attendu pour le bloc #1)")

# 1. Scénario nominal : soumission puis scellement
r = post("/new_transaction", {"hash_sinistre": HASH_1})
check("Soumission d'un sinistre", r, 201)

r = client.get("/mine")
check("Scellement du bloc (notre tour)", r, 200)

r = client.get("/chain")
chain_data = json.loads(r.data)
print(f"Longueur de la chaîne après scellement : {chain_data['length']}")
print(f"Validateur du bloc #1 : {chain_data['chain'][1]['validator_organisme']}")

# 2. FRAUDE : re-soumission du même sinistre après scellement -> doublon détecté
r = post("/new_transaction", {"hash_sinistre": HASH_1})
check("FRAUDE: doublon détecté dans la chaîne confirmée", r, 409)
print("  Message :", r.data.decode())

# 3. FRAUDE : doublon détecté dans le pool (avant scellement)
post("/new_transaction", {"hash_sinistre": HASH_2})
r = post("/new_transaction", {"hash_sinistre": HASH_2})
check("FRAUDE: doublon détecté dans le pool en attente", r, 409)

# 4. Format invalide
r = post("/new_transaction", {"hash_sinistre": "pas-un-hash-valide"})
check("Format invalide rejeté", r, 400)

r = post("/new_transaction", {})
check("Champ hash_sinistre manquant rejeté", r, 400)

# 5. FRAUDE : bloc reçu d'un pair avec une signature de VALIDATEUR falsifiée
# (la transaction elle-même est valide et légitimement signée - seule la
# signature qui scelle le bloc est fausse).
fake_index = noeud.blockchain.last_block.index + 1
fake_tx_hash = "b" * 64
fake_content = {
    "index": fake_index,
    "transactions": [{
        "hash_sinistre": fake_tx_hash,
        "organisme_emetteur": ORGANISME_TEST,
        "signature": identite.signer(noeud.CLE_PRIVEE_NOEUD, "{}|{}".format(fake_tx_hash, ORGANISME_TEST)),
        "timestamp": 0,
    }],
    "timestamp": 0,
    "previous_hash": noeud.blockchain.last_block.hash,
}
fake_hash = sha256(json.dumps(fake_content, sort_keys=True).encode()).hexdigest()

faux_bloc_signature = dict(fake_content)
faux_bloc_signature["hash"] = fake_hash
faux_bloc_signature["validator_organisme"] = ORGANISME_TEST
faux_bloc_signature["validator_signature"] = "00" * 70  # signature bidon

r = post("/add_block", faux_bloc_signature)
check("FRAUDE: bloc avec signature de validateur falsifiée rejeté", r, 400)
print("  Message :", r.data.decode())

# 5bis. FRAUDE : bloc signé par un organisme dont ce n'est PAS le tour
attendu_reel = poa.validateur_attendu(fake_index, _registre_fictif)
usurpateur = next((o for o in ORGANISMES_CERTIFIES if o != attendu_reel), None)
if usurpateur and os.path.exists(os.path.join(chemins.SECRETS_DIR, f"{usurpateur}.pem")):
    cle_privee_usurpateur = identite.charger_cle_privee_pem(os.path.join(chemins.SECRETS_DIR, f"{usurpateur}.pem"))
    signature_hors_tour = poa.signer_bloc(cle_privee_usurpateur, fake_hash, usurpateur)
    faux_bloc_tour = dict(fake_content)
    faux_bloc_tour["hash"] = fake_hash
    faux_bloc_tour["validator_organisme"] = usurpateur
    faux_bloc_tour["validator_signature"] = signature_hors_tour
    r = post("/add_block", faux_bloc_tour)
    check(f"FRAUDE: bloc signé hors tour par {usurpateur} (attendu: {attendu_reel}) rejeté", r, 400)
    print("  Message :", r.data.decode())

# 6. Diffusion des transactions en attente entre pairs (/receive_pending_transaction)
HASH_3 = "d" * 64

tx_signature_invalide = {
    "hash_sinistre": HASH_3, "organisme_emetteur": ORGANISME_TEST,
    "signature": "00" * 70, "timestamp": 0,
}
r = post("/receive_pending_transaction", tx_signature_invalide)
check("FRAUDE: transaction diffusée avec signature invalide rejetée", r, 400)

r = post("/receive_pending_transaction", {"hash_sinistre": "pas-valide", "organisme_emetteur": ORGANISME_TEST, "signature": "x", "timestamp": 0})
check("Format invalide rejeté sur /receive_pending_transaction", r, 400)

# Une diffusion légitimement signée par un organisme certifié (celui de ce
# nœud de test lui-même, pour simplifier) doit être acceptée dans le pool.
tx_legitime = {
    "hash_sinistre": HASH_3, "organisme_emetteur": ORGANISME_TEST,
    "signature": identite.signer(noeud.CLE_PRIVEE_NOEUD, "{}|{}".format(HASH_3, ORGANISME_TEST)),
    "timestamp": 0,
}
r = post("/receive_pending_transaction", tx_legitime)
check("Transaction diffusée légitimement acceptée dans le pool", r, 201)

r = post("/receive_pending_transaction", tx_legitime)
check("FRAUDE: re-diffusion du même sinistre déjà dans le pool rejetée", r, 409)

# 7. Maillage permissionné (/register_node) : seul un organisme certifié,
# prouvant la possession de sa clé, peut s'annoncer comme pair.
ADRESSE_BIDON = "http://127.0.0.1:9/"

r = post("/register_node", {"node_address": ADRESSE_BIDON})
check("Maillage sans organisme_id/signature rejeté", r, 400)

r = post("/register_node", {
    "node_address": ADRESSE_BIDON, "organisme_id": "ORGANISME_INCONNU", "signature": "00" * 70,
})
check("FRAUDE: maillage revendiquant un organisme non certifié rejeté", r, 403)

r = post("/register_node", {
    "node_address": ADRESSE_BIDON, "organisme_id": ORGANISME_TEST, "signature": "00" * 70,
})
check("FRAUDE: maillage avec signature falsifiée rejeté", r, 401)

signature_maillage = identite.signer(noeud.CLE_PRIVEE_NOEUD, "{}|{}".format(ADRESSE_BIDON, ORGANISME_TEST))
r = post("/register_node", {
    "node_address": ADRESSE_BIDON, "organisme_id": ORGANISME_TEST, "signature": signature_maillage,
})
check("Maillage légitimement signé par un organisme certifié accepté", r, 200)

print("\nRésultat global :", "TOUS LES TESTS PASSENT" if all(results) else "ECHEC sur au moins un test")
