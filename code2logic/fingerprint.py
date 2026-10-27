"""
Read-only structural CFG/DFG/I-O/effects fingerprint exporter for semantic retrieval candidates.

Implements PLF-006 (Issue #9):
- Stable read-only structural export and schema versions:
  - ``code2logic.structural_fingerprint/v1``
  - ``code2logic.structural_export/v1``
  - ``code2logic.structural_similarity/v1``
- Symbol-local alpha-renaming normalization of parameters, local variables,
  recursive self-references, and docstrings.
- Normalized symbol-local Control-Flow Graph (CFG), Data-Flow Graph (DFG),
  Input/Output (I/O) signature/return profile, and side-effect profile with
  deterministic SHA-256 digests and source hashes.
- Advisory-only structural similarity comparison and retrieval candidate ranking
  (``read_only=True``, ``authority="advisory_only"``, ``grants_authority=False``).
"""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

STRUCTURAL_FINGERPRINT_SCHEMA = "code2logic.structural_fingerprint/v1"
STRUCTURAL_EXPORT_SCHEMA = "code2logic.structural_export/v1"
STRUCTURAL_SIMILARITY_SCHEMA = "code2logic.structural_similarity/v1"
ADVISORY_AUTHORITY = "advisory_only"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_payload(payload: Any) -> str:
    return _sha256_text(_canonical_json(payload))


def _strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    """Return function body without a leading literal docstring statement."""
    if not body:
        return []
    first = body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return list(body[1:])
    return list(body)


