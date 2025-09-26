import discord
from discord.app_commands import CheckFailure
from discord.ext import commands

from utils.logger import *


# Base class for bot errors (handles general errors)
class BotError(commands.CommandError):
    def __init__(self, message: str):
        super().__init__(message)


# Raised if has_access fails
class AccessError(BotError):
    def __init__(self, message: str, required_permission: str = None):
        super().__init__(message)
        self.required_permission = required_permission

    def __str__(self):
        details = ""
        if self.required_permission:
            details += f"Required permission: {self.required_permission}"
        return f"{super().__str__()} \n({details})"


# Raised if has_access fails for app commands
class AppAccessError(CheckFailure):
    def __init__(self, message: str, required_permission: str = None):
        super().__init__(message)
        self.required_permission = required_permission

    def __str__(self):
        details = ""
        if self.required_permission:
            details += f"Required permission: {self.required_permission}"
        return f"{super().__str__()} \n({details})"


class StartupError(Exception):
    """Base class for startup-related errors."""

    pass


class DBConnectionError(StartupError):
    """Raised when database connection fails."""

    def __init__(self, original_exception: Exception):
        self.original_exception = original_exception
        super().__init__(f"Database connection failed: {original_exception}")


class CogLoadError(StartupError):
    """Raised when a cog fails to load."""

    def __init__(self, cog_name: str, original_exception: Exception):
        self.cog_name = cog_name
        self.original_exception = original_exception
        super().__init__(f"Failed to load cog '{cog_name}': {original_exception}")
