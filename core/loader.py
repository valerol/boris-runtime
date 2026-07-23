import json
from pathlib import Path

from core.core_lock import freeze
from core.normalizer import normalize_core
from core.resolver import resolve_github_release_reference, resolve_local_version
from core.validator import validate_core


CORE_FILE_EXTENSIONS = (".md", ".json", ".yaml", ".yml")


def load_core(reference):
    raw_core, metadata = _load_raw_core(reference)
    canonical = normalize_core(
        raw_core,
        source=metadata.get("source", ""),
        version=metadata.get("version", ""),
    )
    validate_core(canonical)
    return freeze(canonical)


def parse_md_core(path):
    text = Path(path).read_text(encoding="utf-8").strip()
    sections = _split_markdown_sections(text)

    if sections:
        return {
            "bois_core": sections.get("bois", {"content": text}),
            "sima_rules": sections.get("sima", {}),
            "boris_context": sections.get("boris", {}),
        }

    return {
        "bois_core": {
            "format": "md",
            "content": text,
        },
        "sima_rules": {},
        "boris_context": {},
    }


def parse_json_core(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_yaml_core(path):
    text = Path(path).read_text(encoding="utf-8")

    try:
        import yaml
    except ModuleNotFoundError:
        return _parse_simple_yaml(text)

    loaded = yaml.safe_load(text)
    return loaded or {}


def _load_raw_core(reference):
    if isinstance(reference, dict):
        if reference.get("type") == "github_release":
            metadata = resolve_github_release_reference(reference)
            return {
                "bois_core": {},
                "sima_rules": {},
                "boris_context": {},
            }, metadata

        metadata = {
            "source": reference.get("source", "structured-reference"),
            "version": reference.get("version", ""),
        }
        return reference, metadata

    path = Path(reference)
    metadata = resolve_local_version(path)

    if path.is_dir():
        return _load_folder_core(path), metadata

    if not path.is_file():
        raise FileNotFoundError(f"Core reference not found: {reference}")

    return _parse_file(path), metadata


def _load_folder_core(path):
    return {
        "bois_core": _load_component_file(path, "bois"),
        "sima_rules": _load_component_file(path, "sima"),
        "boris_context": _load_component_file(path, "boris"),
    }


def _load_component_file(path, component_name):
    for extension in CORE_FILE_EXTENSIONS:
        candidate = path / f"{component_name}{extension}"
        if candidate.exists():
            if candidate.suffix.lower() == ".md":
                return {
                    "format": "md",
                    "content": candidate.read_text(encoding="utf-8").strip(),
                }
            parsed = _parse_file(candidate)
            return _extract_component(parsed, component_name)
    return {}


def _parse_file(path):
    suffix = path.suffix.lower()

    if suffix == ".md":
        return parse_md_core(path)

    if suffix == ".json":
        return parse_json_core(path)

    if suffix in {".yaml", ".yml"}:
        return parse_yaml_core(path)

    raise ValueError(f"Unsupported core file format: {path}")


def _extract_component(parsed, component_name):
    canonical_keys = {
        "bois": "bois_core",
        "sima": "sima_rules",
        "boris": "boris_context",
    }
    canonical_key = canonical_keys[component_name]

    if isinstance(parsed, dict):
        if canonical_key in parsed:
            return parsed[canonical_key]
        if component_name in parsed:
            return parsed[component_name]

    return parsed


def _split_markdown_sections(text):
    sections = {}
    current = None
    buffer = []

    for line in text.splitlines():
        stripped = line.strip().lower().lstrip("#").strip()
        if stripped in {"bois", "sima", "boris"}:
            if current:
                sections[current] = {"format": "md", "content": "\n".join(buffer).strip()}
            current = stripped
            buffer = []
            continue

        if current:
            buffer.append(line)

    if current:
        sections[current] = {"format": "md", "content": "\n".join(buffer).strip()}

    return sections


def _parse_simple_yaml(text):
    result = {}
    current_key = None
    current_block = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        if not line.startswith((" ", "\t")) and ":" in stripped:
            if current_key and current_block:
                result[current_key] = "\n".join(current_block).strip()
                current_block = []

            key, value = stripped.split(":", 1)
            current_key = key.strip()
            value = value.strip()
            if value:
                result[current_key] = value.strip('"').strip("'")
                current_key = None
            else:
                result[current_key] = {}
            continue

        if current_key:
            current_block.append(stripped)

    if current_key and current_block:
        result[current_key] = "\n".join(current_block).strip()

    return result