class _SymbolAlphaNormalizer:
    """Deterministic symbol-local alpha-renaming environment for Python AST nodes."""

    def __init__(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        is_method: bool = False,
    ) -> None:
        self.func_name = func_node.name
        self.is_method = is_method
        self.param_map: dict[str, str] = {}
        self.local_map: dict[str, str] = {}
        self._bind_parameters(func_node.args, is_method=is_method)
        self._collect_locals(_strip_docstring(func_node.body))

    def _bind_parameters(self, arguments: ast.arguments, *, is_method: bool) -> None:
        ordered_args: list[tuple[str, str]] = []
        for a in arguments.posonlyargs:
            ordered_args.append(("posonly", a.arg))
        for a in arguments.args:
            ordered_args.append(("arg", a.arg))
        if arguments.vararg is not None:
            ordered_args.append(("vararg", arguments.vararg.arg))
        for a in arguments.kwonlyargs:
            ordered_args.append(("kwonly", a.arg))
        if arguments.kwarg is not None:
            ordered_args.append(("kwarg", arguments.kwarg.arg))

        logical_index = 0
        for idx, (_kind, raw_name) in enumerate(ordered_args):
            if is_method and idx == 0 and raw_name in ("self", "cls"):
                self.param_map[raw_name] = "$self"
            else:
                self.param_map[raw_name] = f"$arg{logical_index}"
                logical_index += 1

    def _register_local(self, name: str) -> str:
        if name in self.param_map:
            return self.param_map[name]
        if name == self.func_name:
            return "$self_fn"
        if name not in self.local_map:
            self.local_map[name] = f"$loc{len(self.local_map)}"
        return self.local_map[name]

    def _collect_target_names(self, target: ast.AST) -> list[str]:
        names: list[str] = []
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                names.extend(self._collect_target_names(elt))
        elif isinstance(target, ast.Starred):
            names.extend(self._collect_target_names(target.value))
        return names

    def _collect_locals(self, stmts: Sequence[ast.stmt]) -> None:
        for stmt in stmts:
            self._collect_locals_from_node(stmt)

    def _collect_locals_from_node(self, node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            self._register_local(node.name)
            return

        if isinstance(node, ast.Assign):
            for target in node.targets:
                for name in self._collect_target_names(target):
                    self._register_local(name)
            self._collect_locals_from_node(node.value)
            return

        if isinstance(node, ast.AnnAssign):
            for name in self._collect_target_names(node.target):
                self._register_local(name)
            if node.value is not None:
                self._collect_locals_from_node(node.value)
            return

        if isinstance(node, ast.AugAssign):
            for name in self._collect_target_names(node.target):
                self._register_local(name)
            self._collect_locals_from_node(node.value)
            return

        if isinstance(node, (ast.For, ast.AsyncFor)):
            for name in self._collect_target_names(node.target):
                self._register_local(name)
            self._collect_locals_from_node(node.iter)
            self._collect_locals(node.body)
            self._collect_locals(node.orelse)
            return

        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                self._collect_locals_from_node(item.context_expr)
                if item.optional_vars is not None:
                    for name in self._collect_target_names(item.optional_vars):
                        self._register_local(name)
            self._collect_locals(node.body)
            return

        if isinstance(node, ast.ExceptHandler):
            if isinstance(node.name, str) and node.name:
                self._register_local(node.name)
            self._collect_locals(node.body)
            return

        if isinstance(node, ast.NamedExpr):
            for name in self._collect_target_names(node.target):
                self._register_local(name)
            self._collect_locals_from_node(node.value)
            return

        if isinstance(node, ast.comprehension):
            for name in self._collect_target_names(node.target):
                self._register_local(name)
            self._collect_locals_from_node(node.iter)
            for cond in node.ifs:
                self._collect_locals_from_node(cond)
            return

        for child in ast.iter_child_nodes(node):
            self._collect_locals_from_node(child)

    def normalize_name(self, name: str) -> str:
        if name in self.param_map:
            return self.param_map[name]
        if name in self.local_map:
            return self.local_map[name]
        if name == self.func_name:
            return "$self_fn"
        return f"ext:{name}"

    def is_local_or_param(self, name: str) -> bool:
        return name in self.param_map or name in self.local_map

    def normalize_expr(self, node: ast.AST | None) -> str:
        if node is None:
            return "None"
        if isinstance(node, ast.Name):
            return self.normalize_name(node.id)
        if isinstance(node, ast.Constant):
            return f"const({type(node.value).__name__}:{repr(node.value)})"
        if isinstance(node, ast.Attribute):
            return f"attr({self.normalize_expr(node.value)}.{node.attr})"
        if isinstance(node, ast.Subscript):
            return f"sub({self.normalize_expr(node.value)}[{self.normalize_expr(node.slice)}])"
        if isinstance(node, ast.Slice):
            return (
                f"slice({self.normalize_expr(node.lower)}:"
                f"{self.normalize_expr(node.upper)}:"
                f"{self.normalize_expr(node.step)})"
            )
        if isinstance(node, ast.BinOp):
            op_name = type(node.op).__name__
            return f"binop({op_name},{self.normalize_expr(node.left)},{self.normalize_expr(node.right)})"
        if isinstance(node, ast.UnaryOp):
            op_name = type(node.op).__name__
            return f"unary({op_name},{self.normalize_expr(node.operand)})"
        if isinstance(node, ast.BoolOp):
            op_name = type(node.op).__name__
            vals = ",".join(self.normalize_expr(v) for v in node.values)
            return f"boolop({op_name},[{vals}])"
        if isinstance(node, ast.Compare):
            ops = ",".join(type(op).__name__ for op in node.ops)
            comps = ",".join(self.normalize_expr(c) for c in node.comparators)
            return f"cmp({self.normalize_expr(node.left)},[{ops}],[{comps}])"
        if isinstance(node, ast.Call):
            callee = self.normalize_callee(node.func)
            pos = ",".join(self.normalize_expr(a) for a in node.args)
            kws = ",".join(
                f"{kw.arg or '**'}={self.normalize_expr(kw.value)}"
                for kw in sorted(node.keywords, key=lambda item: item.arg or "")
            )
            return f"call({callee},args=[{pos}],kwargs=[{kws}])"
        if isinstance(node, ast.IfExp):
            return (
                f"ifexp({self.normalize_expr(node.test)},"
                f"{self.normalize_expr(node.body)},"
                f"{self.normalize_expr(node.orelse)})"
            )
        if isinstance(node, ast.Tuple):
            elts = ",".join(self.normalize_expr(e) for e in node.elts)
            return f"tuple([{elts}])"
        if isinstance(node, ast.List):
            elts = ",".join(self.normalize_expr(e) for e in node.elts)
            return f"list([{elts}])"
        if isinstance(node, ast.Set):
            elts = ",".join(self.normalize_expr(e) for e in node.elts)
            return f"set([{elts}])"
        if isinstance(node, ast.Dict):
            pairs = ",".join(
                f"{self.normalize_expr(k)}:{self.normalize_expr(v)}"
                for k, v in zip(node.keys, node.values)
            )
            return f"dict([{{{pairs}}}])"
        if isinstance(node, ast.JoinedStr):
            parts = []
            for val in node.values:
                if isinstance(val, ast.FormattedValue):
                    parts.append(f"fmt({self.normalize_expr(val.value)})")
                elif isinstance(val, ast.Constant):
                    parts.append(f"lit({repr(val.value)})")
                else:
                    parts.append(self.normalize_expr(val))
            return f"fstr([{','.join(parts)}])"
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            kind = type(node).__name__
            gens = ",".join(self._normalize_comprehension(g) for g in node.generators)
            return f"{kind}({self.normalize_expr(node.elt)},[{gens}])"
        if isinstance(node, ast.DictComp):
            gens = ",".join(self._normalize_comprehension(g) for g in node.generators)
            return (
                f"DictComp({self.normalize_expr(node.key)}:"
                f"{self.normalize_expr(node.value)},[{gens}])"
            )
        if isinstance(node, ast.Await):
            return f"await({self.normalize_expr(node.value)})"
        if isinstance(node, ast.Yield):
            return f"yield({self.normalize_expr(node.value)})"
        if isinstance(node, ast.YieldFrom):
            return f"yieldfrom({self.normalize_expr(node.value)})"
        if isinstance(node, ast.NamedExpr):
            return f"named({self.normalize_expr(node.target)}:={self.normalize_expr(node.value)})"
        if isinstance(node, ast.Starred):
            return f"starred({self.normalize_expr(node.value)})"
        if isinstance(node, ast.Lambda):
            body = self.normalize_expr(node.body)
            return f"lambda(arity={len(node.args.args)},{body})"
        return type(node).__name__

    def _normalize_comprehension(self, gen: ast.comprehension) -> str:
        ifs = ",".join(self.normalize_expr(cond) for cond in gen.ifs)
        return (
            f"for({self.normalize_expr(gen.target)} in "
            f"{self.normalize_expr(gen.iter)} if [{ifs}] async={gen.is_async})"
        )

    def normalize_callee(self, func: ast.AST) -> str:
        if isinstance(func, ast.Name):
            return self.normalize_name(func.id)
        if isinstance(func, ast.Attribute):
            return f"{self.normalize_expr(func.value)}.{func.attr}"
        return self.normalize_expr(func)

    def referenced_vars(self, node: ast.AST | None) -> tuple[str, ...]:
        if node is None:
            return ()
        found: list[str] = []
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                norm = self.normalize_name(sub.id)
                if norm not in found:
                    found.append(norm)
        return tuple(sorted(found))


@dataclass(frozen=True)
class CFGNodeRecord:
    """Normalized Control-Flow Graph node."""

    block_id: str
    kind: str
    predicate: str | None = None
    statement_shapes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "kind": self.kind,
            "predicate": self.predicate,
            "statement_shapes": list(self.statement_shapes),
        }


@dataclass(frozen=True)
class CFGEdgeRecord:
    """Normalized directed Control-Flow Graph edge."""

    source: str
    target: str
    label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "label": self.label,
        }


@dataclass(frozen=True)
class ControlFlowFingerprint:
    """Symbol-local normalized Control-Flow Graph representation and digest."""

    nodes: tuple[CFGNodeRecord, ...]
    edges: tuple[CFGEdgeRecord, ...]
    cyclomatic_complexity: int
    branch_predicates: tuple[str, ...]
    loop_headers: tuple[str, ...]
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "cyclomatic_complexity": self.cyclomatic_complexity,
            "branch_predicates": list(self.branch_predicates),
            "loop_headers": list(self.loop_headers),
            "digest": self.digest,
        }


@dataclass(frozen=True)
class DataFlowEdgeRecord:
    """Normalized directed Data-Flow dependency edge (def/use -> target)."""

    source: str
    target: str
    kind: str
    expression_shape: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "expression_shape": self.expression_shape,
        }


