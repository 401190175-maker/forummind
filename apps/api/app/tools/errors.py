"""Internal tool error categories."""


class ToolError(RuntimeError):
    """Base class for errors normalized by the registry."""


class ToolNotFoundError(ToolError):
    pass


class ToolAuthorizationError(ToolError):
    pass


class ToolArgumentsError(ToolError):
    pass


class ToolScopeError(ToolError):
    pass


class ToolExecutionFailure(ToolError):
    pass


class ToolProviderUnavailable(ToolExecutionFailure):
    """A configured external provider failed without exposing its details."""
