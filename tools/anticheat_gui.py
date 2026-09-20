﻿# -*- coding: utf-8 -*-
"""MAYDAY CTF Anti-Cheat Dashboard — Competition Mode"""
import sys, os, subprocess, json, threading
from datetime import datetime
from pathlib import Path

try:
    from key_mgr import _SERVER_SECRET_BLOB, _KDF_SALT, derive_kdf_key
    from detection_stub import run_full_detection
except ImportError as e:
    print(f"Warning: {e}")

import tkinter as tk
from tkinter import filedialog


class AntiCheatGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MAYDAY CTF Anti-Cheat Dashboard")
        self.root.geometry("560x820")
        self.root.configure(bg="#1a1a2e")
        if getattr(sys, 'frozen', False):
            self.repo_root = Path(sys.executable).parent
            self.exe_path = Path(sys._MEIPASS) / "anticheatd" / "build" / "bin" / "Release" / "anticheatd.exe"
        else:
            self.repo_root = Path(__file__).resolve().parent.parent
            self.exe_path = self.repo_root / "anticheatd" / "build" / "bin" / "Release" / "anticheatd.exe"
        self.session_id = "---"
        self.daemon_proc = None
        self._fg = FGLocations()  # auto-detected FG paths
        self._detect_fg()
        self._build_ui()
        self._check_exe()

    # ── FG auto-detect ──────────────────────────────────────────────
    def _detect_fg(self):
        try:
            from tools.fg_detect import detect as fg_d, FGLocations
            self._fg = fg_d()
            if self._fg.data_root:
                self._log(f"FG detect: data={self._fg.data_root}")
            else:
                self._log("FG detect: NO FG installation found (data_root empty)")
            if self._fg.bin_dir:
                self._log(f"FG detect: bin={self._fg.bin_dir}")
            else:
                self._log("FG detect: NO FG binary found")
        except Exception as e:
            self._log(f"FG detect ERROR: {e}")
            self._fg = type('FGLocations', (), {
                'data_root': None, 'bin_dir': None, 'scenery_dir': None, 'bin_exe': None, 'valid': False
            })()
            import traceback; traceback.print_exc()

    # ── Competition args builder ────────────────────────────────────
    def _build_comp_args(self):
        """Return list of anticheatd args representing competition environment."""
        args = []
        # FG paths (for L1 file integrity)
        if self.fg_root_var.get():
            args += ["--fg-root", self.fg_root_var.get()]
        if self.fg_bin_var.get():
            args += ["--fg-bin", self.fg_bin_var.get()]
        if self.scenery_var.get():
            args += ["--scenery", self.scenery_var.get()]

        # Lock file
        args += ["--lock-file", self.lock_var.get() or str(self.repo_root / "env.lock")]

        # Server
        server = self.server_entry.get().strip()
        if server:
            args += ["--server", server]

        # FG args: --addon=<path> (for L0 validation)
        addon = self.addon_var.get()
        if addon:
            args.append("--addon=" + addon)

        # FG args: --multiplay= (for L0 validation)
        mp_out = self._build_multiplay_out()
        if mp_out:
            args.append("--multiplay=" + mp_out)

        mp_in = self._build_multiplay_in()
        if mp_in:
            args.append("--multiplay=" + mp_in)

        return args

    def _build_multiplay_out(self):
        mp_enabled = self.mp_out_enabled_var.get()
        if not mp_enabled:
            return ""
        direction = "out"
        hz = self.mp_out_hz_var.get() or "10"
        host = self.mp_out_host_var.get() or "255.255.255.255"
        port = self.mp_out_port_var.get() or "5000"
        return f"{direction},{hz},{host},{port}"

    def _build_multiplay_in(self):
        mp_enabled = self.mp_in_enabled_var.get()
        if not mp_enabled:
            return ""
        direction = "in"
        hz = self.mp_in_hz_var.get() or "10"
        port = self.mp_in_port_var.get() or "5000"
        return f"{direction},{hz},,{port}"

    # ── UI ─────────────────────────────────────────────────────────
    def _build_ui(self):
        tk.Label(self.root, text="MAYDAY CTF Anti-Cheat", font=("Microsoft YaHei UI", 14, "bold"),
                 fg="#00d4ff", bg="#1a1a2e").pack(pady=12)
        tk.Label(self.root, text="FlightGear Competition Anti-Cheat Daemon", font=("Microsoft YaHei UI", 10),
                 fg="#eee", bg="#1a1a2e").pack()
        self.exe_status = tk.Label(self.root, text="Checking...", font=("Microsoft YaHei UI", 9),
                                    fg="#fa0", bg="#1a1a2e")
        self.exe_status.pack(pady=3)

        # ── Layer Checks ──
        tk.Frame(self.root, height=1, bg="#333").pack(fill="x", pady=6)
        tk.Label(self.root, text="LAYER CHECKS", font=("Microsoft YaHei UI", 9, "bold"),
                 fg="#888", bg="#1a1a2e").pack()
        self.results_frame = tk.Frame(self.root, bg="#16213e", relief="solid", bd=1)
        self.results_frame.pack(fill="x", padx=15, pady=3)
        self.layer_keys = ["L0", "L1", "L2", "L3", "L4", "L5", "VM"]
        self.layer_names = {"L0": "Startup", "L1": "Integrity", "L2": "Property",
                            "L3": "FDM", "L4": "Process", "L5": "Heartbeat", "VM": "Anti-VM"}
        self.layer_labels = {}
        for key in self.layer_keys:
            row = tk.Frame(self.results_frame, bg="#16213e")
            row.pack(fill="x", padx=5, pady=1)
            tk.Label(row, text=f"{key}: {self.layer_names[key]}", font=("Microsoft YaHei UI", 9),
                     fg="#aaa", bg="#16213e").pack(side="left")
            lbl = tk.Label(row, text="...", font=("Segoe UI Symbol", 11), fg="#fa0", bg="#16213e")
            lbl.pack(side="right")
            self.layer_labels[key] = lbl

        # ── Session info ──
        tk.Frame(self.root, height=1, bg="#333").pack(fill="x", pady=6)
        info_frame = tk.Frame(self.root, bg="#16213e", relief="solid", bd=1)
        info_frame.pack(fill="x", padx=15, pady=3)
        tk.Label(info_frame, text="SESSION", font=("Microsoft YaHei UI", 9, "bold"),
                 fg="#888", bg="#16213e").pack(anchor="w", padx=5, pady=3)
        self.session_label = tk.Label(info_frame, text="Session: ---", font=("Consolas", 10),
                                       fg="#0af", bg="#16213e", anchor="w")
        self.session_label.pack(fill="x", padx=5, pady=2)
        self.time_label = tk.Label(info_frame, text="Time: ---", font=("Consolas", 9),
                                    fg="#888", bg="#16213e", anchor="w")
        self.time_label.pack(fill="x", padx=5, pady=0)

        # ── Server ──
        tk.Frame(self.root, height=1, bg="#333").pack(fill="x", pady=6)
        srv_frame = tk.Frame(self.root, bg="#16213e", relief="solid", bd=1)
        srv_frame.pack(fill="x", padx=15, pady=3)
        tk.Label(srv_frame, text="SERVER", font=("Microsoft YaHei UI", 9, "bold"),
                 fg="#888", bg="#16213e").pack(anchor="w", padx=5, pady=3)
        srv_row = tk.Frame(srv_frame, bg="#16213e")
        srv_row.pack(fill="x", padx=5, pady=2)
        tk.Label(srv_row, text="Address:", font=("Microsoft YaHei UI", 9),
                 fg="#aaa", bg="#16213e").pack(side="left")
        self.server_entry = tk.Entry(srv_row, font=("Consolas", 10), bg="#0d1117", fg="#0af",
                                     insertbackground="#0af", relief="solid", bd=0, width=24)
        self.server_entry.pack(side="left", padx=5)
        self.server_entry.insert(0, "127.0.0.1:5001")

        # ── Competition Config ──
        tk.Frame(self.root, height=1, bg="#333").pack(fill="x", pady=6)
        comp_frame = tk.Frame(self.root, bg="#16213e", relief="solid", bd=1)
        comp_frame.pack(fill="x", padx=15, pady=3)
        tk.Label(comp_frame, text="COMPETITION CONFIG (FG paths auto-detected)",
                 font=("Microsoft YaHei UI", 9, "bold"), fg="#fa0", bg="#16213e").pack(anchor="w", padx=5, pady=3)

        # Callsign
        r0 = tk.Frame(comp_frame, bg="#16213e")
        r0.pack(fill="x", padx=5, pady=1)
        tk.Label(r0, text="Callsign:", font=("Microsoft YaHei UI", 9), fg="#aaa", bg="#16213e",
                 width=14, anchor="e").pack(side="left")
        self.uid_entry = tk.Entry(r0, font=("Consolas", 10), bg="#0d1117", fg="#0f0",
                                  insertbackground="#0f0", relief="solid", bd=0, width=22)
        self.uid_entry.pack(side="left", padx=5)
        self.uid_entry.insert(0, "GUEST")

        # FG Root
        r1 = tk.Frame(comp_frame, bg="#16213e")
        r1.pack(fill="x", padx=5, pady=1)
        tk.Label(r1, text="FG Root:", font=("Microsoft YaHei UI", 9), fg="#aaa", bg="#16213e",
                 width=14, anchor="e").pack(side="left")
        self.fg_root_var = tk.StringVar(value=self._fg.data_root or "")
        self.fg_root_entry = tk.Entry(r1, textvariable=self.fg_root_var, font=("Consolas", 9),
                                      bg="#0d1117", fg="#ddd", relief="solid", bd=0, width=38)
        self.fg_root_entry.pack(side="left", padx=5)
        tk.Button(r1, text="...", font=("Microsoft YaHei UI", 8), bg="#444", fg="#fff",
                  command=lambda: self._browse_dir(self.fg_root_var)).pack(side="left")

        # FG Binary
        r2 = tk.Frame(comp_frame, bg="#16213e")
        r2.pack(fill="x", padx=5, pady=1)
        tk.Label(r2, text="FG Binary:", font=("Microsoft YaHei UI", 9), fg="#aaa", bg="#16213e",
                 width=14, anchor="e").pack(side="left")
        self.fg_bin_var = tk.StringVar(value=self._fg.bin_dir or "")
        self.fg_bin_entry = tk.Entry(r2, textvariable=self.fg_bin_var, font=("Consolas", 9),
                                     bg="#0d1117", fg="#ddd", relief="solid", bd=0, width=38)
        self.fg_bin_entry.pack(side="left", padx=5)
        tk.Button(r2, text="...", font=("Microsoft YaHei UI", 8), bg="#444", fg="#fff",
                  command=lambda: self._browse_dir(self.fg_bin_var)).pack(side="left")

        # FG Scenery
        r2b = tk.Frame(comp_frame, bg="#16213e")
        r2b.pack(fill="x", padx=5, pady=1)
        tk.Label(r2b, text="Scenery:", font=("Microsoft YaHei UI", 9), fg="#aaa", bg="#16213e",
                 width=14, anchor="e").pack(side="left")
        self.scenery_var = tk.StringVar(value=self._fg.scenery_dir or "")
        self.scenery_entry = tk.Entry(r2b, textvariable=self.scenery_var, font=("Consolas", 9),
                                      bg="#0d1117", fg="#ddd", relief="solid", bd=0, width=38)
        self.scenery_entry.pack(side="left", padx=5)
        tk.Button(r2b, text="...", font=("Microsoft YaHei UI", 8), bg="#444", fg="#fff",
                  command=lambda: self._browse_dir(self.scenery_var)).pack(side="left")

        # Addon path --addon=
        r3 = tk.Frame(comp_frame, bg="#16213e")
        r3.pack(fill="x", padx=5, pady=1)
        tk.Label(r3, text="Addon (--addon=):", font=("Microsoft YaHei UI", 9), fg="#aaa", bg="#16213e",
                 width=14, anchor="e").pack(side="left")
        default_addon = str(self.repo_root / "client" / "ctf-addon")
        self.addon_var = tk.StringVar(value=default_addon)
        tk.Entry(r3, textvariable=self.addon_var, font=("Consolas", 9),
                 bg="#0d1117", fg="#ddd", relief="solid", bd=0, width=38).pack(side="left", padx=5)

        # Lock file
        r3b = tk.Frame(comp_frame, bg="#16213e")
        r3b.pack(fill="x", padx=5, pady=1)
        tk.Label(r3b, text="Lock file:", font=("Microsoft YaHei UI", 9), fg="#aaa", bg="#16213e",
                 width=14, anchor="e").pack(side="left")
        self.lock_var = tk.StringVar(value=str(self.repo_root / "env.lock"))
        tk.Entry(r3b, textvariable=self.lock_var, font=("Consolas", 9),
                 bg="#0d1117", fg="#ddd", relief="solid", bd=0, width=38).pack(side="left", padx=5)

        # Multiplay Out
        r4 = tk.Frame(comp_frame, bg="#16213e")
        r4.pack(fill="x", padx=5, pady=1)
        self.mp_out_enabled_var = tk.BooleanVar(value=True)
        tk.Checkbutton(r4, text="MP Out", variable=self.mp_out_enabled_var,
                       font=("Microsoft YaHei UI", 9), fg="#aaf", bg="#16213e",
                       selectcolor="#16213e").pack(side="left", padx=2)
        tk.Label(r4, text="Hz:", font=("Microsoft YaHei UI", 9), fg="#888", bg="#16213e").pack(side="left")
        self.mp_out_hz_var = tk.StringVar(value="10")
        tk.Entry(r4, textvariable=self.mp_out_hz_var, font=("Consolas", 9),
                 bg="#0d1117", fg="#ddd", relief="solid", bd=0, width=4).pack(side="left", padx=2)
        tk.Label(r4, text="Host:", font=("Microsoft YaHei UI", 9), fg="#888", bg="#16213e").pack(side="left", padx=2)
        self.mp_out_host_var = tk.StringVar(value="127.0.0.1")
        tk.Entry(r4, textvariable=self.mp_out_host_var, font=("Consolas", 9),
                 bg="#0d1117", fg="#ddd", relief="solid", bd=0, width=14).pack(side="left", padx=2)
        tk.Label(r4, text="Port:", font=("Microsoft YaHei UI", 9), fg="#888", bg="#16213e").pack(side="left", padx=2)
        self.mp_out_port_var = tk.StringVar(value="5000")
        tk.Entry(r4, textvariable=self.mp_out_port_var, font=("Consolas", 9),
                 bg="#0d1117", fg="#ddd", relief="solid", bd=0, width=6).pack(side="left", padx=2)

        # Multiplay In
        r5 = tk.Frame(comp_frame, bg="#16213e")
        r5.pack(fill="x", padx=5, pady=1)
        self.mp_in_enabled_var = tk.BooleanVar(value=True)
        tk.Checkbutton(r5, text="MP In", variable=self.mp_in_enabled_var,
                       font=("Microsoft YaHei UI", 9), fg="#aaf", bg="#16213e",
                       selectcolor="#16213e").pack(side="left", padx=2)
        tk.Label(r5, text="Hz:", font=("Microsoft YaHei UI", 9), fg="#888", bg="#16213e").pack(side="left")
        self.mp_in_hz_var = tk.StringVar(value="10")
        tk.Entry(r5, textvariable=self.mp_in_hz_var, font=("Consolas", 9),
                 bg="#0d1117", fg="#ddd", relief="solid", bd=0, width=4).pack(side="left", padx=2)
        tk.Label(r5, text="Port:", font=("Microsoft YaHei UI", 9), fg="#888", bg="#16213e").pack(side="left", padx=2)
        self.mp_in_port_var = tk.StringVar(value="5000")
        tk.Entry(r5, textvariable=self.mp_in_port_var, font=("Consolas", 9),
                 bg="#0d1117", fg="#ddd", relief="solid", bd=0, width=6).pack(side="left", padx=2)

        # ── Buttons ──
        tk.Frame(self.root, height=1, bg="#333").pack(fill="x", pady=6)
        btn_frame = tk.Frame(self.root, bg="#1a1a2e")
        btn_frame.pack(fill="x", padx=15, pady=3)
        self.btn_check = tk.Button(btn_frame, text="Self-Check", font=("Microsoft YaHei UI", 10),
                                   bg="#0a6", fg="white", command=self._run_check)
        self.btn_check.pack(side="left", padx=2, expand=True, fill="x")
        self.btn_session = tk.Button(btn_frame, text="Open Session", font=("Microsoft YaHei UI", 10),
                                     bg="#06a", fg="white", command=self._open_session)
        self.btn_session.pack(side="left", padx=2, expand=True, fill="x")
        self.btn_daemon = tk.Button(btn_frame, text="Start Daemon", font=("Microsoft YaHei UI", 10),
                                    bg="#950", fg="white", command=self._start_daemon)
        self.btn_daemon.pack(side="left", padx=2, expand=True, fill="x")
        self.btn_stop_daemon = tk.Button(btn_frame, text="Stop", font=("Microsoft YaHei UI", 10),
                                         bg="#555", fg="#aaa", command=self._stop_daemon, state="disabled")
        self.btn_stop_daemon.pack(side="left", padx=2, expand=True, fill="x")

        # ── Log ──
        tk.Label(self.root, text="LOG", font=("Microsoft YaHei UI", 9, "bold"),
                 fg="#888", bg="#1a1a2e").pack(anchor="w", padx=15, pady=3)
        self.log_text = tk.Text(self.root, height=6, font=("Consolas", 8), bg="#0d1117", fg="#bbb")
        self.log_text.pack(fill="both", expand=True, padx=15, pady=3)
        self.log_text.config(state="disabled")
        tk.Label(self.root, text="MAYDAY CTF ShanghaiTech 2026", font=("Microsoft YaHei UI", 8),
                 fg="#555", bg="#1a1a2e").pack(pady=3)

    def _browse_dir(self, var):
        path = filedialog.askdirectory(title="Select directory")
        if path:
            var.set(path)

    # ── Exe check ──────────────────────────────────────────────────
    def _check_exe(self):
        if self.exe_path.exists():
            size = self.exe_path.stat().st_size // 1024
            self.exe_status.config(text=f"anticheatd.exe found ({size} KB)", fg="#0f0")
        else:
            self.exe_status.config(text="anticheatd.exe NOT FOUND", fg="#f44")

    # ── Log ────────────────────────────────────────────────────────
    def _log(self, msg):
        self.log_text.config(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {msg}\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    # ── Display update ─────────────────────────────────────────────
    def _update_display(self, json_data):
        if not json_data or "checks" not in json_data:
            return
        layer_alias = {"Anti-VM": "VM"}
        for check in json_data["checks"]:
            layer = check.get("layer", "")
            layer = layer_alias.get(layer, layer)
            passed = check.get("passed", False)
            lbl = self.layer_labels.get(layer)
            if lbl:
                symbol = "\u2714" if passed else "\u2718"
                color = "#0f0" if passed else "#f44"
                lbl.config(text=symbol, fg=color)

    # ── Self-Check ─────────────────────────────────────────────────
    def _run_check(self):
        self.btn_check.config(state="disabled")
        self._log("Running anticheatd.exe --mode selfcheck --json ...")
        for k in self.layer_labels:
            self.layer_labels[k].config(text="...", fg="#fa0")

        cmd = [str(self.exe_path), "--mode", "selfcheck", "--json"] + self._build_comp_args()

        def _do():
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                stdout = r.stdout.strip()
                stderr = r.stderr.strip()
                if stderr:
                    self._log(stderr)
                if stdout:
                    self._log("(stdout omitted, see dashboard)")

                jd = None
                for src in (stdout, stdout + "\n" + stderr):
                    try:
                        s = src.find('{')
                        e = src.rfind('}') + 1
                        if s >= 0 and e > s:
                            jd = json.loads(src[s:e])
                            break
                    except json.JSONDecodeError:
                        continue
                if jd:
                    self._update_display(jd)
                    self._log(f"Display: {jd.get('passed',0)}/{jd.get('total',0)} passed")
                else:
                    self._log("Parse error: no valid JSON found")
            except Exception as ex:
                self._log(f"Error: {ex}")
            finally:
                self.btn_check.config(state="normal")
        threading.Thread(target=_do, daemon=True).start()

    # ── Open Session ───────────────────────────────────────────────
    def _open_session(self):
        self.btn_session.config(state="disabled")
        userid = self.uid_entry.get().strip() or "GUEST"
        self._log(f"Opening session (userid={userid})...")

        cmd = [str(self.exe_path), "--mode", "session", "--json",
               "--userid", userid] + self._build_comp_args()

        def _do():
            try:
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

    # ── Daemon ─────────────────────────────────────────────────────
    def _start_daemon(self):
        if self.daemon_proc is not None:
            self._log("Daemon already running.")
            return
        self.btn_daemon.config(state="disabled")
        self.btn_stop_daemon.config(state="normal", bg="#c33", fg="white")

        cmd = [str(self.exe_path), "--mode", "daemon", "--json"] + self._build_comp_args()
        self._log(f"Starting daemon: {' '.join(cmd)}")

        def _do():
            try:
                self.daemon_proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1
                )
                for line in iter(self.daemon_proc.stdout.readline, ''):
                    self._log(line.rstrip())
                self.daemon_proc.stdout.close()
                self.daemon_proc.wait()
                self._log(f"Daemon exited (rc={self.daemon_proc.returncode})")
            except Exception as ex:
                self._log(f"Daemon error: {ex}")
            finally:
                self.daemon_proc = None
                self.btn_daemon.config(state="normal")
                self.btn_stop_daemon.config(state="disabled", bg="#555", fg="#aaa")
        threading.Thread(target=_do, daemon=True).start()

    def _stop_daemon(self):
        if self.daemon_proc is None:
            return
        self._log("Stopping daemon...")
        try:
            self.daemon_proc.terminate()
            self.daemon_proc.wait(timeout=5)
        except Exception:
            try:
                self.daemon_proc.kill()
            except Exception:
                pass
        self.daemon_proc = None
        self.btn_daemon.config(state="normal")
        self.btn_stop_daemon.config(state="disabled", bg="#555", fg="#aaa")
        self._log("Daemon stopped.")

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