@dataclass(frozen=True)
class DataFlowFingerprint:
    """Symbol-local normalized Data-Flow Graph representation and digest."""

    parameters: tuple[str, ...]
    locals_defined: tuple[str, ...]
    definitions: tuple[tuple[str, str, str], ...]
    uses: tuple[tuple[str, str], ...]
    edges: tuple[DataFlowEdgeRecord, ...]
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameters": list(self.parameters),
            "locals_defined": list(self.locals_defined),
            "definitions": [
                {"target": target, "kind": kind, "shape": shape}
                for target, kind, shape in self.definitions
            ],
            "uses": [
                {"symbol": sym, "context": ctx}
                for sym, ctx in self.uses
            ],
            "edges": [e.to_dict() for e in self.edges],
            "digest": self.digest,
        }


@dataclass(frozen=True)
class IOProfile:
    """Normalized symbol input/output signature and return profile."""

    arity: int
    arg_kinds: tuple[str, ...]
    param_annotations: tuple[str, ...]
    default_shapes: tuple[str, ...]
    return_annotation: str
    return_shapes: tuple[str, ...]
    yield_shapes: tuple[str, ...]
    is_async: bool
    is_method: bool
    is_generator: bool
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "arity": self.arity,
            "arg_kinds": list(self.arg_kinds),
            "param_annotations": list(self.param_annotations),
            "default_shapes": list(self.default_shapes),
            "return_annotation": self.return_annotation,
            "return_shapes": list(self.return_shapes),
            "yield_shapes": list(self.yield_shapes),
            "is_async": self.is_async,
            "is_method": self.is_method,
            "is_generator": self.is_generator,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class EffectsProfile:
    """Normalized side-effects, external calls, mutations, and exception profile."""

    calls: tuple[str, ...]
    call_Site_shapes: tuple[str, ...]
    raises: tuple[str, ...]
    mutations: tuple[str, ...]
    awaits: tuple[str, ...]
    effect_tags: tuple[str, ...]
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "calls": list(self.calls),
            "call_site_shapes": list(self.call_Site_shapes),
            "raises": list(self.raises),
            "mutations": list(self.mutations),
            "awaits": list(self.awaits),
            "effect_tags": list(self.effect_tags),
            "digest": self.digest,
        }


@dataclass(frozen=True)
class StructuralFingerprint:
    """Read-only structural fingerprint record for a single function or method."""

    schema: str
    symbol_id: str
    qualified_name: str
    module_path: str
    symbol_kind: str
    start_line: int
    end_line: int
    source_sha256: str
    module_source_sha256: str
    normalized_ast_sha256: str
    cfg: ControlFlowFingerprint
    dfg: DataFlowFingerprint
    io: IOProfile
    effects: EffectsProfile
    combined_fingerprint: str
    read_only: bool = True
    authority: str = ADVISORY_AUTHORITY
    grants_authority: bool = False

    @property
    def cfg_fingerprint(self) -> str:
        return self.cfg.digest

    @property
    def dfg_fingerprint(self) -> str:
        return self.dfg.digest

    @property
    def io_fingerprint(self) -> str:
        return self.io.digest

    @property
    def effects_fingerprint(self) -> str:
        return self.effects.digest

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "symbol_id": self.symbol_id,
            "qualified_name": self.qualified_name,
            "module_path": self.module_path,
            "symbol_kind": self.symbol_kind,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "source_sha256": self.source_sha256,
            "module_source_sha256": self.module_source_sha256,
            "normalized_ast_sha256": self.normalized_ast_sha256,
            "cfg_fingerprint": self.cfg.digest,
            "dfg_fingerprint": self.dfg.digest,
            "io_fingerprint": self.io.digest,
            "effects_fingerprint": self.effects.digest,
            "combined_fingerprint": self.combined_fingerprint,
            "cfg": self.cfg.to_dict(),
            "dfg": self.dfg.to_dict(),
            "io": self.io.to_dict(),
            "effects": self.effects.to_dict(),
            "read_only": self.read_only,
            "authority": self.authority,
            "grants_authority": self.grants_authority,
        }


@dataclass(frozen=True)
class StructuralSimilarityMatch:
    """Advisory-only structural similarity evaluation between two symbols."""

    schema: str
    query_symbol_id: str
    candidate_symbol_id: str
    exact_structural_match: bool
    cfg_match: bool
    dfg_match: bool
    io_match: bool
    effects_match: bool
    cfg_similarity: float
    dfg_similarity: float
    io_similarity: float
    effects_similarity: float
    overall_similarity: float
    rationale: tuple[str, ...]
    read_only: bool = True
    authority: str = ADVISORY_AUTHORITY
    grants_authority: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "query_symbol_id": self.query_symbol_id,
            "candidate_symbol_id": self.candidate_symbol_id,
            "exact_structural_match": self.exact_structural_match,
            "cfg_match": self.cfg_match,
            "dfg_match": self.dfg_match,
            "io_match": self.io_match,
            "effects_match": self.effects_match,
            "cfg_similarity": round(self.cfg_similarity, 6),
            "dfg_similarity": round(self.dfg_similarity, 6),
            "io_similarity": round(self.io_similarity, 6),
            "effects_similarity": round(self.effects_similarity, 6),
            "overall_similarity": round(self.overall_similarity, 6),
            "rationale": list(self.rationale),
            "read_only": self.read_only,
            "authority": self.authority,
            "grants_authority": self.grants_authority,
        }


@dataclass(frozen=True)
class StructuralExportBundle:
    """Read-only export container for a module or project's structural fingerprints."""

    schema: str
    candidates: tuple[StructuralFingerprint, ...]
    read_only: bool = True
    authority: str = ADVISORY_AUTHORITY
    grants_authority: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "candidate_count": len(self.candidates),
            "candidates": [c.to_dict() for c in self.candidates],
            "read_only": self.read_only,
            "authority": self.authority,
            "grants_authority": self.grants_authority,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


