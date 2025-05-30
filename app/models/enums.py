import enum


class OwnerType(str, enum.Enum):
    """
    Enum representing the type of owner for resources.
    This allows for both user and team ownership in the future.
    """

    USER = "user"
    TEAM = "team"
