class ResearchAssistantError(Exception):
    """Base application exception."""


class PlanningError(ResearchAssistantError):
    pass


class RetrievalError(ResearchAssistantError):
    pass


class EvidenceValidationError(ResearchAssistantError):
    pass
