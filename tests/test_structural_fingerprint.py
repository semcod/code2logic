"""
Tests for read-only CFG and DFG structural fingerprints for semantic retrieval candidates (PLF-006 / Issue #9).
"""

from __future__ import annotations

import json
from pathlib import Path

from code2logic.core import (
    ADVISORY_AUTHORITY,
    STRUCTURAL_EXPORT_SCHEMA,
    STRUCTURAL_FINGERPRINT_SCHEMA,
    STRUCTURAL_SIMILARITY_SCHEMA,
    compare_structural_fingerprints,
    export_structural_fingerprints,
    extract_structural_fingerprints_from_source,
    rank_retrieval_candidates,
)


ALPHA_EQUIVALENT_A = '''
def compute_discounted_total(prices: list[float], discount_rate: float) -> float:
    """Compute total price after applying discount rate to positive entries."""
    running_total = 0.0
    for unit_price in prices:
        if unit_price > 0:
            discounted = unit_price * (1.0 - discount_rate)
            running_total += discounted
        else:
            continue
    return round(running_total, 2)
'''

ALPHA_EQUIVALENT_B = '''
def calculate_rebated_sum(amounts: list[float], rebate_fraction: float) -> float:
    """Different docstring and completely alpha-renamed identifiers."""
    accum = 0.0
    for item_amount in amounts:
        # Comment that must not affect structural fingerprint
        if item_amount > 0:
            adjusted = item_amount * (1.0 - rebate_fraction)
            accum += adjusted
        else:
            continue
    return round(accum, 2)
'''

RECURSIVE_EQUIVALENT_A = '''
def factorial_calc(n: int) -> int:
    if n <= 1:
        return 1
    prev = factorial_calc(n - 1)
    return n * prev
'''

RECURSIVE_EQUIVALENT_B = '''
def product_sequence(count: int) -> int:
    """Alpha-renamed recursive function."""
    if count <= 1:
        return 1
    sub_result = product_sequence(count - 1)
    return count * sub_result
'''

NEGATIVE_BRANCH_OPERATOR = '''
def compute_discounted_total(prices: list[float], discount_rate: float) -> float:
    running_total = 0.0
    for unit_price in prices:
        if unit_price >= 0:
            discounted = unit_price * (1.0 - discount_rate)
            running_total += discounted
        else:
            continue
    return round(running_total, 2)
'''

NEGATIVE_DATAFLOW_REWIRE = '''
def compute_discounted_total(prices: list[float], discount_rate: float) -> float:
    running_total = 0.0
    for unit_price in prices:
        if unit_price > 0:
            discounted = unit_price * (1.0 - discount_rate)
            running_total += unit_price
        else:
            continue
    return round(running_total, 2)
'''

NEGATIVE_SIDE_EFFECT = '''
def compute_discounted_total(prices: list[float], discount_rate: float) -> float:
    running_total = 0.0
    for unit_price in prices:
        if unit_price > 0:
            discounted = unit_price * (1.0 - discount_rate)
            running_total += discounted
        else:
            raise ValueError("negative price")
    return round(running_total, 2)
'''


def test_alpha_renaming_equivalent_positive_fixtures() -> None:
    fps_a = extract_structural_fingerprints_from_source(
        ALPHA_EQUIVALENT_A, module_path="billing/pricing.py"
    )
    fps_b = extract_structural_fingerprints_from_source(
        ALPHA_EQUIVALENT_B, module_path="orders/rebates.py"
    )
    assert len(fps_a) == 1
    assert len(fps_b) == 1

    fp_a = fps_a[0]
    fp_b = fps_b[0]

    assert fp_a.schema == STRUCTURAL_FINGERPRINT_SCHEMA
    assert fp_a.read_only is True
    assert fp_a.authority == ADVISORY_AUTHORITY
    assert fp_a.grants_authority is False

    # Raw source hashes must differ because identifiers/docstrings differ
    assert fp_a.source_sha256 != fp_b.source_sha256
    assert fp_a.module_source_sha256 != fp_b.module_source_sha256

    # Alpha-normalized structural hashes must match across CFG, DFG, I/O, and effects
    assert fp_a.cfg_fingerprint == fp_b.cfg_fingerprint
    assert fp_a.dfg_fingerprint == fp_b.dfg_fingerprint
    assert fp_a.io_fingerprint == fp_b.io_fingerprint
    assert fp_a.effects_fingerprint == fp_b.effects_fingerprint
    assert fp_a.normalized_ast_sha256 == fp_b.normalized_ast_sha256
    assert fp_a.combined_fingerprint == fp_b.combined_fingerprint

    match = compare_structural_fingerprints(fp_a, fp_b)
    assert match.schema == STRUCTURAL_SIMILARITY_SCHEMA
    assert match.read_only is True
    assert match.authority == ADVISORY_AUTHORITY
    assert match.grants_authority is False
    assert match.exact_structural_match is True
    assert match.cfg_match is True
    assert match.dfg_match is True
    assert match.io_match is True
    assert match.effects_match is True
    assert match.overall_similarity == 1.0


