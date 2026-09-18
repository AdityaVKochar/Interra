from jsonschema import Draft202012Validator
from .manifest import normalize_manifest


class ToolRegistry:
    def __init__(self):
        self._specs = {}
        self._validators = {}

    def replace(self, tools):
        specs = normalize_manifest(tools)
        validators = {
            name: Draft202012Validator(spec.argument_schema)
            for name, spec in specs.items()
        }
        self._specs = specs
        self._validators = validators

    @property
    def specs(self):
        return [spec.model_copy(deep=True) for spec in self._specs.values()]

    def validate(self, request, state):
        if request.tool_name not in self._specs:
            raise ValueError("unknown tool")
        spec = self._specs[request.tool_name]
        self._validators[request.tool_name].validate(request.arguments)
        if request.bindings is not None:
            if set(request.bindings) != set(request.arguments):
                raise ValueError("explicit bindings must cover every argument")
            for argument, slot in request.bindings.items():
                if slot not in state.slots or request.arguments[argument] != state.slots[slot]:
                    raise ValueError("argument does not match bound slot")
        return spec.model_copy(deep=True)
