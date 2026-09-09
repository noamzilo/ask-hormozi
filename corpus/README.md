# MoreMozi corpus

This snapshot contains source material for 2,610 videos from the
[MoreMozi YouTube channel](https://www.youtube.com/@MoreMozi):

- `episodes/`: one catalog page per video
- `metadata/`: source metadata and caption provenance
- `transcripts/`: one readable transcript per video
- `segments/`: 13,946 timestamped passages used by QMD
- `catalog.json`: the complete video inventory
- `caption-coverage.json`: English-caption coverage audit
- `transcript-manifest.json`: transcript build results

Every segment links to its source video at the relevant timestamp. Captions may
be automatically generated and can contain transcription errors, so important
details should be checked against the linked video.

The repository contains no video or audio binaries. See [`NOTICE.md`](NOTICE.md)
for the corpus copyright and license boundary.
