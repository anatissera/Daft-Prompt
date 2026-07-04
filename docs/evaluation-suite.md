# Product Direction Evaluation Suite

Run the local product-direction evaluation without network access:

```bash
cd apps/api
python -m pytest tests/test_product_direction_evaluation.py
```

The suite covers:

- evidence-backed profile Q&A;
- expected `CompositionBrief` outputs for scratch, single-reference, and
  multi-reference prompts;
- symbolic composition validity and harmonic-fit smoke checks.

Fixtures are hand-authored and local. They do not include private audio, secrets,
or commercial assets.
