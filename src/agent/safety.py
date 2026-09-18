"""Session-local at-most-once dispatch ledger; cancellation never implies rollback."""
import hashlib
import json
from dataclasses import dataclass


@dataclass
class Operation:
    key: str
    fingerprint: str
    call_id: str
    status: str = "PENDING"


class SafetyLedger:
    def __init__(self):
        self.operations = {}
        self.fingerprints = {}

    @staticmethod
    def fingerprint(request):
        canonical = json.dumps([request.tool_name, request.arguments], sort_keys=True,
                               separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def reserve(self, request, call_id):
        fingerprint = self.fingerprint(request)
        key = request.operation_key or fingerprint
        # A new model-invented key cannot bypass identical-operation protection.
        if key in self.operations or fingerprint in self.fingerprints:
            return None
        operation = Operation(key, fingerprint, call_id)
        self.operations[key] = operation
        self.fingerprints[fingerprint] = key
        return operation

    def update(self, key, status):
        if key is not None:
            operation = self.operations[key]
            if operation.status != "COMMITTED":
                operation.status = status

    @property
    def uncertain(self):
        return any(op.status == "OUTCOME_UNKNOWN" for op in self.operations.values())
