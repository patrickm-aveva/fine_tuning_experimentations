"""Hydra + Gradio entrypoint for side-by-side base-vs-fine-tuned SQL comparison (hf_mps backend)."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

import gradio as gr
import hydra
from hydra.core.config_store import ConfigStore
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, PreTrainedTokenizerBase

from fine_tuning_experimentations.config.comparator_schema import (
    ComparatorConfig,
    register_comparator_configs,
)
from fine_tuning_experimentations.data_processing.validate_spider import load_canonical_jsonl
from fine_tuning_experimentations.evaluation.comparison import (
    build_comparison_table,
    select_examples,
)
from fine_tuning_experimentations.hf_mps.device import resolve_device, resolve_dtype

register_comparator_configs(ConfigStore.instance())

COMPARISON_COLUMNS = [
    "id",
    "db_id",
    "question",
    "gold_sql",
    "base_sql",
    "base_parses",
    "base_string_match",
    "base_exec_match",
    "finetuned_sql",
    "finetuned_parses",
    "finetuned_string_match",
    "finetuned_exec_match",
]


def rows_to_table(rows: list[dict]) -> list[list]:
    """Convert comparison row dicts into gr.Dataframe-compatible row lists.

    Args:
        rows: Row dicts produced by build_comparison_table.

    Returns:
        One list per row, with values ordered to match COMPARISON_COLUMNS.
    """
    table = [[row[column] for column in COMPARISON_COLUMNS] for row in rows]
    return table


class HfPeftPredictor:
    """Predictor backed by a Hugging Face base model plus a PEFT LoRA adapter."""

    def __init__(
        self,
        model: PeftModel,
        tokenizer: PreTrainedTokenizerBase,
        device: str,
        max_new_tokens: int,
        do_sample: bool,
    ) -> None:
        """Initialize the predictor with an already-loaded model and tokenizer.

        Args:
            model: PeftModel wrapping the base weights and LoRA adapter.
            tokenizer: Tokenizer matching the model.
            device: Torch device the model is on.
            max_new_tokens: Maximum tokens to generate per prediction.
            do_sample: Whether to sample; False for deterministic SQL output.
        """
        self._model = model
        self._tokenizer = tokenizer
        self._device = device
        self._max_new_tokens = max_new_tokens
        self._do_sample = do_sample

    def _generate(self, messages: list[dict], use_adapter: bool) -> str:
        """Render a prompt from chat messages and generate SQL from it.

        Args:
            messages: Canonical record's full "messages" field.
            use_adapter: True for fine-tuned output, False for base-model-only output.

        Returns:
            The generated text, with the prompt stripped and whitespace trimmed.
        """
        prompt = self._tokenizer.apply_chat_template(
            messages[:2], tokenize=False, add_generation_prompt=True
        )
        inputs = self._tokenizer(prompt, return_tensors="pt").to(self._device)
        context = nullcontext() if use_adapter else self._model.disable_adapter()
        with context:
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=self._max_new_tokens,
                do_sample=self._do_sample,
                pad_token_id=self._tokenizer.pad_token_id,
            )
        generated = self._tokenizer.decode(
            output_ids[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True
        )
        result = generated.strip()
        return result

    def generate_base(self, messages: list[dict]) -> str:
        """Generate SQL using the original, non-fine-tuned model.

        Args:
            messages: Canonical record's full "messages" field.

        Returns:
            Predicted SQL text.
        """
        result = self._generate(messages, use_adapter=False)
        return result

    def generate_finetuned(self, messages: list[dict]) -> str:
        """Generate SQL using the fine-tuned model/adapter.

        Args:
            messages: Canonical record's full "messages" field.

        Returns:
            Predicted SQL text.
        """
        result = self._generate(messages, use_adapter=True)
        return result


def build_predictor(cfg: ComparatorConfig, device: str) -> HfPeftPredictor:
    """Load the tokenizer, base model, and adapter, and wrap them in a Predictor.

    Args:
        cfg: Resolved ComparatorConfig.
        device: Torch device to load the model onto.

    Returns:
        An HfPeftPredictor ready to generate base and fine-tuned predictions.
    """
    tokenizer = AutoTokenizer.from_pretrained(cfg.model.base_model_id, revision=cfg.model.revision)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(
        cfg.model.base_model_id,
        revision=cfg.model.revision,
        torch_dtype=resolve_dtype(device),
    ).to(device)
    model = PeftModel.from_pretrained(base_model, cfg.model.adapter_dir)

    predictor = HfPeftPredictor(
        model=model,
        tokenizer=tokenizer,
        device=device,
        max_new_tokens=cfg.generation.max_new_tokens,
        do_sample=cfg.generation.do_sample,
    )
    return predictor


@hydra.main(version_base=None, config_name="comparator_schema")
def main(cfg: ComparatorConfig) -> None:
    """Launch the base-vs-fine-tuned comparator for the hf_mps backend.

    Args:
        cfg: Hydra-resolved ComparatorConfig.

    Returns:
        None.
    """
    device = resolve_device()
    predictor = build_predictor(cfg, device)
    all_records = load_canonical_jsonl(Path(cfg.data.valid_path))
    database_root = Path(cfg.data.database_root)

    def run_comparison(sample_mode: str, sample_size: int, sample_seed: int):
        """Build the comparison table for the requested sample settings.

        Args:
            sample_mode: "random" or "all".
            sample_size: Number of examples when sample_mode is "random".
            sample_seed: Random seed for sampling.

        Returns:
            Comparison rows as a list of lists, ordered per COMPARISON_COLUMNS.
        """
        selected = select_examples(all_records, sample_mode, sample_size, sample_seed)
        rows = build_comparison_table(selected, predictor, database_root)
        table_rows = rows_to_table(rows)
        return table_rows

    with gr.Blocks() as demo:
        sample_mode = gr.Dropdown(choices=["random", "all"], value=cfg.sample.mode, label="Sample mode")
        sample_size = gr.Number(value=cfg.sample.size, label="Sample size", precision=0)
        sample_seed = gr.Number(value=cfg.sample.seed, label="Seed", precision=0)
        run_button = gr.Button("Run")
        table = gr.Dataframe(headers=COMPARISON_COLUMNS, wrap=True)

        run_button.click(
            fn=run_comparison,
            inputs=[sample_mode, sample_size, sample_seed],
            outputs=table,
        )

    demo.launch(server_name=cfg.server.host, server_port=cfg.server.port)


if __name__ == "__main__":
    main()