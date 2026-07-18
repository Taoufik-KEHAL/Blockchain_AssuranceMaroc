"""
registre.web.vues

Interface web d'un organisme : formulaire de déclaration de sinistre
(calcule hash_sinistre localement, sans jamais transmettre l'identifiant
assuré ni le code d'acte au nœud), et journal d'audit listant les sinistres
déjà scellés sur la chaîne de son propre nœud (NODE_ADDRESS).
"""

import os
import json
from datetime import datetime

import requests
from flask import render_template, request, redirect, url_for, flash

from . import app
from .. import hachage

NODE_ADDRESS = os.environ.get("NODE_ADDRESS", "http://127.0.0.1:8000")


def _fetch_journal():
    try:
        response = requests.get(NODE_ADDRESS + "/chain", timeout=3)
        response.raise_for_status()
    except requests.RequestException:
        return []

    data = response.json()
    entries = []
    for block in data["chain"]:
        for tx in block["transactions"]:
            entries.append({
                "hash_sinistre": tx["hash_sinistre"],
                "organisme_emetteur": tx["organisme_emetteur"],
                "bloc": block["index"],
                "horodatage": datetime.fromtimestamp(tx["timestamp"]).strftime("%d/%m/%Y %H:%M:%S"),
                "timestamp": tx["timestamp"],
            })
    entries.sort(key=lambda e: e["timestamp"], reverse=True)
    return entries


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", node_address=NODE_ADDRESS, journal=_fetch_journal())


@app.route("/", methods=["POST"])
def declarer_sinistre():
    identifiant_assure = request.form.get("identifiant_assure", "").strip()
    code_acte = request.form.get("code_acte", "").strip()
    date_acte = request.form.get("date_acte", "").strip()

    if not identifiant_assure or not code_acte or not date_acte:
        flash("Tous les champs sont requis.", "error")
        return redirect(url_for("index"))

    hash_sinistre = hachage.hash_sinistre(identifiant_assure, code_acte, date_acte)

    try:
        response = requests.post(
            NODE_ADDRESS + "/new_transaction",
            data=json.dumps({"hash_sinistre": hash_sinistre}),
            headers={"Content-Type": "application/json"},
            timeout=3,
        )
    except requests.RequestException as e:
        flash(f"Nœud injoignable : {e}", "error")
        return redirect(url_for("index"))

    if response.status_code == 201:
        flash("Sinistre enregistré avec succès (scellement automatique sous quelques secondes).", "success")
    elif response.status_code == 409:
        flash(response.text, "error")
    else:
        flash(f"Erreur du nœud ({response.status_code}) : {response.text}", "error")

    return redirect(url_for("index"))


@app.route("/sceller", methods=["GET"])
def sceller():
    # Le scellement PoA est automatique en arrière-plan (SCELLEMENT_AUTO) ;
    # ce bouton force juste une tentative immédiate, utile pour la démo,
    # via l'endpoint /mine du nœud (nom conservé côté registre.noeud par
    # continuité avec le tutoriel d'origine).
    try:
        response = requests.get(NODE_ADDRESS + "/mine", timeout=10)
        flash(response.text, "success" if response.status_code == 200 else "error")
    except requests.RequestException as e:
        flash(f"Nœud injoignable : {e}", "error")
    return redirect(url_for("index"))


@app.route("/resync", methods=["GET"])
def resync():
    # Le rapport ne décrit pas d'endpoint de resynchronisation dédié côté
    # nœud (seul /mine déclenche le consensus) : ce bouton recharge
    # simplement la vue, ce qui relit /chain à jour.
    return redirect(url_for("index"))
