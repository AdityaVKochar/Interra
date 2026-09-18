from jsonschema import Draft202012Validator
from ..models import ToolSpec


def normalize_manifest(tools: list[dict]) -> dict[str, ToolSpec]:
    result = {}
    for raw in tools:
        spec = ToolSpec.model_validate(raw)
        Draft202012Validator.check_schema(spec.argument_schema)
        if spec.argument_schema.get("type") != "object":
            raise ValueError("tool arguments must be an object schema")
        if spec.name in result:
            raise ValueError("duplicate tool name")
        result[spec.name] = spec.model_copy(deep=True)
    return result
