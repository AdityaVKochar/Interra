"""Deterministic admissibility checks independent of model wording."""


def compatible(call, state):
    if call.state.intent != state.intent:
        return False
    bindings = call.request.bindings
    if bindings is None:
        return call.state.slots == state.slots
    keys = set(bindings.values())
    return all(k in state.slots and k in call.state.slots
               and state.slots[k] == call.state.slots[k] for k in keys)
