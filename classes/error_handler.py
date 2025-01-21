import discord
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
        return f"{super().__str__()} \n\n({details})"


# Add more error classes if needed
