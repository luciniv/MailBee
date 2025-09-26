import sys

from loguru import logger

# Remove default sink
logger.remove()

# Add threaded (non-blocking) sink
logger.add(sys.stdout, enqueue=True, backtrace=True, diagnose=True)

# Creates custom logging levels
logger.level("SYSTEM", no=15, color="\033[38;5;51m\033[48;5;20m\033[1m")
logger.level("NOTIF", no=14, color="\033[38;5;39m\033[48;5;18m\033[1m")
