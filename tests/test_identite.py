"""
tests.test_identite

Vérifie signer()/verifier() (ECDSA SECP256K1 via `cryptography`) : signature
valide acceptée, message falsifié rejeté, signature falsifiée rejetée,
signature absente rejetée sans exception.

Usage (depuis la racine du dépôt) :
    uv run python -m tests.test_identite
"""

from registre import identite

results = []


def check(label, condition):
    results.append(condition)
    print(f"[{'OK ' if condition else 'FAIL'}] {label}")


priv_a, pub_a = identite.generer_paire_cles()
priv_b, pub_b = identite.generer_paire_cles()

message = "41abeb0690bc1d84a506c09ca0590c6c7b94244af2503bc7e236469ad633b2c0|CNSS"
signature = identite.signer(priv_a, message)

check("Signature valide acceptée par la bonne clé publique", identite.verifier(pub_a, message, signature))
check("FRAUDE: signature rejetée par la clé publique d'un autre organisme", not identite.verifier(pub_b, message, signature))
check("FRAUDE: message falsifié rejeté (même signature, autre message)", not identite.verifier(pub_a, message + "x", signature))
check("FRAUDE: signature falsifiée rejetée", not identite.verifier(pub_a, message, "deadbeef"))
check("Signature absente rejetée sans exception", not identite.verifier(pub_a, message, ""))
check("Signature None rejetée sans exception", not identite.verifier(pub_a, message, None))

pem_pub = identite.serialiser_cle_publique_pem(pub_a)
pem_priv = identite.serialiser_cle_privee_pem(priv_a)
check("Sérialisation clé publique PEM", pem_pub.startswith(b"-----BEGIN PUBLIC KEY-----"))
check("Sérialisation clé privée PEM", pem_priv.startswith(b"-----BEGIN PRIVATE KEY-----"))

print("\nRésultat global :", "TOUS LES TESTS PASSENT" if all(results) else "ECHEC sur au moins un test")