class _CFGBuilder:
    """Builds a deterministic symbol-local normalized Control-Flow Graph."""

    def __init__(self, normalizer: _SymbolAlphaNormalizer) -> None:
        self.normalizer = normalizer
        self.nodes: list[CFGNodeRecord] = []
        self.edges: list[CFGEdgeRecord] = []
        self.branch_predicates: list[str] = []
        self.loop_headers: list[str] = []
        self.complexity = 1
        self._counter = 0

    def _new_block_id(self, prefix: str = "B") -> str:
        idx = self._counter
        self._counter += 1
        return f"{prefix}{idx}"

    def _add_node(
        self,
        block_id: str,
        kind: str,
        *,
        predicate: str | None = None,
        statement_shapes: Sequence[str] = (),
    ) -> str:
        self.nodes.append(
            CFGNodeRecord(
                block_id=block_id,
                kind=kind,
                predicate=predicate,
                statement_shapes=tuple(statement_shapes),
            )
        )
        return block_id

    def _add_edge(self, source: str, target: str, label: str) -> None:
        self.edges.append(CFGEdgeRecord(source=source, target=target, label=label))

    def build(self, body: Sequence[ast.stmt]) -> ControlFlowFingerprint:
        entry_id = self._add_node(self._new_block_id("ENTRY"), "entry")
        exit_id = self._new_block_id("EXIT")
        tails = self._process_block(body, [entry_id], exit_id=exit_id, loop_head=None)
        for tail_id, edge_label in tails:
            self._add_edge(tail_id, exit_id, edge_label)
        self._add_node(exit_id, "exit")

        # Count boolean operator decision points inside expressions
        for stmt in body:
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.BoolOp):
                    self.complexity += max(0, len(sub.values) - 1)
                elif isinstance(sub, ast.IfExp):
                    self.complexity += 1
                elif isinstance(sub, ast.comprehension):
                    self.complexity += 1 + len(sub.ifs)

        payload = {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "cyclomatic_complexity": self.complexity,
            "branch_predicates": self.branch_predicates,
            "loop_headers": self.loop_headers,
        }
        return ControlFlowFingerprint(
            nodes=tuple(self.nodes),
            edges=tuple(self.edges),
            cyclomatic_complexity=self.complexity,
            branch_predicates=tuple(self.branch_predicates),
            loop_headers=tuple(self.loop_headers),
            digest=_sha256_payload(payload),
        )

    def _stmt_shape(self, stmt: ast.stmt) -> str:
        if isinstance(stmt, ast.Assign):
            targets = ",".join(self.normalizer.normalize_expr(t) for t in stmt.targets)
            return f"assign([{targets}]={self.normalizer.normalize_expr(stmt.value)})"
        if isinstance(stmt, ast.AnnAssign):
            target = self.normalizer.normalize_expr(stmt.target)
            ann = self.normalizer.normalize_expr(stmt.annotation)
            val = self.normalizer.normalize_expr(stmt.value)
            return f"annassign({target}:{ann}={val})"
        if isinstance(stmt, ast.AugAssign):
            target = self.normalizer.normalize_expr(stmt.target)
            op_name = type(stmt.op).__name__
            val = self.normalizer.normalize_expr(stmt.value)
            return f"augassign({target},{op_name},{val})"
        if isinstance(stmt, ast.Expr):
            return f"expr({self.normalizer.normalize_expr(stmt.value)})"
        if isinstance(stmt, ast.Assert):
            return f"assert({self.normalizer.normalize_expr(stmt.test)})"
        if isinstance(stmt, ast.Delete):
            targets = ",".join(self.normalizer.normalize_expr(t) for t in stmt.targets)
            return f"delete([{targets}])"
        if isinstance(stmt, ast.Pass):
            return "pass"
        return type(stmt).__name__

    def _process_block(
        self,
        stmts: Sequence[ast.stmt],
        incoming: list[str],
        *,
        exit_id: str,
        loop_head: str | None,
    ) -> list[tuple[str, str]]:
        current_incoming: list[tuple[str, str]] = [(bid, "next") for bid in incoming]

        for stmt in stmts:
            if not current_incoming:
                break

            if isinstance(stmt, ast.If):
                self.complexity += 1
                pred = self.normalizer.normalize_expr(stmt.test)
                self.branch_predicates.append(pred)
                branch_id = self._add_node(
                    self._new_block_id("IF"),
                    "branch_if",
                    predicate=pred,
                )
                for src, lbl in current_incoming:
                    self._add_edge(src, branch_id, lbl)

                true_tails = self._process_connected(
                    stmt.body,
                    branch_id,
                    "true",
                    exit_id=exit_id,
                    loop_head=loop_head,
                )
                if stmt.orelse:
                    false_tails = self._process_connected(
                        stmt.orelse,
                        branch_id,
                        "false",
                        exit_id=exit_id,
                        loop_head=loop_head,
                    )
                else:
                    false_tails = [(branch_id, "false")]
                current_incoming = true_tails + false_tails

            elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                self.complexity += 1
                kind = "loop_async_for" if isinstance(stmt, ast.AsyncFor) else "loop_for"
                header = (
                    f"{self.normalizer.normalize_expr(stmt.target)} in "
                    f"{self.normalizer.normalize_expr(stmt.iter)}"
                )
                self.loop_headers.append(header)
                loop_id = self._add_node(
                    self._new_block_id("FOR"),
                    kind,
                    predicate=header,
                )
                for src, lbl in current_incoming:
                    self._add_edge(src, loop_id, lbl)

                body_tails = self._process_connected(
                    stmt.body,
                    loop_id,
                    "loop_body",
                    exit_id=exit_id,
                    loop_head=loop_id,
                )
                for src, lbl in body_tails:
                    self._add_edge(src, loop_id, "loop_back" if lbl == "next" else lbl)

                if stmt.orelse:
                    current_incoming = self._process_connected(
                        stmt.orelse,
                        loop_id,
                        "loop_else",
                        exit_id=exit_id,
                        loop_head=loop_head,
                    )
                else:
                    current_incoming = [(loop_id, "loop_exit")]

            elif isinstance(stmt, ast.While):
                self.complexity += 1
                pred = self.normalizer.normalize_expr(stmt.test)
                self.branch_predicates.append(pred)
                self.loop_headers.append(f"while({pred})")
                loop_id = self._add_node(
                    self._new_block_id("WHILE"),
                    "loop_while",
                    predicate=pred,
                )
                for src, lbl in current_incoming:
                    self._add_edge(src, loop_id, lbl)

                body_tails = self._process_connected(
                    stmt.body,
                    loop_id,
                    "true",
                    exit_id=exit_id,
                    loop_head=loop_id,
                )
                for src, lbl in body_tails:
                    self._add_edge(src, loop_id, "loop_back" if lbl == "next" else lbl)

                if stmt.orelse:
                    current_incoming = self._process_connected(
                        stmt.orelse,
                        loop_id,
                        "false",
                        exit_id=exit_id,
                        loop_head=loop_head,
                    )
                else:
                    current_incoming = [(loop_id, "false")]

            elif isinstance(stmt, ast.Try):
                try_id = self._add_node(self._new_block_id("TRY"), "try_block")
                for src, lbl in current_incoming:
                    self._add_edge(src, try_id, lbl)

                try_tails = self._process_connected(
                    stmt.body,
                    try_id,
                    "try_body",
                    exit_id=exit_id,
                    loop_head=loop_head,
                )
                handler_tails: list[tuple[str, str]] = []
                for handler in stmt.handlers:
                    self.complexity += 1
                    exc_type = self.normalizer.normalize_expr(handler.type)
                    self.branch_predicates.append(f"except({exc_type})")
                    h_id = self._add_node(
                        self._new_block_id("EXCEPT"),
                        "except_handler",
                        predicate=exc_type,
                    )
                    self._add_edge(try_id, h_id, "exception")
                    handler_tails.extend(
                        self._process_connected(
                            handler.body,
                            h_id,
                            "handler_body",
                            exit_id=exit_id,
                            loop_head=loop_head,
                        )
                    )

                if stmt.orelse and try_tails:
                    else_entry = self._add_node(self._new_block_id("TRY_ELSE"), "try_else")
                    for src, lbl in try_tails:
                        self._add_edge(src, else_entry, lbl)
                    try_tails = self._process_connected(
                        stmt.orelse,
                        else_entry,
                        "next",
                        exit_id=exit_id,
                        loop_head=loop_head,
                    )

                combined_tails = try_tails + handler_tails
                if stmt.finalbody:
                    fin_id = self._add_node(self._new_block_id("FINALLY"), "finally_block")
                    for src, lbl in combined_tails:
                        self._add_edge(src, fin_id, lbl)
                    current_incoming = self._process_connected(
                        stmt.finalbody,
                        fin_id,
                        "next",
                        exit_id=exit_id,
                        loop_head=loop_head,
                    )
                else:
                    current_incoming = combined_tails

            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                kind = "async_with" if isinstance(stmt, ast.AsyncWith) else "with"
                ctx_shapes = [
                    self.normalizer.normalize_expr(item.context_expr)
                    for item in stmt.items
                ]
                with_id = self._add_node(
                    self._new_block_id("WITH"),
                    kind,
                    statement_shapes=ctx_shapes,
                )
                for src, lbl in current_incoming:
                    self._add_edge(src, with_id, lbl)
                current_incoming = self._process_connected(
                    stmt.body,
                    with_id,
                    "with_body",
                    exit_id=exit_id,
                    loop_head=loop_head,
                )

            elif isinstance(stmt, ast.Return):
                ret_shape = f"return({self.normalizer.normalize_expr(stmt.value)})"
                ret_id = self._add_node(
                    self._new_block_id("RET"),
                    "return",
                    statement_shapes=(ret_shape,),
                )
                for src, lbl in current_incoming:
                    self._add_edge(src, ret_id, lbl)
                self._add_edge(ret_id, exit_id, "return")
                current_incoming = []

            elif isinstance(stmt, ast.Raise):
                exc_shape = f"raise({self.normalizer.normalize_expr(stmt.exc)})"
                raise_id = self._add_node(
                    self._new_block_id("RAISE"),
                    "raise",
                    statement_shapes=(exc_shape,),
                )
                for src, lbl in current_incoming:
                    self._add_edge(src, raise_id, lbl)
                self._add_edge(raise_id, exit_id, "raise")
                current_incoming = []

            elif isinstance(stmt, ast.Break):
                brk_id = self._add_node(self._new_block_id("BREAK"), "break")
                for src, lbl in current_incoming:
                    self._add_edge(src, brk_id, lbl)
                current_incoming = []

            elif isinstance(stmt, ast.Continue):
                cnt_id = self._add_node(self._new_block_id("CONTINUE"), "continue")
                for src, lbl in current_incoming:
                    self._add_edge(src, cnt_id, lbl)
                if loop_head is not None:
                    self._add_edge(cnt_id, loop_head, "continue")
                current_incoming = []

            else:
                stmt_id = self._add_node(
                    self._new_block_id("STMT"),
                    "statement",
                    statement_shapes=(self._stmt_shape(stmt),),
                )
                for src, lbl in current_incoming:
                    self._add_edge(src, stmt_id, lbl)
                current_incoming = [(stmt_id, "next")]

        return current_incoming

    def _process_connected(
        self,
        stmts: Sequence[ast.stmt],
        source_id: str,
        edge_label: str,
        *,
        exit_id: str,
        loop_head: str | None,
    ) -> list[tuple[str, str]]:
        anchor_id = self._add_node(self._new_block_id("BLK"), f"edge_{edge_label}")
        self._add_edge(source_id, anchor_id, edge_label)
        return self._process_block(
            stmts,
            [anchor_id],
            exit_id=exit_id,
            loop_head=loop_head,
        )


