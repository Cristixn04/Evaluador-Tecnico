class InvitationError(Exception):
    pass


class InvitationNotFoundError(InvitationError):
    pass


class InvitationExpiredError(InvitationError):
    pass


class InvitationAlreadyUsedError(InvitationError):
    pass


class InvitationVacancyMismatchError(InvitationError):
    pass