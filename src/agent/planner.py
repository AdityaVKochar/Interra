from .models import Proposal


async def propose(provider, context):
    raw = await provider.plan(context.model_copy(deep=True))
    return Proposal.model_validate_json(raw) if isinstance(raw, str) else Proposal.model_validate(raw)
