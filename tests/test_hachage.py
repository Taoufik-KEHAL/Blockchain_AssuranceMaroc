"""
tests.test_hachage

Vérifie hash_sinistre() contre le vecteur de test réel cité dans le rapport
technique (section 4.1), et les propriétés attendues (déterminisme,
sensibilité à chaque champ).

Usage (depuis la racine du dépôt) :
    uv run python -m tests.test_hachage
"""

from registre.hachage import hash_sinistre

results = []


def check(label, condition):
    results.append(condition)
    print(f"[{'OK ' if condition else 'FAIL'}] {label}")


check(
    "Vecteur de test du rapport (section 4.1)",
    hash_sinistre("CN123456789", "CONSULT_GEN", "2026-07-10")
    == "41abeb0690bc1d84a506c09ca0590c6c7b94244af2503bc7e236469ad633b2c0",
)

check(
    "Déterminisme : mêmes entrées -> même empreinte",
    hash_sinistre("CN1", "ACTE1", "2026-01-01") == hash_sinistre("CN1", "ACTE1", "2026-01-01"),
)

check(
    "Sensibilité à l'identifiant assuré",
    hash_sinistre("CN1", "ACTE1", "2026-01-01") != hash_sinistre("CN2", "ACTE1", "2026-01-01"),
)

check(
    "Sensibilité au code d'acte",
    hash_sinistre("CN1", "ACTE1", "2026-01-01") != hash_sinistre("CN1", "ACTE2", "2026-01-01"),
)

check(
    "Sensibilité à la date",
    hash_sinistre("CN1", "ACTE1", "2026-01-01") != hash_sinistre("CN1", "ACTE1", "2026-01-02"),
)

check(
    "Format : 64 caractères hexadécimaux",
    len(hash_sinistre("CN1", "ACTE1", "2026-01-01")) == 64,
)

check(
    "Le paramètre sel change l'empreinte",
    hash_sinistre("CN1", "ACTE1", "2026-01-01", sel="x") != hash_sinistre("CN1", "ACTE1", "2026-01-01"),
)

print("\nRésultat global :", "TOUS LES TESTS PASSENT" if all(results) else "ECHEC sur au moins un test")
