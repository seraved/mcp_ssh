class MCPSSHError(Exception):
    """Base error for all mcp_ssh failures."""


class HostNotFoundError(MCPSSHError):
    pass


class MissingEnvError(MCPSSHError):
    def __init__(self, var_name: str):
        self.var_name = var_name
        super().__init__(f"Required environment variable is not set: {var_name}")


class AuthError(MCPSSHError):
    pass


class ConnectionFailedError(MCPSSHError):
    pass


class HostKeyError(MCPSSHError):
    pass
