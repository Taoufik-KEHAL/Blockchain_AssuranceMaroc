"""
launcher_gui.py

Application de bureau (Tkinter) pour mettre en place la gouvernance et les
clés, démarrer/arrêter les 3 nœuds du réseau (CNOPS, CNSS, ASSUREUR_PRIVE)
et leur interface web associée, sans passer par le terminal. Remplace les
4 étapes du démarrage rapide (README.md) : gouvernance et clés, lancement
des nœuds, maillage du réseau, lancement des interfaces web.

Les 3 boutons « Gouvernance et clés » exécutent, en sous-processus,
exactement les mêmes scripts que la ligne de commande (scripts/
generer_autorite_acaps.py, generer_cles_noeud.py, certifier_cle_organisme.py)
- des scripts de bootstrap normalement exécutés une fois par le rôle
correspondant (ACAPS ou organisme), pas des actions répétées à chaque
lancement, mais idempotents : les rejouer ne régénère jamais une clé déjà
existante.

Usage :
    uv run python launcher_gui.py
"""

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox, scrolledtext, ttk

import requests

from registre.chemins import SECRETS_DIR, CLES_PUBLIQUES_DIR

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ORGANISMES = [
    {"id": "CNOPS", "node_port": 8000, "web_port": 5000},
    {"id": "CNSS", "node_port": 8001, "web_port": 5001},
    {"id": "ASSUREUR_PRIVE", "node_port": 8002, "web_port": 5002},
]


class ProcessSlot:
    """Un processus enfant géré (nœud ou interface web) + son flux de logs."""

    def __init__(self):
        self.popen = None
        self.log_queue = queue.Queue()
        self.stopped_by_user = False

    @property
    def running(self):
        return self.popen is not None and self.popen.poll() is None

    def start(self, args, env, on_line=None):
        self.stopped_by_user = False
        self.popen = subprocess.Popen(
            args, cwd=BASE_DIR, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )

        def _reader():
            for line in iter(self.popen.stdout.readline, ""):
                self.log_queue.put(line)
            self.popen.stdout.close()

        threading.Thread(target=_reader, daemon=True).start()

    def stop(self):
        if self.running:
            self.stopped_by_user = True
            self.popen.terminate()
            try:
                self.popen.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.popen.kill()


class OrganismePanel(ttk.LabelFrame):
    def __init__(self, master, config, app):
        super().__init__(master, text=f"{config['id']}  —  nœud :{config['node_port']}  /  interface :{config['web_port']}")
        self.config_ = config
        self.app = app
        self.node = ProcessSlot()
        self.web = ProcessSlot()

        self.node_status = tk.StringVar(value="● nœud arrêté")
        self.web_status = tk.StringVar(value="● interface arrêtée")
        ttk.Label(self, textvariable=self.node_status, foreground="#8a1f1f").grid(row=0, column=0, sticky="w", padx=6, pady=(6, 0))
        ttk.Label(self, textvariable=self.web_status, foreground="#8a1f1f").grid(row=0, column=1, sticky="w", padx=6, pady=(6, 0))

        btns = ttk.Frame(self)
        btns.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=6)
        self.btn_start_node = ttk.Button(btns, text="Démarrer nœud", command=self.start_node)
        self.btn_stop_node = ttk.Button(btns, text="Arrêter nœud", command=self.stop_node, state="disabled")
        self.btn_start_web = ttk.Button(btns, text="Démarrer interface", command=self.start_web, state="disabled")
        self.btn_stop_web = ttk.Button(btns, text="Arrêter interface", command=self.stop_web, state="disabled")
        self.btn_open = ttk.Button(btns, text="Ouvrir dans le navigateur", command=self.open_browser, state="disabled")
        for i, b in enumerate([self.btn_start_node, self.btn_stop_node, self.btn_start_web, self.btn_stop_web, self.btn_open]):
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)
        btns.columnconfigure(0, weight=1)
        btns.columnconfigure(1, weight=1)

        self.log_widget = scrolledtext.ScrolledText(self, height=10, width=40, state="disabled", font=("Consolas", 8))
        self.log_widget.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=6, pady=(0, 6))

    def _append_log(self, text):
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", text)
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def start_node(self):
        cle_privee = os.path.join(SECRETS_DIR, f"{self.config_['id']}.pem")
        if not os.path.exists(cle_privee):
            messagebox.showerror(
                "Clés manquantes",
                f"{cle_privee} introuvable.\n\n"
                "Utiliser d'abord, une seule fois, les boutons « Gouvernance et "
                "clés » en haut de la fenêtre : 1. Générer clé ACAPS, "
                "2. Générer clés des organismes, 3. Certifier les organismes."
            )
            return

        env = os.environ.copy()
        env["ORGANISME_ID"] = self.config_["id"]
        self.node.start([sys.executable, "lancer_noeud.py", str(self.config_["node_port"])], env)
        self.node_status.set("● nœud actif")
        self.btn_start_node.configure(state="disabled")
        self.btn_stop_node.configure(state="normal")
        self.btn_start_web.configure(state="normal")

    def stop_node(self):
        self.node.stop()
        self.node_status.set("● nœud arrêté")
        self.btn_start_node.configure(state="normal")
        self.btn_stop_node.configure(state="disabled")

    def start_web(self):
        env = os.environ.copy()
        env["NODE_ADDRESS"] = f"http://127.0.0.1:{self.config_['node_port']}"
        env["APP_PORT"] = str(self.config_["web_port"])
        self.web.start([sys.executable, "run_app.py"], env)
        self.web_status.set("● interface active")
        self.btn_start_web.configure(state="disabled")
        self.btn_stop_web.configure(state="normal")
        self.btn_open.configure(state="normal")

    def stop_web(self):
        self.web.stop()
        self.web_status.set("● interface arrêtée")
        self.btn_start_web.configure(state="normal" if self.node.running else "disabled")
        self.btn_stop_web.configure(state="disabled")
        self.btn_open.configure(state="disabled")

    def open_browser(self):
        webbrowser.open(f"http://127.0.0.1:{self.config_['web_port']}/")

    def poll(self):
        """Draine les logs en attente et détecte un arrêt inattendu (crash)."""
        for slot, status_var, on_stop in (
            (self.node, self.node_status, self._on_node_died),
            (self.web, self.web_status, self._on_web_died),
        ):
            while True:
                try:
                    line = slot.log_queue.get_nowait()
                except queue.Empty:
                    break
                self._append_log(line)

            if slot.popen is not None and slot.popen.poll() is not None and not slot.stopped_by_user:
                on_stop()
                slot.popen = None

    def _on_node_died(self):
        self.node_status.set("● nœud arrêté (terminé de façon inattendue)")
        self.btn_start_node.configure(state="normal")
        self.btn_stop_node.configure(state="disabled")

    def _on_web_died(self):
        self.web_status.set("● interface arrêtée (terminée de façon inattendue)")
        self.btn_start_web.configure(state="normal" if self.node.running else "disabled")
        self.btn_stop_web.configure(state="disabled")
        self.btn_open.configure(state="disabled")

    def stop_all(self):
        self.node.stop()
        self.web.stop()


class LauncherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Registre Blockchain Inter-Assurances — Lanceur")
        self.geometry("1080x560")

        gouvernance = ttk.LabelFrame(self, text="Gouvernance et clés (à faire une seule fois, dans l'ordre)")
        gouvernance.pack(fill="x", padx=8, pady=(8, 0))

        boutons = ttk.Frame(gouvernance)
        boutons.pack(fill="x")
        ttk.Button(boutons, text="1. Générer clé ACAPS", command=self.generer_cle_acaps).grid(row=0, column=0, padx=4, pady=(6, 0), sticky="ew")
        ttk.Button(boutons, text="2. Générer clés des organismes", command=self.generer_cles_organismes).grid(row=0, column=1, padx=4, pady=(6, 0), sticky="ew")
        ttk.Button(boutons, text="3. Certifier les organismes", command=self.certifier_organismes).grid(row=0, column=2, padx=4, pady=(6, 0), sticky="ew")
        for col in range(3):
            boutons.columnconfigure(col, weight=1)

        self.acaps_status = tk.StringVar()
        self.cles_status = tk.StringVar()
        self.certificats_status = tk.StringVar()
        self.lbl_acaps_status = ttk.Label(boutons, textvariable=self.acaps_status, anchor="center")
        self.lbl_cles_status = ttk.Label(boutons, textvariable=self.cles_status, anchor="center")
        self.lbl_certificats_status = ttk.Label(boutons, textvariable=self.certificats_status, anchor="center")
        self.lbl_acaps_status.grid(row=1, column=0, padx=4, pady=(0, 6), sticky="ew")
        self.lbl_cles_status.grid(row=1, column=1, padx=4, pady=(0, 6), sticky="ew")
        self.lbl_certificats_status.grid(row=1, column=2, padx=4, pady=(0, 6), sticky="ew")
        self._rafraichir_statut_gouvernance()

        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=8)
        ttk.Button(top, text="Mailler le réseau (register_with)", command=self.mailler_reseau).pack(side="left")
        self.mesh_status = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.mesh_status).pack(side="left", padx=10)

        panels_frame = ttk.Frame(self)
        panels_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.panels = []
        for i, config in enumerate(ORGANISMES):
            panel = OrganismePanel(panels_frame, config, self)
            panel.grid(row=0, column=i, sticky="nsew", padx=4)
            panels_frame.columnconfigure(i, weight=1)
            self.panels.append(panel)
        panels_frame.rowconfigure(0, weight=1)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(200, self._poll_all)

    def _poll_all(self):
        for panel in self.panels:
            panel.poll()
        self._rafraichir_statut_gouvernance()
        self.after(200, self._poll_all)

    def _rafraichir_statut_gouvernance(self):
        """
        Relit l'état réel des clés sur le disque (jamais une supposition ni
        un état gardé en mémoire) : reflète aussi bien un clic sur un
        bouton que des clés générées entre-temps en ligne de commande.
        Rafraîchi en continu par _poll_all, donc toujours à jour.
        """
        n = len(ORGANISMES)
        vert, rouge = "#2f7a4d", "#8a1f1f"

        acaps_ok = os.path.exists(os.path.join(SECRETS_DIR, "ACAPS.pem")) and \
            os.path.exists(os.path.join(CLES_PUBLIQUES_DIR, "ACAPS.pem"))
        self.acaps_status.set("✓ clé ACAPS présente" if acaps_ok else "✗ clé ACAPS manquante")
        self.lbl_acaps_status.configure(foreground=vert if acaps_ok else rouge)

        cles_ok = sum(
            os.path.exists(os.path.join(SECRETS_DIR, f"{c['id']}.pem")) for c in ORGANISMES
        )
        self.cles_status.set(f"{'✓' if cles_ok == n else '✗'} clés organismes : {cles_ok}/{n}")
        self.lbl_cles_status.configure(foreground=vert if cles_ok == n else rouge)

        certs_ok = sum(
            os.path.exists(os.path.join(CLES_PUBLIQUES_DIR, f"{c['id']}.cert")) for c in ORGANISMES
        )
        self.certificats_status.set(f"{'✓' if certs_ok == n else '✗'} organismes certifiés : {certs_ok}/{n}")
        self.lbl_certificats_status.configure(foreground=vert if certs_ok == n else rouge)

    def _executer_script_gouvernance(self, module, organisme_id=None):
        """
        Exécute un script de scripts/ (générer/certifier des clés) en
        sous-processus, comme un `uv run python -m ...` en ligne de
        commande, mais depuis un bouton - idempotent (les scripts ne
        régénèrent jamais une clé déjà existante), donc rejouable sans
        risque. Retourne la sortie combinée (stdout + stderr).
        """
        args = [sys.executable, "-m", module]
        if organisme_id:
            args.append(organisme_id)
        result = subprocess.run(args, cwd=BASE_DIR, capture_output=True, text=True)
        sortie = (result.stdout + result.stderr).strip()
        return sortie or f"(aucune sortie, code retour {result.returncode})"

    def generer_cle_acaps(self):
        sortie = self._executer_script_gouvernance("scripts.generer_autorite_acaps")
        messagebox.showinfo("1. Générer clé ACAPS", sortie)

    def generer_cles_organismes(self):
        sorties = [self._executer_script_gouvernance("scripts.generer_cles_noeud", c["id"]) for c in ORGANISMES]
        messagebox.showinfo("2. Générer clés des organismes", "\n".join(sorties))

    def certifier_organismes(self):
        sorties = [self._executer_script_gouvernance("scripts.certifier_cle_organisme", c["id"]) for c in ORGANISMES]
        messagebox.showinfo("3. Certifier les organismes", "\n".join(sorties))

    def mailler_reseau(self):
        actifs = [p for p in self.panels if p.node.running]
        if len(actifs) < 2:
            messagebox.showwarning("Maillage impossible", "Démarrer au moins 2 nœuds avant de mailler le réseau.")
            return

        erreurs = []
        for panel in actifs:
            for autre in actifs:
                if autre is panel:
                    continue
                # /register_with (pas /register_node) : le nœud "panel" signe
                # lui-même sa propre annonce avec sa clé certifiée - le
                # lanceur graphique n'a et ne doit avoir accès à aucune clé.
                url = f"http://127.0.0.1:{panel.config_['node_port']}/register_with"
                adresse = f"http://127.0.0.1:{autre.config_['node_port']}/"
                try:
                    r = requests.post(url, json={"node_address": adresse}, timeout=3)
                    if r.status_code != 200:
                        erreurs.append(f"{panel.config_['id']} <- {autre.config_['id']} : HTTP {r.status_code}")
                except requests.RequestException as e:
                    erreurs.append(f"{panel.config_['id']} <- {autre.config_['id']} : {e}")

        if erreurs:
            self.mesh_status.set("Maillage partiel — voir détails")
            messagebox.showerror("Erreurs de maillage", "\n".join(erreurs))
        else:
            self.mesh_status.set(f"Réseau maillé ({len(actifs)} nœuds).")

    def on_close(self):
        for panel in self.panels:
            panel.stop_all()
        self.destroy()


if __name__ == "__main__":
    LauncherApp().mainloop()
