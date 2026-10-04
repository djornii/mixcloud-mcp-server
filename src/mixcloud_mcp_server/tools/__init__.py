"""Tool registration. Import order here decides nothing; each module registers
itself onto the server instance it is handed.
"""

from . import oauth, read, upload, write

MODULES = (read, write, upload, oauth)


def register(mcp) -> None:
    for module in MODULES:
        module.register(mcp)
