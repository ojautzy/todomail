"""Strategie de gestion d'erreur pour TodoMail.

Trois modes :
- lenient (defaut) : log l'erreur, continue le cycle
- strict (opt-in via --strict) : stop a la premiere erreur
- resume (toujours actif) : enregistre chaque erreur dans state.json
  pour permettre --retry
"""

from enum import Enum


class ErrorAction(Enum):
    """Action a prendre apres une erreur."""
    CONTINUE = "continue"
    STOP_AND_ASK = "stop_and_ask"
    RETRY_LATER = "retry_later"


class ErrorHandler:
    """Handle errors according to the configured mode."""

    def __init__(self, mode: str = "lenient") -> None:
        if mode not in ("lenient", "strict"):
            raise ValueError(f"Invalid error mode: {mode!r}. Must be 'lenient' or 'strict'.")
        self.mode = mode

    def handle(self, exc: Exception, context: dict) -> ErrorAction:
        """Process an exception and decide what to do.

        context should contain at minimum:
        - mail_id: str
        - phase: str

        Always records the error in state.json (resume is always active).
        Returns the appropriate ErrorAction based on mode.
        """
        from lib.state import record_error

        mail_id = context.get("mail_id", "unknown")
        phase = context.get("phase", "unknown")
        error_type = type(exc).__name__
        message = str(exc)

        record_error(mail_id, phase, error_type, message)

        if self.mode == "strict":
            return ErrorAction.STOP_AND_ASK
        return ErrorAction.CONTINUE

    @staticmethod
    def should_retry(error: dict) -> bool:
        """Check if an error should be retried.

        Returns True if retry_count < 3 and not permanent_failure.
        """
        return (
            error.get("retry_count", 0) < 3
            and not error.get("permanent_failure", False)
        )
