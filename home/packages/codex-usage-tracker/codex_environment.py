"""Offline operational-energy subset adapted from EcoLogits (MPL-2.0).

Copyright (c) 2024-2026 GenAI Impact and contributors.
Modifications: standalone stdlib implementation and report aggregation, 2026.
This file is subject to the Mozilla Public License, v. 2.0; see
LICENSE-EcoLogits or https://mozilla.org/MPL/2.0/.
Method and model data pinned to EcoLogits revision below. This is not the full
EcoLogits lifecycle estimator, nor a measurement of OpenAI infrastructure.
"""
import json
import math
from pathlib import Path

REVISION = "3a8e85ca7970c439d00ee44cfb1c5b29fd1afeff"
METHOD = f"https://github.com/genai-impact/ecologits/blob/{REVISION}/ecologits/impacts/llm.py"
# Explicit illustrative assumptions, not observations of the serving datacenter.
PUE = 1.2
DEFAULT_GRID = 400.0  # gCO2e/kWh, illustrative electricity-intensity scenario
# UK DESNZ 2026 methodology: rounded tabulated long-haul economy
# factors before distance uplift. Apply RF only to CO2, not other GHGs.
FLIGHT_SOURCE = "https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2026"
FLIGHT_CO2_KG_PER_PKM = 0.0632
FLIGHT_OTHER_KG_CO2E_PER_PKM = 0.0005
FLIGHT_RF = 1.7
FLIGHT_KMH = 800  # illustrative effective airborne speed, not a measured route
FLIGHT_KG_CO2E_PER_HOUR = (FLIGHT_CO2_KG_PER_PKM * FLIGHT_RF
                           + FLIGHT_OTHER_KG_CO2E_PER_PKM) * FLIGHT_KMH


def catalog():
    data = json.loads(Path(__file__).with_name("environment_models.json").read_text())
    if data["revision"] != REVISION:
        raise ValueError("Environmental catalog revision mismatch")
    models = {m["name"]: m for m in data["models"]}
    for alias in data["aliases"]:
        if alias["alias"] in models:
            models[alias["name"]] = models[alias["alias"]]
    return models


def energy(model, output):
    """Return Wh endpoints for positive recorded output, including reasoning.

    Matches the pinned EcoLogits operational energy equations: H100 80GB,
    FP16, batch 64, 1.2kW non-GPU server/8 GPUs, estimated serving latency
    without a measured request-latency cap. No input/cache energy adjustment.
    Ranges vary inferred parameter counts only; not confidence bounds.
    """
    if output is None or output <= 0:
        return None
    params = model["architecture"]["parameters"]
    total = params.get("total", params)
    active = params.get("active", total)

    def endpoints(value):
        return (value["min"], value["max"]) if isinstance(value, dict) else (value, value)

    deployment = model.get("deployment") or {}
    values = []
    for a, t in zip(endpoints(active), endpoints(total)):
        gpus = 2 ** math.ceil(math.log2(math.ceil(1.2 * t * 16 / 8 / 80)))
        gpu_wh = output * (1.1665273170451914e-6 * math.exp(-0.011205921025579175 * 64)
                           * a + 4.052928146734005e-5)
        tps = deployment.get("tps")
        seconds_per_token = 1 / tps if tps else (0.0006785088094353663 * a
                                                + 0.0003119310311688259 * 64
                                                + 0.019473717579473387)
        seconds = output * seconds_per_token + (deployment.get("ttft") or 0)
        host_wh = seconds / 3600 * 1200 * (gpus / 8) / 64
        values.append(PUE * (gpus * gpu_wh + host_wh))
    return min(values), max(values)


def empty():
    return {"calls": 0, "covered": 0, "output": 0, "covered_output": 0,
            "missing": 0, "zero": 0, "lo": 0.0, "hi": 0.0}


def add(target, value):
    for key in target:
        target[key] += value[key]


def summarize(records, scopes, models):
    """Aggregate per-request model estimates; never allocate by output share."""
    groups, unsupported, warnings = {}, {}, set()
    for record in records:
        scope = scopes.get(record["key"], ("unmatched", None))
        totals = groups.setdefault(scope, empty())
        totals["calls"] += 1
        output = record["output"]
        totals["output"] += output or 0
        # A concrete but unsupported response model must not fall back to a
        # supported requested model: it might have very different architecture.
        name = record["response_model"] or record["model"]
        model = models.get(name)
        if output is None:
            totals["missing"] += 1
        elif output == 0:
            totals["zero"] += 1
        if model is None:
            unsupported[name] = unsupported.get(name, 0) + 1
        estimate = energy(model, output) if model else None
        if estimate is not None:
            totals["covered"] += 1
            totals["covered_output"] += output
            totals["lo"] += estimate[0]
            totals["hi"] += estimate[1]
            warnings.update(model.get("warnings") or [])
    total = empty()
    for group in groups.values():
        add(total, group)
    return groups, total, unsupported, warnings


def percent(numerator, denominator):
    return f"{100 * numerator / denominator:.1f}%" if denominator else "N/A"


def cells(totals, grid):
    if not totals["covered"]:
        return "unknown | unknown | 0/{}".format(totals["calls"])
    return (f"{totals['lo']:.2g}–{totals['hi']:.2g} | "
            f"{totals['lo'] * grid / 1000:.2g}–{totals['hi'] * grid / 1000:.2g} | "
            f"{totals['covered']}/{totals['calls']}")


