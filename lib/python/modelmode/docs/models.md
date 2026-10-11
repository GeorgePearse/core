# Small models worth training

Start with **BERT-tiny** when minimum training/inference cost matters, and
**BERT-mini** when the task needs more capacity. These are contextual encoders,
not autoregressive chat models. They need a task head and supervised training;
ModelMode updates the whole encoder.

| Model | Approximate parameters | Why consider it? |
| --- | ---: | --- |
| [BERT-tiny](https://huggingface.co/google/bert_uncased_L-2_H-128_A-2) | 4.4M | Two layers, width 128. Very small contextual starting point. |
| [BERT-mini](https://huggingface.co/google/bert_uncased_L-4_H-256_A-4) | 11.3M | Four layers, width 256. More capacity while remaining small. |
| [ELECTRA-small](https://huggingface.co/google/electra-small-discriminator) | 13.5M | Strong small-model candidate, but 12 layers: parameter count is not latency. |

All three upstream Google releases use Apache-2.0. Counts are approximate and
change when a pretraining head is replaced with the task classifier. Every run
records its actual total and trainable parameter counts.

Google's [BERT Miniatures documentation](https://github.com/google-research/bert#bert-miniatures)
explicitly describes these models as suitable for limited compute and teacher
supervision. This makes them natural recipients for labels supplied by a stronger
model. ModelMode allows those labels in training only; independently reviewed
validation/test examples are still needed to assess real task quality.

A TF-IDF + logistic classifier is a serious baseline when training speed matters.
It learns from scratch, has no pretrained transformer, and may win on narrow
lexical tasks. Compare it on the same cohort before attributing gains to a neural
architecture. ModelMode includes word and character variants automatically only
when requested (plus an always-present majority-prior dummy).

`bert_tiny_random` is a matched randomly initialized architecture control, using
the same tokenizer and training schedule as `bert_tiny`. It is not pretrained from
scratch on a large language corpus. `training.initialization="random"` also works
for the other neural candidates.

Frozen Model2Vec and MiniLM remain optional comparison backends. They train a
classifier head, not encoder weights. In particular, Model2Vec's tiny static word
vectors are not contextual BERT models. They are not the main fine-tuning path.

## Reading the benchmark

The executable `examples/banking77.py` uses the first 12 alphabetic labels from
PolyAI's [BANKING77 dataset](https://github.com/PolyAI-LDN/task-specific-datasets),
pinned to a source commit with input checksums. It removes normalized duplicates,
keeps official test examples, and takes validation from official training data.
It reports a single seeded pilot, not an overall ranking across domains.

Training time excludes downloads and tokenization. `fit_seconds` includes those
costs. Total run time also includes queueing, startup, validation, checkpoint
serialization, reload verification and result transfer. Warm CPU inference is
measured with two native threads and batched inputs; it is neither cold latency
nor GPU throughput. ModelMode does not infer training speed from parameter count.
