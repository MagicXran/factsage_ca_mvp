# -*- coding: utf-8 -*-
"""
Parse FactSage Equilib XML (FactSage 8.4) for the Ca estimate example.

Outputs:
- summary.csv: one row with alpha (Ca needed), steel composition wt%, oxygen ppm,
  slag composition wt%.
"""
from __future__ import annotations
import csv
import xml.etree.ElementTree as ET
from pathlib import Path

def parse_equilib_xml(xml_path: Path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    header = root.find("header")
    page = root.find("page")
    if header is None or page is None:
        raise ValueError("Unexpected XML structure: missing <header> or <page>")

    alpha = float(page.attrib.get("alpha", "nan"))
    T = float(page.attrib.get("T", "nan"))
    P = float(page.attrib.get("P", "nan"))

    spec_def = header.find("species_definition")
    if spec_def is None:
        raise ValueError("Missing <species_definition> in <header>")

    # Map species id -> phase_id (solution phase)
    species_to_phase = {}
    phaseid_to_state = {}
    for sol in spec_def.findall("solution"):
        pid = sol.attrib.get("phase_id")
        st = sol.attrib.get("state", "")
        if pid:
            phaseid_to_state[pid] = st
        for sp in sol.iter("species"):
            sid = sp.attrib.get("id")
            if sid and pid:
                species_to_phase[sid] = pid

    # Map species id -> human name
    species_name = {}
    for sp in header.iter("species"):
        sid = sp.attrib.get("id")
        if sid and sid not in species_name:
            species_name[sid] = sp.attrib.get("name", sid)

    # Identify phase ids
    steel_pid = None
    slag_pid = None
    for pid, st in phaseid_to_state.items():
        if "Fe-liq" in st:
            steel_pid = pid
        # pick the main liquid slag (#1) if present
        if "Slag-liq#1" in st:
            slag_pid = pid
    if steel_pid is None:
        raise ValueError("Cannot find steel liquid phase (state contains 'Fe-liq')")
    if slag_pid is None:
        # fallback: any slag-liq
        for pid, st in phaseid_to_state.items():
            if "Slag-liq" in st:
                slag_pid = pid
                break

    # Collect masses per phase
    phase_total_g = {}
    phase_species_g = {}
    for r in page.findall("result"):
        sid = r.attrib.get("id")
        if not sid:
            continue
        pid = species_to_phase.get(sid)
        if not pid:
            continue
        g = float(r.attrib.get("g", "0") or 0)
        phase_total_g[pid] = phase_total_g.get(pid, 0.0) + g
        phase_species_g.setdefault(pid, {})[species_name.get(sid, sid)] = (
            phase_species_g.setdefault(pid, {}).get(species_name.get(sid, sid), 0.0) + g
        )

    def wt_pct(phase_id: str, species: str) -> float:
        tot = phase_total_g.get(phase_id, 0.0)
        if tot <= 0:
            return 0.0
        return 100.0 * phase_species_g.get(phase_id, {}).get(species, 0.0) / tot

    steel_tot = phase_total_g.get(steel_pid, 0.0)
    slag_tot = phase_total_g.get(slag_pid, 0.0) if slag_pid else 0.0

    # Key steel elements in this case
    steel_keys = ["Fe", "Mn", "Si", "Al", "O", "S"]
    steel_wt = {f"steel_{k}_wtpct": wt_pct(steel_pid, k) for k in steel_keys}
    steel_wt["steel_O_ppm"] = steel_wt["steel_O_wtpct"] * 1e4

    # Key slag oxides / sulfides
    slag_keys = ["CaO", "Al2O3", "SiO2", "MnO", "FeO", "CaS", "Al2S3", "SiS2"]
    slag_wt = {f"slag_{k}_wtpct": wt_pct(slag_pid, k) for k in slag_keys} if slag_pid else {}

    out = {
        "alpha_Ca_g": alpha,
        "T_K": T,
        "P_atm": P,
        "steel_total_g": steel_tot,
        "slag_total_g": slag_tot,
        **steel_wt,
        **slag_wt,
    }
    return out

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("xml", type=Path, help="FactSage Equilib XML result file")
    ap.add_argument("--out", type=Path, default=Path("summary.csv"))
    args = ap.parse_args()

    row = parse_equilib_xml(args.xml)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        w.writeheader()
        w.writerow(row)
    print(f"Wrote {args.out}")

if __name__ == "__main__":
    main()
