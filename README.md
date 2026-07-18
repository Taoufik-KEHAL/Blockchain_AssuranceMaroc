# Registre Blockchain Inter-Assurances

Master SDIA — Projet académique, module Blockchain.

Registre distribué permissionné entre organismes d'assurance santé
(CNOPS, CNSS, assureurs privés) permettant de détecter la double
indemnisation d'un même acte médical, sans qu'aucun organisme ne partage ses
données internes avec un concurrent. Basé sur le tutoriel "Develop a
blockchain application from scratch in Python" (satwikkansal), branche
`ibm_blockchain_post`.

Pour l'analyse complète (justification du choix blockchain, architecture,
modèle de menaces, tests réalisés en conditions réelles, limites), voir
`rapport/Rapport_Technique_Blockchain_Inter_Assurances.docx`.

## Structure du code

Le code applicatif est organisé en couches, sous `registre/` (voir rapport
technique, section 3.2) - chaque couche ne connaît que celles en dessous
d'elle :

```
registre/
    chemins.py       emplacements partagés (secrets/, cles_publiques/)
    hachage.py        couche de hachage      : hash_sinistre()
    identite.py        couche de signature    : clés ECDSA, signer()/verifier()
    gouvernance.py     certification ACAPS    : PKI minimale
    consensus.py       Proof of Authority     : tour de rôle entre organismes certifiés
    chaine.py           couche on-chain        : Block, Blockchain (chaînage + validation)
    noeud.py             couche réseau/API      : nœud Flask (endpoints REST)
    web/                 interface web          : formulaire + journal d'audit
        vues.py
        templates/index.html
scripts/            scripts de gouvernance à usage unique (ACAPS / organismes)
tests/               suites de tests autonomes, une par couche
```

| Fichier / dossier | Rôle |
|---|---|
| `pyproject.toml` / `uv.lock` | Dépendances gérées par `uv` |
| `requirements.txt` | Alternative pip classique (`flask`, `requests`, `cryptography`) |
| `registre/hachage.py` | `hash_sinistre()` : empreinte SHA-256 non réversible (assuré + acte + date) |
| `registre/identite.py` | Génération de clés ECDSA (SECP256K1), signature et vérification (signatures DER) |
| `registre/gouvernance.py` | Certification des clés publiques par l'ACAPS (PKI minimale) |
| `registre/consensus.py` | Consensus alternatif : Proof of Authority à tour de rôle entre organismes certifiés (remplace la preuve de travail du tutoriel) |
| `registre/chaine.py` | Classe `Block` (chaînage SHA-256) + `Blockchain` : structure de données du registre et ses règles de validation |
| `registre/noeud.py` | Nœud Flask d'un organisme : endpoints REST, identité (`ORGANISME_ID`), registre des clés certifiées |
| `registre/web/` | Interface web : déclaration de sinistre + journal d'audit |
| `scripts/generer_autorite_acaps.py` | Script exécuté une seule fois par l'ACAPS |
| `scripts/generer_cles_noeud.py` | Script exécuté une fois par chaque organisme membre |
| `scripts/certifier_cle_organisme.py` | Script exécuté par l'ACAPS pour certifier un organisme |
| `lancer_noeud.py` | Lance le nœud de l'organisme désigné par `ORGANISME_ID` |
| `run_app.py` | Lance l'interface web, connectée à `NODE_ADDRESS` |
| `launcher_gui.py` | Application de bureau (Tkinter) : démarrer/arrêter les 3 nœuds et leurs interfaces web, mailler le réseau, sans terminal |
| `tests/test_hachage.py`, `test_identite.py`, `test_gouvernance.py`, `test_noeud.py` | Suites de tests autonomes, une par couche |

## Installation

```bash
uv sync
```

<details>
<summary>Alternative sans uv (pip classique)</summary>

```bash
pip install -r requirements.txt
```
</details>

## Démarrage rapide (réseau à 3 nœuds)

