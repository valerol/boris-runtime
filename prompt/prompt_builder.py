import json

from core_retriever.retrieve import (
    CoreRetrieverError,
    core_retriever_debug_enabled,
    core_retriever_enabled,
    render_retrieved_chunks,
    retrieve_core_context,
)


class PromptBuilder:
    """Deterministic prompt builder for the protocol pipeline."""

    def __init__(self):
        self.last_context = {}

    def build(
        self,
        core,
        sima_signals,
        bois_frame,
        boris_context,
        user_input,
        state,
        core_context=None,
    ):
        core_context = core_context or self._build_core_context(core, user_input)
        clarification_context = self._build_clarification_context(user_input, state)
        split_input = self._split_clarifications(user_input)
        self.last_context = {
            "core": core_context["metadata"],
            "clarification": clarification_context,
        }

        sections = [
            "BOIS/SIMA/BORIS MIDDLEWARE PROTOCOL",
            "Return exactly one JSON object:",
            "{",
            '  "type": "ANSWER" | "QUESTION" | "TOOL_CALL" | "GAP",',
            '  "content": "string",',
            '  "metadata": {}',
            "}",
            "Do not return plain text outside this schema.",
            "Do not echo the user question as QUESTION unless you genuinely need clarification according to the BOIS/SIMA/BORIS protocol.",
            "If the response asks the user to clarify, specify, provide details, provide missing information, choose among alternatives, or supply evidence, the JSON type must be QUESTION, not ANSWER.",
            "ANSWER must contain a final answer or a clear limitation statement that does not require user input.",
            "QUESTION must be used for any user-facing request for missing information.",
            "Do not put please clarify or equivalent clarification requests inside ANSWER content.",
            "Use RETRIEVED_ACTIVE_CORE as the active BOIS Core context when it is present.",
            "Do not treat BOIS as a generic framework if specific BOIS/SIMA/BORIS terms are present.",
            "For analysis/comparison tasks, prefer BOIS/SIMA mechanism-level analysis over generic textbook categories.",
            "Keep the final response inside the JSON content field.",
            "If CLARIFICATION_CONTEXT.is_clarification_turn is true, first evaluate whether USER_CLARIFICATIONS resolves the previous question.",
            "On a clarification turn, do not return the same QUESTION as PREVIOUS_TURN.",
            "On a clarification turn, do not ask for information that was just supplied in USER_CLARIFICATIONS.",
            "On a clarification turn, prefer ANSWER when the supplied clarification is sufficient.",
            "If still insufficient, ask a narrower new QUESTION and identify the still-missing field in metadata.missing_fields or metadata.gap_key.",
            "Never return a duplicate clarification question after a clarification has been supplied.",
            "",
            core_context["source_section"],
            "",
            "SIMA_SIGNALS:",
            str(sima_signals),
            "",
            "BOIS_FRAME:",
            str(bois_frame),
            "",
            "BORIS_CONTEXT:",
            str(boris_context),
            "",
            "CURRENT_STATE:",
            str(state.snapshot()),
            "",
            "PREVIOUS_TURN:",
            str(state.last_decision),
            "",
        ]

        if core_context["retrieved_section"]:
            sections.extend([core_context["retrieved_section"], ""])

        if clarification_context["is_clarification_turn"]:
            sections.extend([
                "CLARIFICATION_CONTEXT:",
                json.dumps(clarification_context, ensure_ascii=False, indent=2),
                "",
            ])

        if split_input["has_clarifications"]:
            sections.extend([
                "ORIGINAL_REQUEST:",
                split_input["original_request"],
                "",
                "USER_CLARIFICATIONS:",
                "\n".join(split_input["clarifications"]),
                "",
            ])

        sections.extend([
            "USER_INPUT:",
            user_input,
        ])

        if core_retriever_debug_enabled():
            self._print_debug(core_context, clarification_context, split_input)

        return "\n".join(sections)

    @staticmethod
    def _build_core_context(core, user_input):
        if core_retriever_enabled():
            try:
                context = retrieve_core_context(user_input)
            except CoreRetrieverError:
                if core_retriever_debug_enabled():
                    raise
            else:
                manifest = context["manifest"]
                source = {
                    "source_path": manifest.get("source_path", ""),
                    "source_sha256": manifest.get("source_sha256", ""),
                    "model_name": manifest.get("model_name", ""),
                    "chunks_count": manifest.get("chunks_count", 0),
                    "active_core_version": _active_core_version(manifest, context["chunks"]),
                }
                return {
                    "mode": "external",
                    "source_section": "\n".join((
                        "EXTERNAL_CORE_SOURCE:",
                        json.dumps(source, ensure_ascii=False, indent=2),
                    )),
                    "retrieved_section": "\n".join((
                        "RETRIEVED_ACTIVE_CORE:",
                        context["rendered"],
                    )),
                    "rendered_active_core": context["rendered"],
                    "chunks": context["chunks"],
                    "metadata": {
                        "core_source": "external",
                        "core_version": source["active_core_version"],
                        "core_source_path": source["source_path"],
                        "core_source_sha256": source["source_sha256"],
                        "core_model_name": source["model_name"],
                        "core_chunks_count": source["chunks_count"],
                        "retriever_enabled": True,
                        "retrieved_chunk_count": len(context["chunks"]),
                    },
                }

        local_source = {
            "bois_core": dict(core["bois_core"]),
            "sima_rules": dict(core["sima_rules"]),
            "boris_context": dict(core["boris_context"]),
            "meta": dict(core["meta"]),
        }
        return {
            "mode": "local_fallback",
            "source_section": "\n".join((
                "LOCAL_FALLBACK_CORE:",
                str(local_source),
            )),
            "retrieved_section": "",
            "rendered_active_core": "",
            "chunks": [],
            "metadata": {
                "core_source": "local_fallback",
                "core_version": core["meta"].get("version", "local"),
                "core_source_path": core["meta"].get("source", ""),
                "core_source_sha256": core["meta"].get("hash", ""),
                "core_model_name": "",
                "core_chunks_count": 0,
                "retriever_enabled": core_retriever_enabled(),
                "retrieved_chunk_count": 0,
            },
        }

    @staticmethod
    def _build_clarification_context(user_input, state):
        split_input = PromptBuilder._split_clarifications(user_input)
        previous = _last_asked_question(state)
        is_clarification_turn = any((
            getattr(state, "clarification_cycles", 0) > 0,
            getattr(state, "last_output_type", None) == "CLARIFIED",
            split_input["has_clarifications"],
            bool(getattr(state, "asked_questions", [])) and split_input["has_clarifications"],
        ))

        return {
            "is_clarification_turn": is_clarification_turn,
            "clarification_cycles": getattr(state, "clarification_cycles", 0),
            "max_clarification_cycles": getattr(state, "max_clarification_cycles", 0),
            "previous_question": previous.get("question", ""),
            "previous_gap_key": previous.get("gap_key", ""),
            "clarification_policy": [
                "The user has already provided a clarification for the previous question.",
                "Treat the clarification as additional information for the original request.",
                "Do not repeat the previous clarification question.",
                "If the clarification resolves the missing information, return ANSWER.",
                "Return QUESTION only if a materially new missing field remains.",
                "A new QUESTION must not be semantically equivalent to any previous asked question.",
                "If the input is still insufficient, ask one narrower non-duplicate clarification question.",
            ],
        }

    @staticmethod
    def _split_clarifications(user_input):
        marker = "Clarification:"
        if marker not in user_input:
            return {
                "has_clarifications": False,
                "original_request": user_input,
                "clarifications": [],
            }

        original, *clarifications = user_input.split(marker)
        return {
            "has_clarifications": True,
            "original_request": original.strip(),
            "clarifications": [
                clarification.strip()
                for clarification in clarifications
                if clarification.strip()
            ],
        }

    @staticmethod
    def _print_debug(core_context, clarification_context, split_input):
        selected_scores = {
            chunk.get("id"): chunk.get("score")
            for chunk in core_context["chunks"]
        }
        print("========== BOIS CORE PROMPT CONTEXT (DEV MODE) ==========")
        print(f"core_mode: {core_context['mode']}")
        print(f"source_path: {core_context['metadata'].get('core_source_path', '')}")
        print(f"source_sha256: {core_context['metadata'].get('core_source_sha256', '')}")
        print(f"chunks_count: {core_context['metadata'].get('core_chunks_count', 0)}")
        print(f"retrieved_chunk_count: {core_context['metadata'].get('retrieved_chunk_count', 0)}")
        print(f"selected_chunk_ids: {[chunk.get('id') for chunk in core_context['chunks']]}")
        print(f"selected_chunk_scores: {selected_scores}")
        print("rendered_active_core:")
        print(core_context["rendered_active_core"])
        print(f"is_clarification_turn: {clarification_context['is_clarification_turn']}")
        print(f"previous_question: {clarification_context.get('previous_question', '')}")
        if split_input["has_clarifications"]:
            print("original_request:")
            print(split_input["original_request"])
            print("user_clarifications:")
            print("\n".join(split_input["clarifications"]))
        print("=========================================================")


def _active_core_version(manifest, chunks):
    for chunk in chunks:
        if chunk.get("id") == "core:metadata":
            text = chunk.get("text", "")
            for line in text.splitlines():
                if '"version"' in line or "'version'" in line:
                    return line.split(":", 1)[-1].strip().strip('",')
    return manifest.get("source_sha256", "")[:12] or "external"


def _last_asked_question(state):
    asked = getattr(state, "asked_questions", []) or []
    if asked:
        return asked[-1]
    last_decision = getattr(state, "last_decision", {}) or {}
    if last_decision.get("type") == "QUESTION":
        return {
            "question": last_decision.get("content", ""),
            "gap_key": last_decision.get("metadata", {}).get("gap_key", ""),
        }
    return {}
