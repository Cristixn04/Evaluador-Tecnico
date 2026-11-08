class LLMError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class LLMConfigurationError(LLMError):
    pass


class LLMAuthenticationError(LLMError):
    pass


class LLMTimeoutError(LLMError):
    def __init__(self, message: str, *, is_uncertain: bool = True) -> None:
        super().__init__(message)
        self.is_uncertain = is_uncertain


class LLMRateLimitError(LLMError):
    pass


class LLMProviderError(LLMError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        headers: object = None,
        gateway_metadata: dict[str, str] | None = None,
        is_uncertain: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.headers = headers
        self.gateway_metadata = gateway_metadata or {}
        self.is_uncertain = is_uncertain


class LLMInvalidResponseError(LLMError):
    def __init__(
        self,
        message: str,
        *,
        gateway_metadata: dict[str, str] | None = None,
        is_uncertain: bool = True,
    ) -> None:
        super().__init__(message)
        self.gateway_metadata = gateway_metadata or {}
        self.is_uncertain = is_uncertain