def _build_dfg(
    body: Sequence[ast.stmt],
    normalizer: _SymbolAlphaNormalizer,
) -> DataFlowFingerprint:
    definitions: list[tuple[str, str, str]] = []
    uses: list[tuple[str, str]] = []
    edges: list[DataFlowEdgeRecord] = []

    parameters = tuple(normalizer.param_map.values())
    locals_defined = tuple(normalizer.local_map.values())

    for canonical_param in parameters:
        definitions.append((canonical_param, "parameter", canonical_param))

    def record_flow(
        target_symbol: str,
        kind: str,
        value_node: ast.AST | None,
        extra_sources: Sequence[str] = (),
    ) -> None:
        shape = normalizer.normalize_expr(value_node)
        definitions.append((target_symbol, kind, shape))
        sources = list(normalizer.referenced_vars(value_node))
        for extra in extra_sources:
            if extra not in sources:
                sources.append(extra)
        if not sources:
            edges.append(
                DataFlowEdgeRecord(
                    source="$const",
                    target=target_symbol,
                    kind=kind,
                    expression_shape=shape,
                )
            )
        else:
            for src in sorted(sources):
                uses.append((src, f"{kind}:{target_symbol}"))
                edges.append(
                    DataFlowEdgeRecord(
                        source=src,
                        target=target_symbol,
                        kind=kind,
                        expression_shape=shape,
                    )
                )

    def walk_stmts(stmts: Sequence[ast.stmt]) -> None:
        for stmt in stmts:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    target_names = normalizer._collect_target_names(target)
                    if target_names:
                        for raw_name in target_names:
                            norm_target = normalizer.normalize_name(raw_name)
                            record_flow(norm_target, "assign", stmt.value)
                    else:
                        norm_target = normalizer.normalize_expr(target)
                        record_flow(norm_target, "mutate", stmt.value)

            elif isinstance(stmt, ast.AnnAssign):
                target_names = normalizer._collect_target_names(stmt.target)
                for raw_name in target_names:
                    norm_target = normalizer.normalize_name(raw_name)
                    record_flow(norm_target, "ann_assign", stmt.value)

            elif isinstance(stmt, ast.AugAssign):
                op_name = type(stmt.op).__name__
                target_names = normalizer._collect_target_names(stmt.target)
                if target_names:
                    for raw_name in target_names:
                        norm_target = normalizer.normalize_name(raw_name)
                        record_flow(
                            norm_target,
                            f"aug_assign:{op_name}",
                            stmt.value,
                            extra_sources=(norm_target,),
                        )
                else:
                    norm_target = normalizer.normalize_expr(stmt.target)
                    record_flow(
                        norm_target,
                        f"aug_mutate:{op_name}",
                        stmt.value,
                    )

            elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                for raw_name in normalizer._collect_target_names(stmt.target):
                    norm_target = normalizer.normalize_name(raw_name)
                    record_flow(norm_target, "iter_bind", stmt.iter)
                walk_stmts(stmt.body)
                walk_stmts(stmt.orelse)

            elif isinstance(stmt, ast.While):
                for src in normalizer.referenced_vars(stmt.test):
                    uses.append((src, "while_cond"))
                walk_stmts(stmt.body)
                walk_stmts(stmt.orelse)

            elif isinstance(stmt, ast.If):
                for src in normalizer.referenced_vars(stmt.test):
                    uses.append((src, "if_cond"))
                walk_stmts(stmt.body)
                walk_stmts(stmt.orelse)

            elif isinstance(stmt, ast.Try):
                walk_stmts(stmt.body)
                for handler in stmt.handlers:
                    if isinstance(handler.name, str) and handler.name:
                        norm_exc = normalizer.normalize_name(handler.name)
                        record_flow(norm_exc, "except_bind", handler.type)
                    walk_stmts(handler.body)
                walk_stmts(stmt.orelse)
                walk_stmts(stmt.finalbody)

            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                for item in stmt.items:
                    if item.optional_vars is not None:
                        for raw_name in normalizer._collect_target_names(item.optional_vars):
                            norm_target = normalizer.normalize_name(raw_name)
                            record_flow(norm_target, "with_bind", item.context_expr)
                walk_stmts(stmt.body)

            elif isinstance(stmt, ast.Return):
                record_flow("$return", "return", stmt.value)

            elif isinstance(stmt, ast.Raise):
                record_flow("$raise", "raise", stmt.exc)

            elif isinstance(stmt, ast.Expr):
                if isinstance(stmt.value, (ast.Yield, ast.YieldFrom)):
                    record_flow("$yield", "yield", stmt.value.value)
                else:
                    for src in normalizer.referenced_vars(stmt.value):
                        uses.append((src, "expr_eval"))

    walk_stmts(body)

    payload = {
        "parameters": list(parameters),
        "locals_defined": list(locals_defined),
        "definitions": [list(item) for item in definitions],
        "uses": [list(item) for item in uses],
        "edges": [e.to_dict() for e in edges],
    }
    return DataFlowFingerprint(
        parameters=parameters,
        locals_defined=locals_defined,
        definitions=tuple(definitions),
        uses=tuple(uses),
        edges=tuple(edges),
        digest=_sha256_payload(payload),
    )


