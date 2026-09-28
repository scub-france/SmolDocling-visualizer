# Fine-tuning Laya for section selection (pilot)

Question: does fine-tuning turn Laya into a reliable section selector? The model is trained on
Qasper, where the answer location comes for free, then tested on held-out Qasper papers and on the
13 hand-checked cases of `../cases.json` (Docling trees, never used for training).

The task is the F2 variant of `../run_variants.py`: one yes/no question per section,
`Does passage help answer query?`, with the passage `Section › Subsection: <first 400 characters>`.
Sections are opened by decreasing P(yes).

## Pipeline

Run from the repository root.

```bash
uv run experiments/laya-nav-test/finetune/build_qasper.py
uv run experiments/laya-nav-test/finetune/evaluate.py --scorer laya:convaiinnovations/laya --scorer granite --scorer bm25 --name zero-shot
uv run experiments/laya-nav-test/finetune/train.py --out checkpoints/qasper-v1
uv run experiments/laya-nav-test/finetune/evaluate.py --scorer laya:checkpoints/qasper-v1 --name qasper-v1
```

1. `build_qasper.py` downloads Qasper (Parquet, about 26 MB) and maps every evidence paragraph to
   its section. A section's relevance is the share of the question's annotators whose evidence falls
   in it. Evidence that cites a figure or a table is skipped, and questions whose annotators all
   answered "unanswerable" are dropped.
2. `evaluate.py` scores every section of each question's paper and reports found within 1, 3 and 5
   openings, the mean number of openings, and for Laya the AUROC and ECE of the top section's
   P(yes) against a first-try hit. Random order is computed analytically.
3. `train.py` runs the RLCD recipe of the official notebook, then fits the yes/no temperature on
   validation papers. The output directory loads with `laya.load(...)`.

## Data

| Split | Papers | Questions kept | Sections per question | Relevant per question | Training pairs |
|---|---|---|---|---|---|
| train | 888 | 2,098 of 2,593 | 15.5 | 1.21 | 15,055 (2,543 positive) |
| validation | 281 | 888 of 1,005 | 14.6 | 1.41 | 6,492 (1,250 positive) |
| test | 416 | 1,309 of 1,451 | 14.7 | 1.60 | none, evaluation only |

Training pairs are every relevant section plus 6 negatives per question: 3 of the closest by BM25,
3 at random. 96% of the text evidence maps to a section; the rest is ignored.

## Time and hardware

- Apple M3 Max (MPS, fp32): about 1.1 s per batch of 8 pairs, so about 35 minutes per epoch and
  1 h 15 for the default 2 epochs. Evaluating one Laya model on Qasper test takes about 6 minutes.
- CUDA (a free Kaggle T4 or a rented GPU): `--device cuda` turns on fp16 autocast. Add
  `--gradient-checkpointing` on a 16 GB card.

## What stays held out

- Qasper test papers never reach training, and the temperature is fitted on validation papers.
- The 13 hand-checked cases are never used for training or tuning. They measure transfer from
  Qasper's S2ORC sections to Docling structure.
- Tune hyperparameters on validation (`evaluate.py --split validation`), never on test or on the 13
  cases.

## Differences from the official notebook

- One process instead of DDP over two GPUs, and 2 epochs by default instead of 4.
- Yes/no section items instead of the typed-decisions workflows.
- The temperature is fitted on validation papers rather than on a slice of the training items.
- `max_len` and `head_max_len` stay at the checkpoint's 512 and 192: the notebook raises them for
  long typed-decision states, and our sequences are about 150 tokens.

## Caveats

- Training passages come from S2ORC text, with placeholders such as `FIGREF1`, while the 13 cases
  come from Docling. The shift is intended, but it is a shift.
- The temperature is fitted on positives plus sampled negatives, not on the full set of sections seen
  at inference.

## Licences

Qasper: CC BY 4.0 (AllenAI). Laya and its fine-tuning notebook: Apache 2.0. Granite reranker:
Apache 2.0.
