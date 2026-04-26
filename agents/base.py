"""Shared base class for all scheduled agents."""
import logging
import time
from abc import ABC, abstractmethod

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    level=logging.INFO,
)


class BaseAgent(ABC):
    """Wraps run() with retry logic and structured logging.

    Subclasses implement run(). Call execute() from the scheduler.
    """

    max_retries: int = 3
    retry_delay: float = 5.0  # seconds between retries

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def run(self) -> None:
        """Main agent logic. Raises on unrecoverable errors."""

    def execute(self) -> None:
        """Run with retry logic. Called by the scheduler."""
        for attempt in range(1, self.max_retries + 1):
            try:
                self.logger.info("Starting (attempt %d/%d)", attempt, self.max_retries)
                self.run()
                self.logger.info("Completed successfully")
                return
            except Exception as exc:
                self.logger.error(
                    "Attempt %d/%d failed: %s",
                    attempt, self.max_retries, exc,
                    exc_info=True,
                )
                if attempt < self.max_retries:
                    self.logger.info(
                        "Retrying in %.0f seconds...", self.retry_delay
                    )
                    time.sleep(self.retry_delay)
                else:
                    self.logger.error(
                        "All %d attempts failed. Giving up.", self.max_retries
                    )
