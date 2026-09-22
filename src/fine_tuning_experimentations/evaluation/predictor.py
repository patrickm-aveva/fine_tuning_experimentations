from typing import Protocol


class Predictor(Protocol):
    """Minimal interface a backend must implement to be comparator-compatible."""

    def generate_base(self, messages: list[dict]) -> str:
        """Generate SQL using the original, non-fine-tuned model."""
        ...

    def generate_finetuned(self, messages: list[dict]) -> str:
        """Generate SQL using the fine-tuned model/adapter."""
        ...