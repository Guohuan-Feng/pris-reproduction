"""Make standalone figures from independently recomputed numerical results."""
from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    result = ROOT / "results" / "eos"
    d = pd.read_csv(result / "per_candidate.csv")
    s = json.loads((result / "summary.json").read_text())
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.7), constrained_layout=True)
    ax = axes[0]
    ax.scatter(d.published_b0_gpa, d.refit_b0_gpa, s=18, alpha=.75, color="#176d7e")
    lo, hi = d.published_b0_gpa.min()-5, d.published_b0_gpa.max()+5
    ax.plot([lo, hi], [lo, hi], color="#a3a9ad", linestyle="--", linewidth=1)
    ax.set(xlabel="Published bulk modulus (GPa)", ylabel="Independently refitted modulus (GPa)",
           title="All 260 moduli reproduced")
    ax.text(.04, .96, f"Max absolute difference: {s['b0_absolute_error_gpa_max']:.6f} GPa", transform=ax.transAxes, va="top", fontsize=9)
    ax = axes[1]
    ordered = d.sort_values("refit_b0_gpa").reset_index(drop=True)
    for role, color, marker in [("control", "#8d969d", "."), ("priority", "#177486", "o"), ("screened", "#b64a37", "x")]:
        mask = ordered.role == role
        ax.scatter(ordered.index[mask], ordered.loc[mask,"refit_b0_gpa"], s=22, color=color, marker=marker, label=role)
    ax.axhline(400, color="#222222", linestyle="--", linewidth=1, label="Original 400 GPa")
    ax.axhline(s["mapped_dft_threshold_gpa"], color="#9d7d21", linestyle=":", linewidth=1.3, label="Mapped 375.819 GPa")
    ax.set(xlabel="Candidate rank by recomputed modulus", ylabel="Bulk modulus (GPa)",
           title="Screening interpretation depends on threshold")
    ax.legend(fontsize=8, loc="lower right")
    for ax in axes:
        ax.spines[["right", "top"]].set_visible(False)
    fig.supxlabel("Independent BM3 refit of published energy-volume values; no new DFT. Selected E4 sample, n=260.", fontsize=9)
    fig.savefig(result / "eos_reproduction.png", dpi=180)
    plt.close(fig)
    validation = ROOT / "results" / "core_validation"
    s = json.loads((validation / "results.json").read_text())
    cases = s["same_NaCl_geometry"]
    labels = ["Primitive\n2 sites", "Conventional\n8 sites", "Primitive supercell\n16 sites"]
    keys = ["primitive", "conventional", "primitive_2x2x2"]
    values = [cases[k]["law7"]["value"] for k in keys]
    fig, ax = plt.subplots(figsize=(7.2, 4.3), constrained_layout=True)
    ax.bar(labels, values, color=["#b64a37", "#176d7e", "#176d7e"], width=.55)
    ax.axhline(2/3, linestyle="--", color="#444444", label="Law 7 threshold: 2/3")
    for x, value, key in zip(range(3), values, keys):
        ax.text(x, value+.025, f"{value:.3f}: {cases[key]['verdict']}", ha="center", fontsize=9)
    ax.set(ylim=(0, 1.15), ylabel="Inequivalent sites / input sites", title="Same NaCl crystal, different upstream Set 4 verdict")
    ax.legend(loc="upper right", fontsize=9)
    ax.spines[["right", "top"]].set_visible(False)
    fig.supxlabel("Synthetic geometry control. All other seven laws are unchanged. Upstream code left unmodified.", fontsize=9)
    fig.savefig(validation / "cell_representation.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
