class LLMError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class LLMConfigurationError(LLMError):
    pass


class LLMAuthenticationError(LLMError):
    pass


class LLMTimeoutError(LLMError):
    pass


class LLMRateLimitError(LLMError):
    pass


class LLMProviderError(LLMError):
    pass


class LLMInvalidResponseError(LLMError):
    pass