def test_recursive_self_call_alpha_equivalence() -> None:
    fp_a = extract_structural_fingerprints_from_source(RECURSIVE_EQUIVALENT_A)[0]
    fp_b = extract_structural_fingerprints_from_source(RECURSIVE_EQUIVALENT_B)[0]

    assert fp_a.source_sha256 != fp_b.source_sha256
    assert fp_a.combined_fingerprint == fp_b.combined_fingerprint
    assert "$self_fn" in fp_a.effects.calls


def test_behavior_changing_negative_fixtures_diverge() -> None:
    baseline = extract_structural_fingerprints_from_source(ALPHA_EQUIVALENT_A)[0]
    branch_changed = extract_structural_fingerprints_from_source(NEGATIVE_BRANCH_OPERATOR)[0]
    dfg_rewired = extract_structural_fingerprints_from_source(NEGATIVE_DATAFLOW_REWIRE)[0]
    effect_added = extract_structural_fingerprints_from_source(NEGATIVE_SIDE_EFFECT)[0]

    # 1. Branch operator change (> vs >=) alters CFG and combined fingerprint
    assert baseline.cfg_fingerprint != branch_changed.cfg_fingerprint
    assert baseline.combined_fingerprint != branch_changed.combined_fingerprint
    branch_cmp = compare_structural_fingerprints(baseline, branch_changed)
    assert branch_cmp.exact_structural_match is False
    assert branch_cmp.cfg_match is False

    # 2. Data-flow dependency rewiring alters DFG and combined fingerprint
    assert baseline.dfg_fingerprint != dfg_rewired.dfg_fingerprint
    assert baseline.combined_fingerprint != dfg_rewired.combined_fingerprint
    dfg_cmp = compare_structural_fingerprints(baseline, dfg_rewired)
    assert dfg_cmp.exact_structural_match is False
    assert dfg_cmp.dfg_match is False

    # 3. Replacing continue with raise ValueError alters effects and CFG fingerprints
    assert baseline.effects_fingerprint != effect_added.effects_fingerprint
    assert baseline.cfg_fingerprint != effect_added.cfg_fingerprint
    assert baseline.combined_fingerprint != effect_added.combined_fingerprint
    eff_cmp = compare_structural_fingerprints(baseline, effect_added)
    assert eff_cmp.exact_structural_match is False
    assert eff_cmp.effects_match is False
    assert eff_cmp.cfg_match is False


def test_export_bundle_and_candidate_ranking(tmp_path: Path) -> None:
    mod_a = tmp_path / "alpha.py"
    mod_b = tmp_path / "beta.py"
    mod_a.write_text(ALPHA_EQUIVALENT_A + "\n" + RECURSIVE_EQUIVALENT_A, encoding="utf-8")
    mod_b.write_text(
        ALPHA_EQUIVALENT_B + "\n" + NEGATIVE_BRANCH_OPERATOR + "\n" + NEGATIVE_SIDE_EFFECT,
        encoding="utf-8",
    )

    bundle = export_structural_fingerprints(tmp_path)
    assert bundle.schema == STRUCTURAL_EXPORT_SCHEMA
    assert bundle.read_only is True
    assert bundle.authority == ADVISORY_AUTHORITY
    assert bundle.grants_authority is False
    assert len(bundle.candidates) == 5

    serialized = json.loads(bundle.to_json())
    assert serialized["schema"] == STRUCTURAL_EXPORT_SCHEMA
    assert serialized["read_only"] is True
    assert serialized["authority"] == ADVISORY_AUTHORITY
    assert serialized["grants_authority"] is False
    assert serialized["candidate_count"] == 5

    query = next(c for c in bundle.candidates if c.symbol_id == "alpha.py::compute_discounted_total")
    other_candidates = [c for c in bundle.candidates if c.symbol_id != query.symbol_id]

    ranked = rank_retrieval_candidates(query, other_candidates)
    assert len(ranked) == 4
    # Exact alpha-renamed equivalent must rank first with similarity 1.0
    assert ranked[0].candidate_symbol_id == "beta.py::calculate_rebated_sum"
    assert ranked[0].exact_structural_match is True
    assert ranked[0].overall_similarity == 1.0
    assert ranked[0].authority == ADVISORY_AUTHORITY
    assert ranked[0].grants_authority is False

    # Unrelated recursive function must rank last
    assert ranked[-1].candidate_symbol_id == "alpha.py::factorial_calc"
    assert ranked[-1].overall_similarity < ranked[1].overall_similarity
