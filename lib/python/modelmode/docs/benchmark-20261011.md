# BANKING77 pilot — 11 October 2026

[Interactive report](https://storage.googleapis.com/binit-public/modelmode/20261011/report.html)
· [Raw public evidence](https://storage.googleapis.com/binit-public/modelmode/20261011/benchmark.json)

The first 12 alphabetically sorted intents, selected before evaluation, yielded
1,296 training / 324 validation / 479 test examples after normalized deduplication.
The official test partition was preserved; validation was sampled from official
training data. Source commit and input hashes are embedded in the report.

| Candidate | Validation macro F1 | Neural train loop | Entire fit | Warm CPU ms/item |
| --- | ---: | ---: | ---: | ---: |
| Character TF-IDF + logistic | 97.73% | — | 0.56 s | 0.094 |
| BERT-mini, pretrained | 96.94% | 6.89 s | 14.77 s | 1.863 |
| Word TF-IDF + logistic | 96.51% | — | 0.35 s | 0.037 |
| BERT-tiny, pretrained | 96.28% | 2.61 s | 6.38 s | 0.496 |
| BERT-tiny, random weights | 82.58% | 3.75 s | 17.95 s | 0.492 |

Neural runs used all weights, six epochs, batch size 32, max length 96, AdamW at
3e-4, seed 42, one Tesla T4. Model size including the 12-class head was 4.39M
parameters for BERT-tiny and 11.17M for BERT-mini. Inference was measured on the
Modal worker's CPU with two native threads, batches of 64 (internally 32 for
neural models), one warm-up and seven repeats. CPU model identification is not
available inside this Modal container.

The complete comparison took **78.13 seconds** including remote startup, model
loads, validation, serialization/reload verification and transfer. The remote
function took 48.90 seconds. Pure training times above are not end-to-end times;
candidate ordering and first-use kernel/import/cache costs affect both.

Selection used validation macro F1. Character TF-IDF won and was the only learned
candidate evaluated on final test: **98.13% macro F1 / 98.12% accuracy**, compared
with the dummy's 1.28% macro F1. The final test cohort is now sealed. Every model's
saved artifact was downloaded and reloaded locally; all validation confusion
matrices matched exactly and prediction scores matched to 1e-5 tolerance.

This is one seeded pilot on a subset, with no uncertainty intervals. It supports
BERT-tiny as an inexpensive trainable option, and shows why a linear baseline
belongs in ModelMode. It does not establish a universal speed or quality ranking.
The stronger model's contribution would be task definition, training labels and
failure analysis; this pilot used only the public dataset's provided labels.

A coordinator-PID check incorrectly emitted an intermediate failure message
inside the remote container. All candidates finished successfully. The original
status record was preserved locally, a documented metadata correction removed
the stale error, and a regression test now prevents that check inside remote
fitting. This did not change any model, metric, split or timing. New deployments
also bake source into the image and reject a caller/worker implementation hash
mismatch before training.

Data: PolyAI BANKING77, distributed under CC BY 4.0; this benchmark selects a subset,
deduplicates normalized inputs and adds a validation split.

## Neural-only publication check

A second, disjoint cohort uses alphabetic labels 13–16 (`card_arrival`,
`card_delivery_estimate`, `card_linking`, `card_not_working`): 412 train, 103
validation and 160 test examples. With only BERT-tiny as the learned candidate,
four epochs produced **89.39% test macro F1**, versus the dummy's 10%.
This verifies neural-model publication; it is not a comparison with the 12-intent
results above. Its final test is also sealed.

The updated remote implementation hash matched the installed package. A new MCP
process then loaded capability `neural_intent`, version 1, with Hugging Face and
Transformers offline modes enabled. It correctly classified the two smoke inputs
as `card_linking` and `card_not_working`. The complete
[verification receipt](https://storage.googleapis.com/binit-public/modelmode/20261011/neural-verification.json)
includes dataset provenance, the remote call ID, checksums, parameters and metrics.
