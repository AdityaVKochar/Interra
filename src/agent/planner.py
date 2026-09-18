from .models import Proposal
from pydantic import ValidationError


async def propose(provider, context, repairs=0, on_invalid=None):
    for attempt in range(repairs + 1):
        raw = await provider.plan(context.model_copy(deep=True))
        try:
            return Proposal.model_validate_json(raw) if isinstance(raw, str) else Proposal.model_validate(raw)
        except ValidationError as exc:
            if on_invalid:
                on_invalid(attempt, str(exc))
            if attempt == repairs:
                raise
            context = context.model_copy(update={"input": {**context.input,
                "schema_error": str(exc), "instruction": "Return a corrected proposal matching the schema."}}, deep=True)
