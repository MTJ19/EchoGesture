# EchoGesture

EchoGesture is an experimental ASL recognition app built with Flask, MediaPipe and scikit-learn. It provides separate studios for fingerspelling and short, isolated word signs, with text composition and speech playback.

## Current status — 27 November 2026

| Area | Implemented behaviour |
| --- | --- |
| Alphabet Studio | 24 static letters (A–I and K–Y), webcam and image/video uploads, landmark overlay and stable letter recognition |
| J/Z motion | Experimental automatic recognition in webcam/video input; reliability remains unresolved |
| Word Studio | Default 50-word showcase backed by the existing 81-class checkpoint; one recorded or uploaded sign at a time |
| Text and speech | Manual letter assembly, spaces, deletion, clearing, copying and full-message speech; letter/word voice playback |
| Interface | Green-and-cream landing page, sage hand artwork, smooth “How it works” scrolling and enlarged camera previews in both studios |
| Demonstration clips | `testproj/` contains 44 previously successful clips across 15 words, with results and source records |

This is isolated-sign recognition and manual fingerspelling composition. Continuous sign-language translation, automatic sentence recognition and reliable general webcam accuracy have not been established.

## Run locally

Use Python 3.9–3.12 and the pinned MediaPipe version in `requirements.txt`. Newer MediaPipe releases may not expose the legacy `mp.solutions` API used here.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open:

