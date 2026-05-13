# Examples

This folder shows how `conflit` manages layered ML training configuration for
an imaginary model called **Orion**, across three YAML files that compose together.

## Files

- `base.yaml` — shared defaults: model architecture, optimizer, data paths, logging.
- `gpu_large.yaml` — full-scale GPU overrides using `!merge` to update nested
  dicts (larger model, bigger batches) and `!append` to accumulate feature flags.
- `hardware.yaml` — standalone GPU cluster spec, composed under the `hardware`
  namespace so all its keys land at `hardware.*` in the final config.
- `experiment.yaml` — the compose entry point: pulls in all layers with `_compose`,
  scoping `hardware.yaml` under the `hardware` key, adds experiment metadata,
  and appends one more feature flag.
- `compose_walkthrough.py` — notebook-style script that prints each raw YAML layer,
  shows the compose expansion into `(namespace, payload)` pairs, renders the final
  merged dict, and validates the result against a Pydantic model.

## Running the walkthrough

```bash
uv run python examples/compose_walkthrough.py
```

Or open `compose_walkthrough.ipynb` (generate first with `poe nb`) in Jupyter.

## What this demonstrates

| Feature | Where |
|---|---|
| Baseline defaults | `base.yaml` |
| Deep dict merge (`!merge`) | `gpu_large.yaml` — model, training, data, logging |
| List accumulation (`!append`) | `gpu_large.yaml` and `experiment.yaml` — features |
| Namespace routing (`namespace:`) | `experiment.yaml` — `hardware.yaml` scoped under `hardware.*` |
| Compose layering (`_compose`) | `experiment.yaml` |
| Pydantic validation (`schema=`) | `compose_walkthrough.py` — `OrionConfig` |
