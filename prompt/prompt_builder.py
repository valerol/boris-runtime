from core_retriever.retrieve import (
    CoreRetrieverError,
    core_retriever_debug_enabled,
    core_retriever_enabled,
    index_debug_summary,
    render_retrieved_chunks,
    retrieve_core_chunks,
)


class PromptBuilder:
    """Deterministic prompt builder for the protocol pipeline."""

    def build(self, core, sima_signals, bois_frame, boris_context, user_input, state):
        retrieved_chunks = self._retrieve_active_core(user_input)
        retrieved_core_section = self._render_active_core_section(retrieved_chunks)

        return "\n".join(
            [
                "BOIS/SIMA/BORIS MIDDLEWARE PROTOCOL",
                "Return exactly one JSON object:",
                '{',
                '  "type": "ANSWER" | "QUESTION" | "TOOL_CALL" | "GAP",',
                '  "content": "string",',
                '  "metadata": {}',
                '}',
                "Do not return plain text outside this schema.",
                "Do not echo the user question as QUESTION unless you genuinely need clarification according to the BOIS/SIMA/BORIS protocol.",
                "Use RETRIEVED_ACTIVE_CORE as the active BOIS Core context when it is present.",
                "Do not treat BOIS as a generic framework if specific BOIS/SIMA/BORIS terms are present.",
                "For analysis/comparison tasks, prefer BOIS/SIMA mechanism-level analysis over generic textbook categories.",
                "Keep the final response inside the JSON content field.",
                "",
                "IMMUTABLE_CORE:",
                str({
                    "bois_core": dict(core["bois_core"]),
                    "sima_rules": dict(core["sima_rules"]),
                    "boris_context": dict(core["boris_context"]),
                    "meta": dict(core["meta"]),
                }),
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
                retrieved_core_section,
                "",
                "USER_INPUT:",
                user_input,
            ]
        )

    @staticmethod
    def _retrieve_active_core(user_input):
        if not core_retriever_enabled():
            return []

        try:
            chunks = retrieve_core_chunks(user_input)
        except CoreRetrieverError:
            if core_retriever_debug_enabled():
                raise
            return []

        if core_retriever_debug_enabled():
            summary = index_debug_summary(chunks)
            print("========== BOIS CORE RETRIEVER (DEV MODE) ==========")
            print(f"source_path: {summary['source_path']}")
            print(f"source_sha256: {summary['source_sha256']}")
            print(f"chunks_count: {summary['chunks_count']}")
            print(f"selected_chunk_ids: {summary['selected_chunk_ids']}")
            print(f"selected_chunk_scores: {summary['selected_chunk_scores']}")
            print("====================================================")

        return chunks

    @staticmethod
    def _render_active_core_section(chunks):
        if not chunks:
            return ""

        return "\n".join((
            "RETRIEVED_ACTIVE_CORE:",
            render_retrieved_chunks(chunks),
        ))
