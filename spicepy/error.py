class SpiceAIError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message=message)

    def __str__(self) -> str:
        return f"Spice AI error: {self.message}"
