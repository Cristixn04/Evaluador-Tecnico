class VacancyParserError(Exception):
    pass


class VacancyParserInvalidInputError(VacancyParserError):
    pass


class VacancyParserInvalidResponseError(VacancyParserError):
    pass
