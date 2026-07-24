import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REMOVED_TOP_LEVEL_PACKAGES = {
    "adapters",
    "archive",
    "core",
    "core_retriever",
    "prompt",
    "protocol",
    "runtime",
}
ACTIVE_PACKAGES = {
    "api",
    "application",
    "cli",
    "core_surface",
    "llm",
    "mcp_server",
    "runtime_compatibility",
    "semantic_executor",
}


def test_legacy_top_level_packages_are_absent():
    existing = {
        path.name
        for path in PROJECT_ROOT.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    }

    assert not (REMOVED_TOP_LEVEL_PACKAGES & existing)
    assert ACTIVE_PACKAGES <= existing


def test_active_python_modules_do_not_import_removed_packages():
    violations = []
    for package in sorted(ACTIVE_PACKAGES):
        for path in (PROJECT_ROOT / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                imported = _imported_top_level(node)
                if imported in REMOVED_TOP_LEVEL_PACKAGES:
                    violations.append(
                        f"{path.relative_to(PROJECT_ROOT)} imports {imported}"
                    )

    assert violations == []


def test_core_surface_is_the_only_canonical_core_source():
    provider_source = (
        PROJECT_ROOT / "application" / "context_provider.py"
    ).read_text(encoding="utf-8")
    projector_source = (
        PROJECT_ROOT / "application" / "context_projection.py"
    ).read_text(encoding="utf-8")

    assert "load_core_surface" in provider_source
    assert "project_core_context" in provider_source
    assert "CoreSurface" in projector_source
    assert "BORIS_CORE_RETRIEVER" not in provider_source
    assert "core/definitions" not in provider_source


def test_core_surface_remains_query_independent():
    assert not (PROJECT_ROOT / "core_surface" / "context.py").exists()

    violations = []
    for path in (PROJECT_ROOT / "core_surface").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imported = _imported_top_level(node)
            if imported in {
                "api",
                "application",
                "llm",
                "mcp_server",
                "runtime_compatibility",
                "semantic_executor",
            }:
                violations.append(
                    f"{path.relative_to(PROJECT_ROOT)} imports {imported}"
                )

    assert violations == []


def test_context_packet_v2_has_no_retriever_field_names():
    source = (
        PROJECT_ROOT / "application" / "context_packet.py"
    ).read_text(encoding="utf-8")

    assert 'PACKET_VERSION = "boris-context/2.0"' in source
    assert '"projected_core"' in source
    assert '"projection_metadata"' in source
    assert "retrieved_core" not in source
    assert "retrieval_metadata" not in source


def _imported_top_level(node):
    if isinstance(node, ast.Import) and node.names:
        return node.names[0].name.split(".", 1)[0]
    if isinstance(node, ast.ImportFrom) and node.module:
        return node.module.split(".", 1)[0]
    return None
