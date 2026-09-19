# -*- coding: utf-8 -*-
"""MAYDAY CTF Anti-Cheat Dashboard - Pure Display Layer"""
import sys, os, subprocess, json, threading
from datetime import datetime
from pathlib import Path

try:
    from key_mgr import _SERVER_SECRET_BLOB, _KDF_SALT, derive_kdf_key
    from detection_stub import run_full_detection
except ImportError as e:
    print(f"Warning: {e}")

import tkinter as tk

class AntiCheatGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MAYDAY CTF Anti-Cheat Dashboard")
        self.root.geometry("520x640")
        self.root.configure(bg="#1a1a2e")
        if getattr(sys, 'frozen', False):
            self.repo_root = Path(sys.executable).parent
            self.exe_path = Path(sys._MEIPASS) / "anticheatd" / "build" / "bin" / "Release" / "anticheatd.exe"
        else:
            self.repo_root = Path(__file__).parent.parent
            self.exe_path = self.repo_root / "anticheatd" / "build" / "bin" / "Release" / "anticheatd.exe"
        self.session_id = "---"
        self._build_ui()
        self._check_exe()

    def _build_ui(self):
        tk.Label(self.root, text="MAYDAY CTF Anti-Cheat", font=("Microsoft YaHei UI", 14, "bold"), fg="#00d4ff", bg="#1a1a2e").pack(pady=15)
        tk.Label(self.root, text="FlightGear Competition Anti-Cheat Daemon", font=("Microsoft YaHei UI", 10), fg="#eee", bg="#1a1a2e").pack()
        self.exe_status = tk.Label(self.root, text="Checking...", font=("Microsoft YaHei UI", 9), fg="#fa0", bg="#1a1a2e")
        self.exe_status.pack(pady=5)
        tk.Frame(self.root, height=2, bg="#333").pack(fill="x", pady=8)
        tk.Label(self.root, text="LAYER CHECKS", font=("Microsoft YaHei UI", 9, "bold"), fg="#888", bg="#1a1a2e").pack()
        self.results_frame = tk.Frame(self.root, bg="#16213e", relief="solid", bd=1)
        self.results_frame.pack(fill="x", padx=15, pady=5)
        self.layer_keys = ["L0", "L1", "L2", "L3", "L4", "L5", "VM"]
        self.layer_names = {"L0":"Startup","L1":"Integrity","L2":"Property","L3":"FDM","L4":"Process","L5":"Heartbeat","VM":"Anti-VM"}
        self.layer_labels = {}
        for key in self.layer_keys:
            row = tk.Frame(self.results_frame, bg="#16213e")
            row.pack(fill="x", padx=5, pady=2)
            tk.Label(row, text=f"{key}: {self.layer_names[key]}", font=("Microsoft YaHei UI", 9), fg="#aaa", bg="#16213e").pack(side="left")
            lbl = tk.Label(row, text="...", font=("Segoe UI Symbol", 11), fg="#fa0", bg="#16213e")
            lbl.pack(side="right")
            self.layer_labels[key] = lbl
        tk.Frame(self.root, height=2, bg="#333").pack(fill="x", pady=8)
        info_frame = tk.Frame(self.root, bg="#16213e", relief="solid", bd=1)
        info_frame.pack(fill="x", padx=15, pady=5)
        tk.Label(info_frame, text="SESSION", font=("Microsoft YaHei UI", 9, "bold"), fg="#888", bg="#16213e").pack(anchor="w", padx=5, pady=5)
        self.session_label = tk.Label(info_frame, text="Session: ---", font=("Consolas", 10), fg="#0af", bg="#16213e", anchor="w")
        self.session_label.pack(fill="x", padx=5, pady=3)
        self.time_label = tk.Label(info_frame, text="Time: ---", font=("Consolas", 9), fg="#888", bg="#16213e", anchor="w")
        self.time_label.pack(fill="x", padx=5, pady=0)
        tk.Frame(self.root, height=2, bg="#333").pack(fill="x", pady=8)
        btn_frame = tk.Frame(self.root, bg="#1a1a2e")
        btn_frame.pack(fill="x", padx=15, pady=5)
        self.btn_check = tk.Button(btn_frame, text="Self-Check", font=("Microsoft YaHei UI", 10), bg="#0a6", fg="white", command=self._run_check)
        self.btn_check.pack(side="left", padx=5, expand=True, fill="x")
        self.btn_session = tk.Button(btn_frame, text="Open Session", font=("Microsoft YaHei UI", 10), bg="#06a", fg="white", command=self._open_session)
        self.btn_session.pack(side="left", padx=5, expand=True, fill="x")
        tk.Label(self.root, text="LOG", font=("Microsoft YaHei UI", 9, "bold"), fg="#888", bg="#1a1a2e").pack(anchor="w", padx=15, pady=5)
        self.log_text = tk.Text(self.root, height=8, font=("Consolas", 8), bg="#0d1117", fg="#bbb")
        self.log_text.pack(fill="both", expand=True, padx=15, pady=5)
        self.log_text.config(state="disabled")
        tk.Label(self.root, text="MAYDAY CTF ShanghaiTech 2026", font=("Microsoft YaHei UI", 8), fg="#555", bg="#1a1a2e").pack(pady=5)

    def _check_exe(self):
        if self.exe_path.exists():
            size = self.exe_path.stat().st_size // 1024
            self.exe_status.config(text=f"anticheatd.exe found ({size} KB)", fg="#0f0")
        else:
            self.exe_status.config(text="anticheatd.exe NOT FOUND", fg="#f44")

    def _log(self, msg):
        self.log_text.config(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {msg}\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _update_display(self, json_data):
        if not json_data or "checks" not in json_data:
            return
        # map possible C++ layer names to GUI keys
        layer_alias = {"Anti-VM": "VM"}
        for check in json_data["checks"]:
            layer = check.get("layer", "")
            layer = layer_alias.get(layer, layer)
            passed = check.get("passed", False)
            lbl = self.layer_labels.get(layer)
            if lbl:
                symbol = "\u2714" if passed else "\u2718"  # ✔  ✘
                color = "#0f0" if passed else "#f44"
                lbl.config(text=symbol, fg=color)

    def _run_check(self):
        self.btn_check.config(state="disabled")
        self._log("Running anticheatd.exe --json ...")
        for k in self.layer_labels:
            self.layer_labels[k].config(text="...", fg="#fa0")
        def _do():
            try:
                cmd = [str(self.exe_path), "--mode", "selfcheck", "--json"]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                output = r.stdout + r.stderr
                self._log(output.strip())
                try:
                    s = output.find('{')
                    e = output.rfind('}') + 1
                    if s >= 0 and e > s:
                        jd = json.loads(output[s:e])
                        self._update_display(jd)
                        self._log(f"Display: {jd.get('passed',0)}/{jd.get('total',0)} checks")
                    else:
                        self._log("No JSON found")
                except json.JSONDecodeError as ex:
                    self._log(f"Parse error: {ex}")
            except Exception as ex:
                self._log(f"Error: {ex}")
            finally:
                self.btn_check.config(state="normal")
        threading.Thread(target=_do, daemon=True).start()

    def _open_session(self):
        self.btn_session.config(state="disabled")
        self._log("Opening session...")
        def _do():
            try:
                cmd = [str(self.exe_path), "--mode", "session", "--userid", "GUEST", "--json"]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                output = r.stdout + r.stderr
                self._log(output.strip())
                try:
                    s = output.find('{')
                    e = output.rfind('}') + 1
                    if s >= 0 and e > s:
                        jd = json.loads(output[s:e])
                        if "session_id" in jd:
                            self.session_id = jd["session_id"]
                            self.session_label.config(text=f"Session: {self.session_id}")
                except Exception:
                    pass
            except Exception as ex:
                self._log(f"Error: {ex}")
            finally:
                self.btn_session.config(state="normal")
        threading.Thread(target=_do, daemon=True).start()

    def _update_time(self):
        self.time_label.config(text=f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.root.after(1000, self._update_time)

def main():
    root = tk.Tk()
    app = AntiCheatGUI(root)
    app._update_time()
    root.mainloop()

if __name__ == "__main__":
    main()