"""
tests.test_gouvernance

Vérifie registre.gouvernance : certificat ACAPS valide accepté, clé non
certifiée / certificat falsifié / organisme usurpé rejetés — les 3 cas
testés en conditions réelles section 8.3 du rapport.

Usage (depuis la racine du dépôt) :
    uv run python -m tests.test_gouvernance
"""

from registre import identite, gouvernance

results = []


def check(label, condition):
    results.append(condition)
    print(f"[{'OK ' if condition else 'FAIL'}] {label}")


priv_acaps, pub_acaps = identite.generer_paire_cles()
priv_cnss, pub_cnss = identite.generer_paire_cles()
pem_cnss = identite.serialiser_cle_publique_pem(pub_cnss)

certificat = gouvernance.certifier_cle_publique("CNSS", pem_cnss, priv_acaps)

check(
    "Certificat valide émis par l'ACAPS -> accepté",
    gouvernance.verifier_certificat("CNSS", pem_cnss, certificat, pub_acaps),
)

check(
    "FRAUDE: organisme usurpé (même certificat, autre organisme_id) -> rejeté",
    not gouvernance.verifier_certificat("CNOPS", pem_cnss, certificat, pub_acaps),
)

check(
    "FRAUDE: certificat falsifié (signature bidon) -> rejeté",
    not gouvernance.verifier_certificat("CNSS", pem_cnss, "deadbeef", pub_acaps),
)

_, pub_racine_falsifiee = identite.generer_paire_cles()
check(
    "FRAUDE: certificat vérifié avec une mauvaise clé racine ACAPS -> rejeté",
    not gouvernance.verifier_certificat("CNSS", pem_cnss, certificat, pub_racine_falsifiee),
)

print("\nRésultat global :", "TOUS LES TESTS PASSENT" if all(results) else "ECHEC sur au moins un test")
