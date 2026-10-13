#!/usr/bin/env python3
"""Verify generate_micro_insight() produces dynamic, per-province text.

Extracts the function source from app.py and execs it in isolation,
avoiding the full app import (which triggers bootstrap + scheduler).
"""
import ast
import sys

def extract_function(source, func_name):
    """Extract a function's source from a module without executing the module."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            # Get source lines
            lines = source.splitlines()
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    raise ValueError(f"Function {func_name} not found")

def extract_constant(source, const_name):
    """Extract a module-level constant."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == const_name:
                    lines = source.splitlines()
                    return "\n".join(lines[node.lineno - 1:node.end_lineno])
    raise ValueError(f"Constant {const_name} not found")

with open("app.py") as f:
    source = f.read()

func_src = extract_function(source, "generate_micro_insight")
proj_src = extract_constant(source, "PROJECTION")

ns = {}
exec(proj_src, ns)
exec(func_src, ns)
generate_micro_insight = ns["generate_micro_insight"]

# Test with DKI Jakarta
metrics_jkt = {
    "province": "DKI Jakarta",
    "ump_monthly": 3643000,
    "bbm_price": 10000,
    "liters_per_ump": 364.3,
    "hours_per_liter": 2.7,
    "bbm_index_2014": 150.0,
    "wage_index_2014": 130.0,
    "bbm_burden": 4.0,
    "monthly_consumption": 20,
    "monthly_expenditure": 5000000,
}

# Test with Aceh (lower UMP)
metrics_aceh = {
    "province": "Aceh",
    "ump_monthly": 2300000,
    "bbm_price": 10000,
    "liters_per_ump": 230.0,
    "hours_per_liter": 4.3,
    "bbm_index_2014": 140.0,
    "wage_index_2014": 135.0,
    "bbm_burden": 5.2,
    "monthly_consumption": 20,
    "monthly_expenditure": 4200000,
}

insight_jkt = generate_micro_insight(metrics_jkt, ikk_latest={"value": 105.0})
insight_aceh = generate_micro_insight(metrics_aceh, ikk_latest={"value": 95.0})

print("=== DKI Jakarta ===")
print(insight_jkt)
print()
print("=== Aceh ===")
print(insight_aceh)
print()

# Assertions
errors = []

def check(condition, msg):
    if condition:
        print(f"[PASS] {msg}")
    else:
        errors.append(msg)
        print(f"[FAIL] {msg}")

check("DKI Jakarta" in insight_jkt, "Jakarta insight mentions province")
check("Aceh" in insight_aceh, "Aceh insight mentions province")
check("364" in insight_jkt, "Jakarta shows ~364 liters")
check("230" in insight_aceh, "Aceh shows ~230 liters")
check(insight_jkt != insight_aceh, "Insights differ between provinces")
check("naik lebih cepat" in insight_jkt or "naik lebih lambat" in insight_jkt or "seimbang" in insight_jkt,
      "BBM vs upah comparison present")
check("beban" in insight_jkt.lower(), "Beban BBM mentioned")
check("jam" in insight_jkt.lower(), "Jam kerja mentioned")
check("105" in insight_jkt, "IKK > 100 shows value")
check("95" in insight_aceh, "IKK < 100 shows value")

# Test IKK branch differences
check("optimis" in insight_jkt.lower(), "IKK > 100 uses 'optimis'")
check("melemah" in insight_aceh.lower(), "IKK < 100 uses 'melemah'")

print()
if errors:
    print(f"FAILED: {len(errors)} check(s) failed")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
    sys.exit(0)