def _build_io_profile(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    body: Sequence[ast.stmt],
    normalizer: _SymbolAlphaNormalizer,
    *,
    is_method: bool,
) -> IOProfile:
    args = func_node.args
    arg_kinds: list[str] = []
    param_annotations: list[str] = []

    all_pos = list(args.posonlyargs) + list(args.args)
    for idx, arg in enumerate(all_pos):
        if is_method and idx == 0 and arg.arg in ("self", "cls"):
            continue
        kind = "posonly" if idx < len(args.posonlyargs) else "arg"
        arg_kinds.append(kind)
        param_annotations.append(normalizer.normalize_expr(arg.annotation))

    if args.vararg is not None:
        arg_kinds.append("vararg")
        param_annotations.append(normalizer.normalize_expr(args.vararg.annotation))
    for kwarg in args.kwonlyargs:
        arg_kinds.append("kwonly")
        param_annotations.append(normalizer.normalize_expr(kwarg.annotation))
    if args.kwarg is not None:
        arg_kinds.append("kwarg")
        param_annotations.append(normalizer.normalize_expr(args.kwarg.annotation))

    default_nodes = list(args.defaults) + [d for d in args.kw_defaults if d is not None]
    default_shapes = tuple(normalizer.normalize_expr(d) for d in default_nodes)

    return_annotation = normalizer.normalize_expr(func_node.returns)
    return_shapes: list[str] = []
    yield_shapes: list[str] = []

    for stmt in body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Return):
                return_shapes.append(normalizer.normalize_expr(sub.value))
            elif isinstance(sub, ast.Yield):
                yield_shapes.append(f"yield({normalizer.normalize_expr(sub.value)})")
            elif isinstance(sub, ast.YieldFrom):
                yield_shapes.append(f"yieldfrom({normalizer.normalize_expr(sub.value)})")

    is_async = isinstance(func_node, ast.AsyncFunctionDef)
    is_generator = bool(yield_shapes)
    arity = len(arg_kinds)

    payload = {
        "arity": arity,
        "arg_kinds": arg_kinds,
        "param_annotations": param_annotations,
        "default_shapes": list(default_shapes),
        "return_annotation": return_annotation,
        "return_shapes": return_shapes,
        "yield_shapes": yield_shapes,
        "is_async": is_async,
        "is_method": is_method,
        "is_generator": is_generator,
    }
    return IOProfile(
        arity=arity,
        arg_kinds=tuple(arg_kinds),
        param_annotations=tuple(param_annotations),
        default_shapes=default_shapes,
        return_annotation=return_annotation,
        return_shapes=tuple(return_shapes),
        yield_shapes=tuple(yield_shapes),
        is_async=is_async,
        is_method=is_method,
        is_generator=is_generator,
        digest=_sha256_payload(payload),
    )


