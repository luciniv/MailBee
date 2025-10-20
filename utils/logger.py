import sys

from loguru import logger


# logger.remove()
# logger.add("mailbee.log", rotation="10 MB", retention="30 days", compression="zip")

logger.level("SYSTEM", no=15, color="\033[38;5;51m\033[48;5;20m\033[1m")
logger.level("NOTIF", no=14, color="\033[38;5;39m\033[48;5;18m\033[1m")