def readable(value):
    """Two significant figures without hard-to-read scientific notation."""
    rounded = float(f'{value:.2g}')
    places = max(0, 1 - math.floor(math.log10(abs(rounded)))) if rounded else 0
    return f"{rounded:,.{places}f}"


def quantity_range(lo, hi, unit):
    return f"{readable(lo)}–{readable(hi)} {unit}"


def flight_hours(total, grid):
    """Per-passenger climate-equivalent hours, not actual flight/whole-plane time."""
    if not total['covered']:
        return None
    # Wh * (g/kWh) / 1e6 = kg CO2e.
    return tuple(total[k] * grid / 1e6 / FLIGHT_KG_CO2E_PER_HOUR for k in ('lo', 'hi'))


def summary(total, unsupported, warnings, grid, period, details=False):
    print(f"\nEnvironmental estimate — {period}")
    if total['covered']:
        energy_unit, energy_scale = ('kWh', 1000) if total['hi'] >= 1000 else ('Wh', 1)
        carbon_hi = total['hi'] * grid / 1000  # g CO2e
        carbon_unit, carbon_scale = ('kg CO2e', 1000) if carbon_hi >= 1000 else ('g CO2e', 1)
        electricity = quantity_range(total['lo'] / energy_scale, total['hi'] / energy_scale, energy_unit)
        carbon = quantity_range(total['lo'] * grid / 1000 / carbon_scale,
                                carbon_hi / carbon_scale, carbon_unit)
        print(f"Covered operational subtotal: {electricity}; {carbon} (scenario, not measured).")
        lo, hi = flight_hours(total, grid)
        # Weekly comparisons are often minutes, not hours; retain readable units.
        unit, scale = ('hours', 1) if hi >= 1 else ('minutes', 60)
        print(f"Equivalent flight time: {quantity_range(lo * scale, hi * scale, unit)} for ONE "
              "long-haul economy passenger, including non-CO2 warming allowance.")
    else:
        print("Covered operational subtotal: unknown; equivalent flight time: unknown (not zero).")
    if details:
        return  # The detailed introduction below supplies coverage, warnings and caveats.
    print(f"Estimate coverage: {total['covered']:,}/{total['calls']:,} calls; "
          f"{percent(total['covered_output'], total['output'])} of recorded output. "
          f"Unknown output {total['missing']:,}; zero-output unestimated {total['zero']:,}.")
    print(f"Assumptions: grid {grid:g} g CO2e/kWh, PUE {PUE:g}; flight ~{FLIGHT_KMH} km/h, "
          f"UK2026 long-haul economy factors + {FLIGHT_RF:g}x CO2 warming multiplier.")
    print("Scenario ranges, NOT confidence bounds. Prefill/cache effects unmodeled; "
          "excludes training, hardware manufacture, idle reserves, water, laptop/tools and other clients.")
    if unsupported:
        print("Unsupported models (unknown, not zero): " + "; ".join(
            f"{name}: {count:,} calls" for name, count in sorted(unsupported.items())))
    if warnings:
        print("Source warnings: " + ", ".join(sorted(warnings)))
    print("Methods: EcoLogits " + REVISION[:12] + "; flight: " + FLIGHT_SOURCE
          + " (use --environment for detailed assumptions/tables).")


def introduction(total, unsupported, warnings, grid):
    print("\nEnvironmental scenario — ESTIMATED operational inference only, not measured")
    print("Covered subtotal: Wh | g CO2e | estimated/recorded calls")
    print(cells(total, grid))
    print(f"Estimate coverage: {total['covered']:,}/{total['calls']:,} calls "
          f"({percent(total['covered'], total['calls'])}); "
          f"{percent(total['covered_output'], total['output'])} of recorded output.")
    print(f"Unknown output: {total['missing']:,} calls; zero-output calls not estimated: {total['zero']:,}.")
    print(f"Assumed grid: {grid:g} g CO2e/kWh; PUE {PUE:g}; H100 FP16; batch 64.")
    print("Ranges vary inferred model parameters only, NOT confidence intervals or bounds on actual impact.")
    print("Long-context prefill/cache effects are not modeled; reasoning is included once in output.")
    print("Excludes training, hardware manufacture, idle reserves, water, laptop/tools and other clients.")
    print("Serving hardware/location/batching are unknown; carbon is a conditional electricity scenario.")
    if unsupported:
        print("Unsupported models (unknown, not zero): " + "; ".join(
            f"{name}: {count:,} calls" for name, count in sorted(unsupported.items())))
    if warnings:
        print("Source warnings: " + ", ".join(sorted(warnings)))
    print(f"Method/data: EcoLogits {REVISION[:12]} (MPL-2.0); {METHOD}")
    print(f"Flight comparison: UK2026 long-haul economy {FLIGHT_CO2_KG_PER_PKM:g} kg CO2/pkm "
          f"+ {FLIGHT_OTHER_KG_CO2E_PER_PKM:g} kg CO2e/pkm other GHGs; "
          f"CO2-only warming multiplier {FLIGHT_RF:g}; assumed {FLIGHT_KMH} km/h.")
    print(f"Flight method: {FLIGHT_SOURCE}; no extra distance uplift on assumed airborne km.")