```bash
# 1. Gouvernance et clés (une seule fois)
uv run python -m scripts.generer_autorite_acaps
uv run python -m scripts.generer_cles_noeud CNOPS
uv run python -m scripts.generer_cles_noeud CNSS
uv run python -m scripts.generer_cles_noeud ASSUREUR_PRIVE
uv run python -m scripts.certifier_cle_organisme CNOPS
uv run python -m scripts.certifier_cle_organisme CNSS
uv run python -m scripts.certifier_cle_organisme ASSUREUR_PRIVE

# 2. Lancer les 3 nœuds (un terminal chacun)
ORGANISME_ID=CNOPS uv run python lancer_noeud.py 8000
ORGANISME_ID=CNSS uv run python lancer_noeud.py 8001
ORGANISME_ID=ASSUREUR_PRIVE uv run python lancer_noeud.py 8002

# 3. Maillage du réseau (répéter pour chaque paire de nœuds) - toujours
#    via /register_with sur le nœud QUI REJOINT : c'est lui qui signe sa
#    propre annonce avec sa clé déjà certifiée par l'ACAPS (/register_node
#    refuse toute adresse non accompagnée d'une signature valide - réseau
#    permissionné, seuls les organismes certifiés peuvent se mailler)
curl -X POST http://127.0.0.1:8001/register_with \
  -H "Content-Type: application/json" \
  -d '{"node_address": "http://127.0.0.1:8000/"}'

# 4. Lancer les interfaces web (une par organisme)
NODE_ADDRESS=http://127.0.0.1:8000 APP_PORT=5000 uv run python run_app.py
```

Voir `rapport/Rapport_Technique_Blockchain_Inter_Assurances.docx`, section 9,
pour les instructions complètes (maillage à 6 appels, dépannage) et section 8
pour le détail des scénarios de test.

### Consensus : Proof of Authority à tour de rôle (pas de preuve de travail)

Le réseau étant permissionné (3 organismes connus, chacun certifié hors
ligne par l'ACAPS), un calcul de preuve de travail n'apporterait ici aucune
protection réelle - voir la discussion détaillée dans le rapport technique.
Le bloc d'indice `n` est scellé par `validateurs[n % len(validateurs)]`
(liste triée des organismes certifiés, donc identique sur tous les nœuds) :
chaque nœud vérifie s'il y a des transactions en attente et si c'est son
tour, toutes les `SCELLEMENT_INTERVALLE_SECONDES` (3 secondes par défaut),
en arrière-plan - aucune action de l'opérateur n'est requise.
`GET /mine` (nom conservé par continuité) et `GET /validator_status`
(ordre de passage, tour actuel) restent disponibles pour la démonstration
et le débogage. Désactivable avec `SCELLEMENT_AUTO=0` (utilisé par les
scripts de test pour un comportement déterministe).

### Alternative : lanceur graphique (sans terminal)

Une fois les clés générées (étape 1 ci-dessus, à faire une seule fois en
ligne de commande), les étapes 2 à 4 peuvent être remplacées par une
application de bureau :

```bash
uv run python launcher_gui.py
```

Elle affiche un panneau par organisme (CNOPS:8000, CNSS:8001,
ASSUREUR_PRIVE:8002) avec un bouton pour démarrer/arrêter son nœud et son
interface web, un journal des logs de chaque nœud, un bouton « Ouvrir dans
le navigateur », et un bouton global « Mailler le réseau » qui effectue les
6 appels `register_with` (chaque nœud s'annonce lui-même, signé avec sa
propre clé certifiée) à la place de l'étape 3. Fermer la fenêtre arrête
proprement tous les processus qu'elle a lancés.

## Lancer les tests

```bash
uv run python -m tests.test_hachage
uv run python -m tests.test_identite
uv run python -m tests.test_gouvernance
uv run python -m tests.test_noeud
```

## Sécurité

`secrets/` (clés privées, `chmod 600`) n'est jamais commité (`.gitignore`).
Seules les clés publiques et leurs certificats ACAPS (`cles_publiques/`)
sont destinés à être distribués entre les nœuds du réseau.

## Limite connue : fenêtre entre soumission et scellement

La détection de doublon d'un nœud ne fait autorité que sur son propre pool
en attente et sa propre chaîne confirmée. Dès qu'une transaction est
acceptée, elle est diffusée à un saut vers les pairs déjà maillés
(`/receive_pending_transaction`) - ce qui détecte la plupart des doublons
soumis à deux organismes différents avant tout scellement de bloc. Cette
diffusion reste best-effort (pas d'accusé de réception, pas de nouvelle
tentative) : deux soumissions quasi simultanées (de l'ordre de la latence
réseau) peuvent encore, dans de rares cas, être acceptées en parallèle par
deux nœuds avant que l'une n'ait eu le temps d'atteindre l'autre. Seul le
scellement d'un bloc (et la propagation qui s'ensuit) constitue une
confirmation définitive.
