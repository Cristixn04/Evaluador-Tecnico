class SandboxError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class SandboxConfigurationError(SandboxError):
    pass


class SandboxTimeoutError(SandboxError):
    pass


class SandboxProviderError(SandboxError):
    pass


class SandboxInvalidResponseError(SandboxError):
    pass


class SandboxUnavailableError(SandboxError):
    pass