- [Landing page](http://127.0.0.1:8080/)
- [Alphabet Studio](http://127.0.0.1:8080/sign)
- [Word Studio](http://127.0.0.1:8080/words)
- [Alphabet development tools](http://127.0.0.1:8080/sign?tools=1)

Allow camera access when prompted. Word recordings are three seconds; uploaded word clips must be no longer than ten seconds and no larger than 8 MB. Clips are deleted after prediction and are not automatically added to training. The development server binds to this computer only.

**A fresh clone does not include trained weights, the full research datasets or cached landmarks.** Install dependencies and obtain or reproduce the required trusted model artifacts before expecting recognition. The existing local workspace contains those artifacts. Example-video playback additionally needs local training videos and their quality manifest. Never load untrusted joblib files.

`requirements-lock.txt` records the original tested Apple-silicon Python 3.9 environment.

## Word recognition

When `models/word81-grammar-candidate.joblib` is present, the default is `showcase50`. The displayed vocabulary is defined in [`config/showcase50.json`](config/showcase50.json). This is a restricted interface over the 81-class model, not a newly trained 50-class model. A top prediction outside the showcase vocabulary is withheld.

The SVM variants also require the base `models/words20-candidate.joblib` bundle. Without the 81-class checkpoint, default selection falls back to the available 80-word checkpoint or the earlier prototype; missing required artifacts prevent recognition.

To select a variant explicitly:

```sh
ECHOGESTURE_WORD_MODEL=showcase50 python app.py
# Full 81-class vocabulary:
ECHOGESTURE_WORD_MODEL=word81-svm python app.py
# Earlier 80-word checkpoint:
ECHOGESTURE_WORD_MODEL=word80-svm python app.py
```

The 50 showcase words are:

> accident, apple, before, black, book, brown, chair, class, clothes, color, computer, cow, dance, door, enjoy, family, finish, go, grammar, green, hearing, hot, language, later, like, man, meet, mother, need, no, now, orange, paint, pink, play, purple, red, secretary, son, table, teacher, thin, visit, wait, water, white, work, year, yellow, yes.

Use **Speak result** or **Enable voice** for spoken predictions. Unfamiliar signs can still receive incorrect supported labels; model decision scores are not calibrated confidence.

## Recorded evaluation and limitations

| Evaluation | Recorded result | Interpretation |
| --- | --- | --- |
| Original static-letter baseline | 90.98% accuracy on 1,198 successfully extracted held-out-signer images | Public-dataset pilot; does not measure the later personalized model or live camera reliability |
| Dictionary word screening | 53/86 correct across 44 words | Existing 81-class upload pipeline; small, now-inspected evaluation batch |
| Additional word retest | 14/28 correct across 16 previously promising words | Shows that initial 2/2 results did not consistently repeat |

Language, orange and son scored 4/4 across the screening and retest; table and teacher scored 3/3. These small selected counts do not establish general accuracy. Source/hash checks do not prove signer independence or exclude every re-encoded duplicate. Screening used the full 81-class pipeline, rather than a separately evaluated 50-class model.

See [`reports/RESULTS.md`](reports/RESULTS.md), [`reports/showcase-fresh50-summary.csv`](reports/showcase-fresh50-summary.csv) and [`reports/showcase-retest19-summary.csv`](reports/showcase-retest19-summary.csv).

The live static acceptance setting remains 30%, with four-frame stability and no-hand/multiple-hand rejection. The original saved baseline used 70%. Lowering the cutoff can increase incorrect acceptance. J/Z motion is enabled experimentally; its development replays and synthetic checks are not independent live evaluations.

## Try the selected demonstration clips

[`testproj/`](testproj/) groups 44 clips by 15 expected words: clothes, dance, enjoy, family, hearing, language, like, mother, no, orange, paint, son, table, teacher and white.

Upload a clip in Word Studio. Read [`testproj/README.txt`](testproj/README.txt), [`sources.csv`](testproj/sources.csv) and [`word-results.csv`](testproj/word-results.csv) for provenance and complete per-word attempt counts. These clips were selected because they previously worked; they are demonstration examples, not a fresh accuracy test. Original source rights still apply.

## Google Colab showcase

[Open the showcase notebook](https://colab.research.google.com/github/MTJ19/EchoGesture/blob/main/notebooks/EchoGesture_Showcase.ipynb).

The notebook supports letter-image uploads, experimental J/Z videos, 81-word video inference, model inspection and labelled evaluation. It targets the 2026.07 Colab runtime with Python 3.12. Authentication may be needed for repository access, and required model/data artifacts must be available. Hosted Colab execution has not been fully verified. Uploaded media is processed in the Colab runtime, rather than solely on your computer.

## Data and training

Read [`datasets/README.md`](datasets/README.md) and [`datasets/DATASET_REPORT.md`](datasets/DATASET_REPORT.md) for sources, licences, preprocessing and actual training roles. Raw media is under `datasets/raw/`; derived data is under `datasets/preprocessed/`. The historical `data/` path is a compatibility link.

To reproduce the original static baseline:

```sh
python scripts/download_aslyset.py
tar -xf data/raw/ASLYset.rar -C data/raw
python scripts/import_aslyset.py
python scripts/extract.py data/aslyset-manifest.csv
python -m asl_lab.train
```

Training compares SVM, Random Forest and KNN, selects on validation macro F1 and writes `models/classifier.joblib` and evaluation reports. It checks partition/group overlap, duplicate image hashes and missing classes. Preserve existing models and reports before rerunning training. Keep each signer in one partition, and keep inspected evaluation/demo clips out of future fitting.

## Repository layout and checks

- `app.py`, `templates/`, `static/`: Flask app and browser interface
- `asl_lab/`: landmark processing, classifiers and inference routes
- `config/`: showcase vocabulary and model-related configuration
- `scripts/`: acquisition, preprocessing, training and evaluation utilities
- `models/`: local trusted checkpoints, excluded from Git
- `datasets/`: dataset documentation and ignored research media/caches
- `reports/`: recorded evaluation evidence
- `testproj/`: selected demonstration clips and source records
- `notebooks/`: Colab showcase

The `tests/` folder was removed at the project owner’s request. See [the word ranking](ranking.md) for recorded per-word evaluation results; those results do not establish live recognition accuracy.

For context, see the [project report](docs/PROJECT_REPORT.md), [demo checklist](docs/DEMO_CHECKLIST.md), [evaluation protocol](docs/EVALUATION_MODE.md), [continuation notes](docs/ECHOGESTURE_START.md) and [`memory.md`](memory.md). [`PROJECT_HANDOFF.md`](PROJECT_HANDOFF.md) preserves earlier history; some milestones there are superseded by the current implementation.