def _build_effects_profile(
    body: Sequence[ast.stmt],
    normalizer: _SymbolAlphaNormalizer,
) -> EffectsProfile:
    calls: list[str] = []
    call_site_shapes: list[str] = []
    raises: list[str] = []
    mutations: list[str] = []
    awaits: list[str] = []

    for stmt in body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Call):
                callee = normalizer.normalize_callee(sub.func)
                calls.append(callee)
                call_site_shapes.append(normalizer.normalize_expr(sub))
            elif isinstance(sub, ast.Raise):
                if sub.exc is None:
                    raises.append("reraise")
                elif isinstance(sub.exc, ast.Call):
                    raises.append(normalizer.normalize_callee(sub.exc.func))
                else:
                    raises.append(normalizer.normalize_expr(sub.exc))
            elif isinstance(sub, ast.Await):
                awaits.append(normalizer.normalize_expr(sub.value))
            elif isinstance(sub, (ast.Attribute, ast.Subscript)) and isinstance(
                sub.ctx, (ast.Store, ast.Del)
            ):
                mutations.append(normalizer.normalize_expr(sub))

    tags: set[str] = set()
    if calls:
        tags.add("external_call")
    if raises:
        tags.add("raises")
    if mutations:
        tags.add("mutates_state")
    if awaits:
        tags.add("async_await")
    if not tags:
        tags.add("pure")

    sorted_calls = tuple(sorted(set(calls)))
    sorted_call_shapes = tuple(call_site_shapes)
    sorted_raises = tuple(sorted(set(raises)))
    sorted_mutations = tuple(sorted(set(mutations)))
    sorted_awaits = tuple(sorted(set(awaits)))
    sorted_tags = tuple(sorted(tags))

    payload = {
        "calls": list(sorted_calls),
        "call_site_shapes": list(sorted_call_shapes),
        "raises": list(sorted_raises),
        "mutations": list(sorted_mutations),
        "awaits": list(sorted_awaits),
        "effect_tags": list(sorted_tags),
    }
    return EffectsProfile(
        calls=sorted_calls,
        call_Site_shapes=sorted_call_shapes,
        raises=sorted_raises,
        mutations=sorted_mutations,
        awaits=sorted_awaits,
        effect_tags=sorted_tags,
        digest=_sha256_payload(payload),
    )


def extract_symbol_fingerprint(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    source_code: str,
    *,
    module_path: str = "<memory>",
    class_name: str | None = None,
) -> StructuralFingerprint:
    """Extract a normalized read-only ``StructuralFingerprint`` for one Python function/method."""
    is_method = class_name is not None
    qualified_name = f"{class_name}.{func_node.name}" if class_name else func_node.name
    symbol_kind = "method" if is_method else "function"
    symbol_id = f"{module_path}::{qualified_name}"

    module_source_sha256 = _sha256_text(source_code)
    segment = ast.get_source_segment(source_code, func_node)
    if not segment:
        lines = source_code.splitlines()
        start_idx = max(0, (getattr(func_node, "lineno", 1) or 1) - 1)
        end_idx = getattr(func_node, "end_lineno", len(lines)) or len(lines)
        segment = "\n".join(lines[start_idx:end_idx])
    source_sha256 = _sha256_text(segment)

    normalizer = _SymbolAlphaNormalizer(func_node, is_method=is_method)
    body = _strip_docstring(func_node.body)

    cfg = _CFGBuilder(normalizer).build(body)
    dfg = _build_dfg(body, normalizer)
    io_profile = _build_io_profile(func_node, body, normalizer, is_method=is_method)
    effects_profile = _build_effects_profile(body, normalizer)

    normalized_ast_repr = {
        "cfg": cfg.to_dict(),
        "dfg": dfg.to_dict(),
        "io": io_profile.to_dict(),
        "effects": effects_profile.to_dict(),
    }
    normalized_ast_sha256 = _sha256_payload(normalized_ast_repr)
    combined_fingerprint = _sha256_payload(
        {
            "schema": STRUCTURAL_FINGERPRINT_SCHEMA,
            "cfg": cfg.digest,
            "dfg": dfg.digest,
            "io": io_profile.digest,
            "effects": effects_profile.digest,
        }
    )

    return StructuralFingerprint(
        schema=STRUCTURAL_FINGERPRINT_SCHEMA,
        symbol_id=symbol_id,
        qualified_name=qualified_name,
        module_path=module_path,
        symbol_kind=symbol_kind,
        start_line=int(getattr(func_node, "lineno", 1) or 1),
        end_line=int(getattr(func_node, "end_lineno", getattr(func_node, "lineno", 1)) or 1),
        source_sha256=source_sha256,
        module_source_sha256=module_source_sha256,
        normalized_ast_sha256=normalized_ast_sha256,
        cfg=cfg,
        dfg=dfg,
        io=io_profile,
        effects=effects_profile,
        combined_fingerprint=combined_fingerprint,
        read_only=True,
        authority=ADVISORY_AUTHORITY,
        grants_authority=False,
    )


def extract_structural_fingerprints_from_source(
    source_code: str,
    *,
    module_path: str = "<memory>",
) -> tuple[StructuralFingerprint, ...]:
    """Parse Python source code and extract structural fingerprints for top-level functions and class methods."""
    tree = ast.parse(source_code)
    results: list[StructuralFingerprint] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            results.append(
                extract_symbol_fingerprint(
                    node,
                    source_code,
                    module_path=module_path,
                    class_name=None,
                )
            )
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    results.append(
                        extract_symbol_fingerprint(
                            item,
                            source_code,
                            module_path=module_path,
                            class_name=node.name,
                        )
                    )

    return tuple(results)


def export_structural_fingerprints(
    target: str | Path,
) -> StructuralExportBundle:
    """Export a read-only ``StructuralExportBundle`` for a Python file or directory."""
    path = Path(target)
    fingerprints: list[StructuralFingerprint] = []

    if path.is_file():
        source = path.read_text(encoding="utf-8")
        fingerprints.extend(
            extract_structural_fingerprints_from_source(
                source,
                module_path=path.name,
            )
        )
    elif path.is_dir():
        for py_file in sorted(path.rglob("*.py")):
            rel_path = py_file.relative_to(path).as_posix()
            if any(part.startswith(".") or part == "__pycache__" for part in py_file.parts):
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
                fingerprints.extend(
                    extract_structural_fingerprints_from_source(
                        source,
                        module_path=rel_path,
                    )
                )
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
    else:
        raise FileNotFoundError(f"Target path does not exist: {target}")

    return StructuralExportBundle(
        schema=STRUCTURAL_EXPORT_SCHEMA,
        candidates=tuple(fingerprints),
        read_only=True,
        authority=ADVISORY_AUTHORITY,
        grants_authority=False,
    )


