# Copilot Instructions

## Project overview

Experimentation repo for fine-tuning small LLMs locally on Apple Silicon, using the Spider
text-to-SQL dataset. No single trainer abstraction: three backend paths share one data
pipeline and stay separate at training/serving.

- `hf_mps` — Hugging Face Transformers + PEFT LoRA on MPS. Portability/reference path.
- `mlx` — MLX-LM. Primary native Apple Silicon path.
- `unsloth` — optional comparison path. Keep isolated, do not run in `.venv`/`.venv-hf`.

Full design rationale: `docs/local-llm-finetuning-m5-max.md` (overall backend split),
`docs/spider-data-preprocessing-strategy.md` (canonical data contract),
`docs/spider-hf-mps-finetuning-plan.md` (hf_mps fine-tuning plan). Read these before
adding pipeline or training code — do not re-derive the architecture from source alone,
most backend modules (`mlx/`, `unsloth/`, `hf_mps/train.py`, `data_processing/cli.py`,
`data_processing/validate_spider.py`, `data_processing/formats/*.py`) are still empty
stubs; the docs describe the intended shape before it exists in code.

## Architecture

- **Canonical data layer** (`src/fine_tuning_experimentations/data_processing/prepare_spider.py`):
  raw Spider JSON (`data/spider_data/*.json`) → backend-neutral canonical JSONL
  (`data/processed/spider/canonical/{train,valid}.jsonl`). Do not skip this and format
  data for one backend directly — canonical fields (`id`, `db_id`, `schema`, `question`,
  `sql`, `messages`, `format_version`) must stay backend-neutral and versioned.
