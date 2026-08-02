from abc import ABC, abstractmethod


class MailSource(ABC):
    """Abstract base for mail providers (Gmail, IMAP, POP, etc.)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique source identifier (e.g. 'gmail', 'imap')."""
        ...

    @property
    @abstractmethod
    def account(self) -> str:
        """Account identifier (e.g. 'user@gmail.com')."""
        ...

    @abstractmethod
    def check_new(self) -> list[dict]:
        """Return list of new messages since last check.
        Each dict: {id, from, subject, date, snippet, important}.
        """
        ...