def _jaccard(left: Iterable[Any], right: Iterable[Any]) -> float:
    set_l = set(left)
    set_r = set(right)
    if not set_l and not set_r:
        return 1.0
    union = set_l | set_r
    if not union:
        return 1.0
    return len(set_l & set_r) / len(union)


def compare_structural_fingerprints(
    query: StructuralFingerprint,
    candidate: StructuralFingerprint,
) -> StructuralSimilarityMatch:
    """Compute advisory-only structural similarity between two ``StructuralFingerprint`` records."""
    cfg_match = query.cfg.digest == candidate.cfg.digest
    dfg_match = query.dfg.digest == candidate.dfg.digest
    io_match = query.io.digest == candidate.io.digest
    effects_match = query.effects.digest == candidate.effects.digest
    exact_match = query.combined_fingerprint == candidate.combined_fingerprint

    if cfg_match:
        cfg_sim = 1.0
    else:
        q_cfg_features = [
            (n.kind, n.predicate, n.statement_shapes) for n in query.cfg.nodes
        ] + [(e.label,) for e in query.cfg.edges]
        c_cfg_features = [
            (n.kind, n.predicate, n.statement_shapes) for n in candidate.cfg.nodes
        ] + [(e.label,) for e in candidate.cfg.edges]
        pred_sim = _jaccard(query.cfg.branch_predicates, candidate.cfg.branch_predicates)
        node_sim = _jaccard(q_cfg_features, c_cfg_features)
        cfg_sim = 0.65 * node_sim + 0.35 * pred_sim

    if dfg_match:
        dfg_sim = 1.0
    else:
        q_edges = [(e.source, e.target, e.kind, e.expression_shape) for e in query.dfg.edges]
        c_edges = [(e.source, e.target, e.kind, e.expression_shape) for e in candidate.dfg.edges]
        q_defs = query.dfg.definitions
        c_defs = candidate.dfg.definitions
        dfg_sim = 0.6 * _jaccard(q_edges, c_edges) + 0.4 * _jaccard(q_defs, c_defs)

    if io_match:
        io_sim = 1.0
    else:
        arity_sim = 1.0 if query.io.arity == candidate.io.arity else (
            1.0 / (1.0 + abs(query.io.arity - candidate.io.arity))
        )
        ret_sim = _jaccard(query.io.return_shapes, candidate.io.return_shapes)
        async_sim = 1.0 if query.io.is_async == candidate.io.is_async else 0.0
        io_sim = 0.4 * arity_sim + 0.45 * ret_sim + 0.15 * async_sim

    if effects_match:
        effects_sim = 1.0
    else:
        call_sim = _jaccard(query.effects.call_Site_shapes, candidate.effects.call_Site_shapes)
        raise_sim = _jaccard(query.effects.raises, candidate.effects.raises)
        mut_sim = _jaccard(query.effects.mutations, candidate.effects.mutations)
        tag_sim = _jaccard(query.effects.effect_tags, candidate.effects.effect_tags)
        effects_sim = 0.45 * call_sim + 0.2 * raise_sim + 0.2 * mut_sim + 0.15 * tag_sim

    overall = (
        0.35 * cfg_sim
        + 0.35 * dfg_sim
        + 0.15 * io_sim
        + 0.15 * effects_sim
    )

    rationale: list[str] = []
    if exact_match:
        rationale.append("exact_alpha_normalized_structural_match")
    else:
        if cfg_match:
            rationale.append("cfg_exact_match")
        if dfg_match:
            rationale.append("dfg_exact_match")
        if io_match:
            rationale.append("io_exact_match")
        if effects_match:
            rationale.append("effects_exact_match")
        if not rationale:
            rationale.append("partial_structural_overlap")

    return StructuralSimilarityMatch(
        schema=STRUCTURAL_SIMILARITY_SCHEMA,
        query_symbol_id=query.symbol_id,
        candidate_symbol_id=candidate.symbol_id,
        exact_structural_match=exact_match,
        cfg_match=cfg_match,
        dfg_match=dfg_match,
        io_match=io_match,
        effects_match=effects_match,
        cfg_similarity=cfg_sim,
        dfg_similarity=dfg_sim,
        io_similarity=io_sim,
        effects_similarity=effects_sim,
        overall_similarity=overall,
        rationale=tuple(rationale),
        read_only=True,
        authority=ADVISORY_AUTHORITY,
        grants_authority=False,
    )


def rank_retrieval_candidates(
    query: StructuralFingerprint,
    candidates: Sequence[StructuralFingerprint],
    *,
    min_similarity: float = 0.0,
) -> tuple[StructuralSimilarityMatch, ...]:
    """Rank candidate symbols against ``query`` by advisory structural similarity."""
    matches = [
        compare_structural_fingerprints(query, candidate)
        for candidate in candidates
    ]
    filtered = [m for m in matches if m.overall_similarity >= min_similarity]
    filtered.sort(
        key=lambda m: (
            m.exact_structural_match,
            round(m.overall_similarity, 8),
            m.cfg_match,
            m.dfg_match,
            m.candidate_symbol_id,
        ),
        reverse=True,
    )
    return tuple(filtered)


__all__ = [
    "ADVISORY_AUTHORITY",
    "STRUCTURAL_EXPORT_SCHEMA",
    "STRUCTURAL_FINGERPRINT_SCHEMA",
    "STRUCTURAL_SIMILARITY_SCHEMA",
    "CFGEdgeRecord",
    "CFGNodeRecord",
    "ControlFlowFingerprint",
    "DataFlowEdgeRecord",
    "DataFlowFingerprint",
    "EffectsProfile",
    "IOProfile",
    "StructuralExportBundle",
    "StructuralFingerprint",
    "StructuralSimilarityMatch",
    "compare_structural_fingerprints",
    "export_structural_fingerprints",
    "extract_structural_fingerprints_from_source",
    "extract_symbol_fingerprint",
    "rank_retrieval_candidates",
]
