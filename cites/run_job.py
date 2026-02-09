# -*- coding: utf-8 -*-
"""
Render .equi and .mac from templates and run FactSage Equilib in batch mode.

Assumptions:
- FactSage installed at C:\FactSage
- You run this script on Windows
- You have a standalone/dongle installation that supports batch macro processing

Usage:
  python run_job.py jobs\example_deoxidation.json --factsage-dir C:\FactSage --work-root C:\demo\jobs

Each job gets an isolated folder:
  <work_root>\<job_id>\input, <work_root>\<job_id>\out
"""
from __future__ import annotations
import json, subprocess, uuid
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, Optional

from jinja2 import Template

def _read_text(path: Path) -> str:
    # IMPORTANT: no UTF-8 BOM, FactSage macro parser will choke on it.
    return path.read_text(encoding="utf-8")

def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write UTF-8 without BOM; keep CRLF for Windows friendliness
    text = text.replace("\n", "\r\n")
    path.write_text(text, encoding="utf-8", newline="")

def render_template(template_path: Path, params: Dict[str, Any]) -> str:
    t = Template(_read_text(template_path))
    return t.render(**params)

def run_factsage_macro(
    factsage_dir: Path,
    macro_path: Path,
    cwd: Optional[Path] = None,
    hide_window: bool = True,
) -> int:
    exe = factsage_dir / "EquiSage.exe"
    if not exe.exists():
        raise FileNotFoundError(f"Cannot find EquiSage.exe under: {factsage_dir}")

    cmd = [str(exe), "/EQUILIB", "/MACRO", str(macro_path)]
    # FactSage needs to run with CWD at factsage dir (Initialize.ini, FACTHELP, etc.)
    workdir = str(cwd or factsage_dir)

    # Hide/minimize (best effort). EquiSage is a GUI app; SW_HIDE usually works.
    startupinfo = None
    creationflags = 0
    if hide_window:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE

    p = subprocess.Popen(cmd, cwd=workdir, startupinfo=startupinfo, creationflags=creationflags)
    return p.wait()

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("job_json", type=Path)
    ap.add_argument("--factsage-dir", type=Path, default=Path(r"C:\FactSage"))
    ap.add_argument("--work-root", type=Path, default=Path(r"C:\demo\jobs"))
    ap.add_argument("--templates-dir", type=Path, default=Path("templates"))
    ap.add_argument("--hide-window", action="store_true", default=True)
    ap.add_argument("--no-hide-window", dest="hide_window", action="store_false")
    args = ap.parse_args()

    job = json.loads(args.job_json.read_text(encoding="utf-8"))
    job_id = job.get("job_id") or uuid.uuid4().hex[:8]
    prefix = job.get("prefix", "case")
    # folders
    job_dir = args.work_root / job_id
    in_dir = job_dir / "input"
    out_dir = job_dir / "out"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    # render equi
    equi_params = {
        "alpha_guess": job.get("alpha_guess", 0.5),
        "Fe_g": job["steel"]["Fe_g"],
        "Mn_field": job["steel"].get("Mn_field", ""),  # empty string => "balance" in the original example
        "Si_g": job["steel"]["Si_g"],
        "Al_g": job["steel"]["Al_g"],
        "O_g": job["steel"]["O_g"],
        "S_g": job["steel"]["S_g"],
        "CaO_g": job["slag"]["CaO_g"],
        "Al2O3_g": job["slag"]["Al2O3_g"],
        "SiO2_g": job["slag"]["SiO2_g"],
        "T_C": job["conditions"]["T_C"],
        "P_atm": job["conditions"].get("P_atm", 1.0),
        "target_elem": job["target"]["element"],
        "target_value": job["target"]["value"],
    }
    equi_text = render_template(args.templates_dir / "ca_equilib_estimate.equi.j2", equi_params)
    equi_path = in_dir / f"{prefix}.equi"
    _write_text(equi_path, equi_text)

    # render macro
    mac_params = {
        "equi_file": str(equi_path),
        "out_dir": str(out_dir) + "\\",
        "prefix": prefix,
        "T_C": job["conditions"]["T_C"],
        "P_atm": job["conditions"].get("P_atm", 1.0),
    }
    mac_text = render_template(args.templates_dir / "run_equilib.mac.j2", mac_params)
    mac_path = in_dir / f"{prefix}.mac"
    _write_text(mac_path, mac_text)

    # run
    rc = run_factsage_macro(args.factsage_dir, mac_path, cwd=args.factsage_dir, hide_window=args.hide_window)
    if rc != 0:
        raise SystemExit(f"FactSage exited with code {rc}")

    print(f"Job done. Outputs in: {out_dir}")

if __name__ == "__main__":
    main()
