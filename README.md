# Ask Hormozi

Ask Hormozi ships a Markdown corpus for Alex Hormozi's
[MoreMozi](https://www.youtube.com/@MoreMozi) channel and gives AI coding
agents a skill for answering questions with video-level, timestamped sources.
Installation builds only the local QMD index; it does not download video,
audio, captions, or transcripts.

The current corpus snapshot contains 2,610 videos, 2,611 readable transcripts,
and 13,946 timestamped segments.

## What it does

- Ships a catalog of every MoreMozi video with its YouTube URL.
- Ships a readable Markdown transcript for each video.
- Ships 90-second Markdown segments with video metadata and timestamps.
- Registers those segments as a dedicated
  [QMD](https://github.com/qntx-labs/qmd) collection.
- Installs an `ask-hormozi` skill for Codex and Claude Code.
- Returns retrieved context with clickable YouTube timestamps so the agent can
  answer without inventing attribution.
- Syncs incrementally: reruns skip videos already transcribed.

## Install as an HQ pack

Install from the HQ marketplace:

```bash
hq install marketplace:ask-hormozi
bash core/scripts/hq-ask-hormozi setup
```

Or install the full source package directly from GitHub:

```bash
hq install https://github.com/poseljacob/ask-hormozi
bash core/scripts/hq-ask-hormozi setup
```

The second command prepares the Markdown already bundled in the pack and creates
the local QMD index. Marketplace installs unpack a compressed copy of the same
timestamped Markdown locally to stay within the marketplace artifact limit.
Neither path downloads video, audio, captions, or transcripts during setup.

Start a fresh Codex or Claude Code session from HQ, invoke `/ask-hormozi`, and
ask a normal question:

> What does Hormozi recommend for improving an offer?

The skill checks the index on each use and creates it automatically when it is
missing. Direct HQ runtime commands are also available:

```bash
bash core/scripts/hq-ask-hormozi search \
  "How should I price and position my offer?"
bash core/scripts/hq-ask-hormozi doctor
bash core/scripts/hq-ask-hormozi refresh
```

## Standalone install

Requirements: macOS or Linux, Python 3.10+, and `curl`. The setup script
installs the package in an isolated virtual environment and installs QMD when it
is not already available. QMD currently publishes no prebuilt release binaries,
so setup falls back to building it from source, which additionally needs a Rust
toolchain (`rustup`) and `pkg-config`. This project targets the QMD 0.5.x CLI.

```bash
git clone https://github.com/poseljacob/ask-hormozi.git
cd ask-hormozi
./setup.sh
```

Ensure `~/.local/bin` is on your `PATH`, then search directly:

```bash
ask-hormozi search "How should I price and position my offer?"
```

Or invoke the installed `/ask-hormozi` skill in Codex or Claude Code and ask a
normal question:

> What does Hormozi recommend for improving an offer?

## HQ pack contents

The root `package.yaml` declares two contributions:

- `skills/ask-hormozi` — the portable Codex/Claude retrieval skill.
- `scripts/hq-ask-hormozi` — the HQ runtime that uses the bundled Python module
  and corpus without a separate package install.

HQ wires those contributions to `.claude/skills/ask-hormozi` and
`core/scripts/hq-ask-hormozi`. The corpus remains inside
`core/packages/hq-pack-ask-hormozi/corpus`.

## Commands

```text
ask-hormozi sync [--limit N] [--jobs N] [--force]
ask-hormozi catalog [--output-dir corpus]
ask-hormozi audit-captions [--jobs N]
ask-hormozi index
ask-hormozi configure --data-dir PATH
ask-hormozi search "question" [--limit N] [--format markdown|json]
ask-hormozi doctor
```

```text
corpus/
├── catalog.json
├── caption-coverage.json
├── transcript-manifest.json
├── episodes/
│   └── VIDEO_ID.md
├── metadata/
│   └── VIDEO_ID.json
├── transcripts/
│   └── VIDEO_ID.md
└── segments/
    └── VIDEO_ID/
        ├── 000000.md
        ├── 000090.md
        └── ...
```

`setup.sh` configures the CLI to use the checked-out `corpus/` directory.
`index` owns the QMD collection named `ask-hormozi`; it replaces that collection
registration without running a global QMD update.

## Refreshing

Update the HQ pack and re-index:

```bash
bash core/scripts/hq-ask-hormozi refresh
```

For a standalone checkout, pull the latest prebuilt corpus and re-index:

```bash
git pull
./setup.sh
```

End-user installation never downloads from YouTube. The maintainer-only
`ask-hormozi sync` command rebuilds corpus source files for an authorized
release.

Maintainers can refresh non-transcript release metadata independently:

```bash
ask-hormozi catalog --output-dir corpus
ask-hormozi audit-captions --output-file corpus/caption-coverage.json
```

The caption audit resumes from its existing output. If YouTube throttles a
large pass, retry only failed videos conservatively:

```bash
ask-hormozi audit-captions --jobs 1 --delay 5
```

The maintainer commands use yt-dlp's unauthenticated `web_embedded` YouTube
client, falling back to its `tv` client when a video disables embedding. They
do not read browser cookies or require a YouTube account.

## Retrieval and citations

The skill runs QMD BM25 search through the package CLI. Each result is enriched
from the matching local segment:

```json
{
  "title": "Video title",
  "start_seconds": 540,
  "context": "Retrieved transcript passage...",
  "citation_url": "https://www.youtube.com/watch?v=VIDEO_ID&t=540s",
  "transcript_source": "automatic_captions"
}
```

The skill must paraphrase by default, distinguish Hormozi's statements from its
own synthesis, and cite material claims as:

```markdown
[Video title — 09:00](https://www.youtube.com/watch?v=VIDEO_ID&t=540s)
```

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
```

Bundled-corpus smoke test:

```bash
.venv/bin/ask-hormozi configure --data-dir "$PWD/corpus"
.venv/bin/ask-hormozi index --data-dir "$PWD/corpus"
.venv/bin/ask-hormozi search "pricing value equation irresistible offer"
```

## Content and affiliation

This project is not affiliated with or endorsed by Alex Hormozi,
Acquisition.com, MoreMozi, or YouTube.

The transcript corpus is redistributed with permission. Copyright in the
video-derived corpus remains with its respective owner and is not relicensed
under the repository's or package manifest's MIT code license. See
[`corpus/NOTICE.md`](corpus/NOTICE.md). No video or audio binaries are included.
Verify important details against the linked video because captions can contain
errors.
