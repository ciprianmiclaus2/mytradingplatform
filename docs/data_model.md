# Data Model

All persisted data lives under `DATA_DIR`. See the [README](../README.md#data-directory) for the folder layout and [architecture.md](architecture.md#persistence) for how files are written.

## Conventions

- **Format:** Parquet with zstd compression, one declared `DatasetSchema` per dataset.
- **File metadata:**
  - `mtp_dataset` holds the dataset name and `mtp_schema_version` its integer version. Both are checked on every read.
  - Keys starting with `x_` carry extra information, e.g. `x_source_fingerprint` for derived data.
- **Types:**
  - Money and quantities: `decimal128`. The precision will be fixed per dataset in Phases 4–5.
  - Timestamps: `timestamp[us, tz=UTC]`.
  - Identifiers: strings.
- **Data schema version:** `metadata/schema_version.json` holds the version of the data directory as a whole. It is currently `1`.

## Datasets

| Dataset | Path | Version | Introduced |
|---|---|---|---|
| _(none yet)_ | | | Entity schemas are added in Phases 3–7 |
