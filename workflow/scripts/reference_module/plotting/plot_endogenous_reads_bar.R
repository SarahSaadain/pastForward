#!/usr/bin/env Rscript

suppressPackageStartupMessages({
library(dplyr)
library(ggplot2)
library(tidyr)
library(ggpattern)
})


plot_endogenous_reads_bar <- function(source_file, output_file) {
  
  dir.create(dirname(output_file), recursive = TRUE, showWarnings = FALSE)
  
  df <- read.table(source_file, sep = "\t", header = TRUE) %>%
    mutate(
      individual = sub("_.*", "", individual),
      percent_endogenous = (mapped_endogenous_reads / mapped_input_reads) * 100,
      percent_after_dup_removal = (endogenous_duplicates_removed / mapped_input_reads) * 100,
      percent_duplicates_removed = percent_endogenous - percent_after_dup_removal
    ) %>%
    distinct(individual, .keep_all = TRUE)
  
  df_long <- df %>%
    select(individual, percent_after_dup_removal, percent_duplicates_removed) %>%
    pivot_longer(
      cols = -individual,
      names_to = "category",
      values_to = "percent"
    ) %>%
    mutate(
      category = factor(category,
                        levels = c("percent_after_dup_removal",
                                   "percent_duplicates_removed"))
    )
  
  p <- ggplot(df_long, aes(x = individual, y = percent, pattern = category, fill = category)) +
    geom_bar_pattern(stat = "identity", position = position_stack(reverse = TRUE),
                     colour = "black",
                     pattern_fill = "grey30",
                     pattern_angle = 45,
                     pattern_density = 0.3,
                     pattern_spacing = 0.03) +
scale_fill_manual(
  name = NULL,
  values = c("percent_after_dup_removal" = "grey30",
             "percent_duplicates_removed" = "white"),
  labels = c("percent_after_dup_removal" = "Final Endogenous",
             "percent_duplicates_removed" = "Duplicates Removed")
) +
scale_pattern_manual(
  name = NULL,
  values = c("percent_after_dup_removal" = "none",
             "percent_duplicates_removed" = "none"),
  labels = c("percent_after_dup_removal" = "Final Endogenous",
             "percent_duplicates_removed" = "Duplicates Removed")
) +
    labs(x = "Individual", y = "Endogenous Reads [%]", title = "Endogenous Reads and Duplicates") +
    theme_bw() +
    theme(axis.text.x = element_text(size = 12, angle = 45, vjust = 1, hjust = 1),
          axis.text.y = element_text(size = 12),
          axis.title.x = element_text(size = 14, face = "bold"),
          axis.title.y = element_text(size = 14, face = "bold"),
          plot.title = element_text(size = 14, hjust = 0.5),
          legend.position = "bottom",
          panel.grid.major = element_blank(),
          panel.grid.minor = element_blank(),
          panel.background = element_rect(fill = "white", colour = "black"))
  
  ggsave(output_file, plot = p, width = 8, height = 6, dpi = 300)
}

if (exists("snakemake")) {
  source_file <- snakemake@input[[1]]
  output_file <- snakemake@output[[1]]
  plot_endogenous_reads_bar(source_file, output_file)
}