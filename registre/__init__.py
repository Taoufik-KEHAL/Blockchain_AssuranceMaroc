"""
registre — Registre Blockchain Inter-Assurances.

Package organisé en couches (voir rapport technique, section 3.2) :
  - hachage      : empreinte SHA-256 non réversible d'un sinistre
  - identite      : clés ECDSA, signature et vérification
  - gouvernance   : certification des clés par l'ACAPS (PKI minimale)
  - consensus     : Proof of Authority à tour de rôle entre organismes certifiés
  - chaine        : structure de données du registre (Block, Blockchain)
  - noeud         : couche réseau/API - nœud Flask d'un organisme
  - web           : interface web (déclaration de sinistre, journal d'audit)
"""