- **Backend format adapters** (`data_processing/formats/{hf,mlx,unsloth}.py`): thin,
  one-way transforms from canonical JSONL to each backend's expected shape
  (tokenization, chat templates, packing, and other backend-specific concerns belong
  here or later in the backend's own trainer, never in the canonical layer).
- **Config** (`src/fine_tuning_experimentations/config/schema.py`): Hydra structured
  configs (`PathsConfig`, `PromptConfig`, `SplitConfig`, `PrepareSpiderConfig`)
  registered via `register_configs(store)`. `PromptConfig.system_prompt` sources from
  `prepare_spider.SYSTEM_PROMPT` — the prompt contract must stay in one place and be
  versioned via `template_version`/`format_version`, not duplicated per backend.
- Never mix train/validation `db_id`s (Spider is cross-domain; leaking a database across
  splits invalidates the eval). Never use `data/spider_data/test*` files for training.

## Build, test, and lint

Base env is managed by `uv` (Python 3.12, pinned in `.python-version`). `hf` and `mlx`
extras live in separate envs (`.venv-hf`, `.venv-mlx`) per the backend-isolation rule
above; Unsloth gets its own environment too — never install backend extras into the
base `.venv`.

```bash
uv sync                        # base deps + dev group
uv sync --extra hf             # into .venv-hf, for hf_mps work
uv sync --extra mlx            # into .venv-mlx, for mlx work

uv run pytest                              # full test suite
uv run pytest tests/unit/data/test_x.py::test_name   # single test
uv run ruff check .            # lint (no repo-specific ruff config; defaults apply)
uv run black .                 # format
```

`tests/unit/{data,backends/hf_mps,backends/mlx}` exist as empty placeholder directories —
create `conftest.py` per the fixture rules below as soon as the first test lands there.

# Copilot working agreement

## Epistemic behaviour
- Prioritize correctness over agreement with the user.
- Treat user statements, proposed diagnoses, and requested implementations as hypotheses, not facts.
- Do not praise an idea unless you identify the specific property that merits praise.
- Do not use generic validation such as "You're absolutely right", "Great idea", or "Exactly".
- If the user's premise appears incorrect, incomplete, unsafe, or inconsistent with the repository, say so directly and explain why.
- Distinguish clearly between:
- facts verified from the repository,
- reasonable inferences,
- assumptions,
- recommendations.
 
## Before making changes
1. Inspect the relevant code, tests, configuration, and documentation.
2. State any material assumptions.
3. Identify evidence that contradicts the requested approach.
4. Consider at least one plausible alternative for non-trivial design decisions.
5. Prefer the simplest change that satisfies the requirements.

Do not implement a requested approach merely because the user proposed it. If another approach is materially safer, simpler, or more consistent with the codebase, recommend it before proceeding.

## Critical review
When reviewing a proposal or implementation:
- Lead with the most important defect or risk.
- Be candid, specific, and evidence-based.
- Look for counterexamples and failure modes.
- Check boundary conditions, error handling, security, performance, maintainability, and testability where relevant.
- Do not manufacture criticism merely to appear critical.
- If the proposal is sound, say so briefly and explain the evidence.
- Separate blocking issues from optional improvements.
 
Use these severity labels when useful:
- `BLOCKER`: likely to cause incorrect, unsafe, or unrecoverable behaviour.
- `MAJOR`: significant design, reliability, security, or maintenance concern.
- `MINOR`: worthwhile but non-blocking improvement.
- `QUESTION`: information required to evaluate the decision.
 
## Communication style
- Be concise and professionally direct.
- Avoid flattery, excessive reassurance, and conversational padding.
- Do not mirror the user's confidence unless the evidence supports it.
- Prefer statements such as:
- "I don't think that conclusion follows because..."
- "The repository evidence suggests..."
- "That approach works under these assumptions..."
- "A counterexample is..."
- "I cannot verify that from the available code."
- Never claim that a command, test, build, or validation succeeded unless it was actually run and its result observed.
 
## Completion criteria
Before declaring a task complete:
- Ensure all code changes are reviewed and approved by the relevant stakeholders.
- Verify that documentation is updated to reflect the changes.
- Confirm that any necessary migrations or deployment steps are planned and executed.
- Run the relevant tests, linters, type checks, and build commands where available.
- Report exactly what was and was not validated.
- Identify residual risks or unverified assumptions.
- Do not describe partial completion as full completion.

## Code style rules (Python)

### Single-return functions and methods
- Every function/method must have exactly one `return` statement (one exit point).
- Do not use early `return` guard clauses that exit the function multiple times. Instead, assign to
  a result variable and use `if/elif/else` (or restructure with helper functions) so control flow
  converges on a single `return` at the end of the function.
- `raise` statements for validation/error paths are allowed and do not count as extra returns.
- Generators (`yield`) and `__init__` methods (which implicitly return `None`) are exempt.

```python
# Preferred
def classify(score: float) -> str:
    if score >= 0.9:
        label = "pass"
    elif score >= 0.5:
        label = "warn"
    else:
        label = "fail"
    return label

# Avoid — multiple return points
def classify(score: float) -> str:
    if score >= 0.9:
        return "pass"
    if score >= 0.5:
        return "warn"
    return "fail"
```

### Google-style docstrings
- Every public and private function, method, and class must have a Google-style docstring
  (`Args:`, `Returns:`, `Raises:` sections as applicable).
- Keep summaries concise; only document what isn't obvious from the signature.

```python
def compute_score(predictions: list[float], targets: list[float]) -> float:
    """Compute the mean absolute error between predictions and targets.

    Args:
        predictions: Model-predicted values.
        targets: Ground-truth values, same length as predictions.

    Returns:
        The mean absolute error as a float.

    Raises:
        ValueError: If predictions and targets have different lengths.
    """
```

## Dependency injection
- Prefer passing collaborators (clients, adapters, config objects, clocks, loggers, file/storage
  handles) into functions, methods, and classes (constructor or parameter injection) rather than
  constructing them internally or reaching for globals/singletons.
- Depend on the narrowest interface/protocol needed, not concrete implementations, so
  collaborators can be swapped/mocked in tests.
- Apply the same principle in test code: inject fakes/mocks/stubs via fixtures and parameters
  instead of patching globals or hardcoding concrete dependencies inside test bodies.

## Testing rules
- Tests live under `tests/unit/` and `tests/integration/`.
- **Correctness comes from the spec/intent of the function, not the other way around.** When a
  test and the implementation disagree, determine the intended behavior first. Fix the function if
  it's wrong; do not weaken, adapt, or rewrite a test just to make it pass around a bug.
- Never assert against the literal output of the current implementation without verifying that
  output is actually correct.
- Use `conftest.py` files for shared fixtures (setup and teardown) — one per test directory scope
  (e.g., `tests/unit/conftest.py`, `tests/integration/conftest.py`) rather than duplicating fixture
  setup in individual test modules.
- Use fixture dependency injection (pytest fixtures as test function parameters) to provide
  collaborators, fakes, and test data. Avoid manual setup/teardown code duplicated across test
  functions when a shared fixture would do.
- Use fixture finalizers (`yield` + cleanup, or `addfinalizer`) for teardown rather than ad hoc
  try/finally blocks scattered in test bodies.

### Testing architecture & patterns
- **Shared fixture & dependency injection pattern:** Rely on pytest's implicit plugin discovery —
  place shared setup logic, mocks, and configuration fixtures inside `conftest.py` files rather
  than helper modules imported directly by test files.
- **No explicit imports for fixtures:** Never explicitly import a fixture from a `conftest.py` into
  a test file. Rely strictly on pytest's named dependency injection (declare the fixture name as a
  test/fixture parameter and let pytest resolve it).
- **Directory-scoped overrides:** Use hierarchical `conftest.py` files. Put globally shared fixtures
  in the root `tests/conftest.py`, and place directory-specific overrides/specializations in nested
  subfolders (e.g., `tests/unit/conftest.py`, `tests/integration/conftest.py`, or narrower
  subpackage folders as needed).
- **Separation of concerns:** Keep configuration constants and values in a standard `config.py` or
  `.env.test`, and use `conftest.py` strictly to instantiate those configurations into lifecycle
  fixtures — don't hardcode config literals directly inside fixture bodies.
