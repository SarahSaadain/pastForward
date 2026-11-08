import pandas as pd

feature_libraries = snakemake.params.feature_libraries
frames = []
for feature_library, tsv_file in zip(feature_libraries, snakemake.input):
    df = pd.read_csv(tsv_file, sep="\t")
    df.insert(0, "feature_library", feature_library)
    frames.append(df)
pd.concat(frames, ignore_index=True).to_csv(
    snakemake.output.combined, sep="\t", index=False
)
