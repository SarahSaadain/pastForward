#!/usr/bin/env Rscript

suppressPackageStartupMessages({
library(ggplot2)
library(dplyr)
library(readr)
})

# Access Snakemake variables
input_file <- snakemake@input[[1]]
output_file <- snakemake@output[[1]]
species <- snakemake@params[["species"]]

df <- read_csv(input_file, show_col_types = FALSE)
if (nrow(df) == 0) stop("Input file is empty.")

dir.create(dirname(output_file), recursive = TRUE, showWarnings = FALSE)

df <- df %>%
  mutate(
    divergence_rate = as.numeric(divergence_rate),
    status = as.character(status)
  )

# The threshold is cohort-wide, so every scored individual carries the same value.
# It is empty when no cohort score could be computed.
threshold <- suppressWarnings(as.numeric(df$outlier_threshold_rate))
threshold <- threshold[!is.na(threshold)]
threshold <- if (length(threshold) > 0) threshold[1] else NA_real_

status_colours <- c(
  "ok"                   = "grey30",
  "outlier"              = "firebrick",
  "insufficient_data"    = "grey70",
  "insufficient_cohort"  = "grey50"
)

bar_plot <- ggplot(df, aes(x = reorder(individual, -divergence_rate),
                           y = divergence_rate,
                           fill = status)) +
  geom_bar(stat = "identity") +
  scale_fill_manual(name = NULL, values = status_colours, drop = FALSE) +
  theme_bw() +
  ylab("Divergence from reference [mismatches / base]") +
  xlab("Individual") +
  ggtitle(paste0("SNP Divergence per Individual: ", species)) +
  theme(axis.text.x = element_text(size = 12, angle = 45, hjust = 1),
        axis.text.y = element_text(size = 12),
        axis.title.x = element_text(size = 12, face = "bold"),
        axis.title.y = element_text(size = 12, face = "bold"),
        plot.title = element_text(size = 14, hjust = 0.5),
        legend.position = "bottom")

if (!is.na(threshold)) {
  bar_plot <- bar_plot +
    geom_hline(yintercept = threshold, linetype = "dashed", colour = "firebrick") +
    annotate("text", x = Inf, y = threshold, label = "outlier threshold",
             hjust = 1.05, vjust = -0.5, size = 3.5, colour = "firebrick")
}

ggsave(output_file, plot = bar_plot, width = 12, height = 6, dpi = 300)
