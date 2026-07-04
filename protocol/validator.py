from runtime.state import ALLOWED_OUTPUT_TYPES


class ProtocolValidationError(ValueError):
    pass


class ProtocolOutputValidator:
    def validate(self, output):
        output_type = getattr(output, "type", None)
        content = getattr(output, "content", None)
        metadata = getattr(output, "metadata", None)

        if output_type not in ALLOWED_OUTPUT_TYPES:
            raise ProtocolValidationError(f"Invalid output type: {output_type}")

        if not isinstance(content, str):
            raise ProtocolValidationError("Output content must be a string.")

        if not isinstance(metadata, dict):
            raise ProtocolValidationError("Output metadata must be an object.")

        return output

