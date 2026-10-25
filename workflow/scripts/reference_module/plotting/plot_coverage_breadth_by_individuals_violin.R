#!/usr/bin/env Rscript

suppressPackageStartupMessages({
library(ggplot2)
library(dplyr)
library(readr)
library(stringr)
})


species <- snakemake@params[["species"]]
input_file <- snakemake@input[[1]]
output_file <- snakemake@output[[1]]

df <- read_csv(input_file)
if (nrow(df) == 0) stop("Input file is empty.")

# Extract individual
df <- df %>%
  mutate(individual = str_split(Filename, "_", simplify = TRUE)[,1])

# Violin plot function
violin_plot <- ggplot(df, aes(x = factor(individual), y = percent_covered)) +
  geom_violin(scale = "width", trim = TRUE, fill = "grey30") +
  theme_bw() +
  ylab("Breadth Coverage (per scaffold) [%]") +
  xlab("Individual") +
  ggtitle(paste0("Distribution of Coverage Breadth per Scaffold: ", species)) +
  theme(axis.text.x = element_text(size = 14, angle = 45, vjust = 1, hjust = 1),
        axis.text.y = element_text(size = 14),
        axis.title.x = element_text(size = 16, face = "bold"),
        axis.title.y = element_text(size = 16, face = "bold"),
        plot.title = element_text(size = 18, face = "bold", hjust = 0.5),
        panel.grid.major = element_blank(),
        panel.grid.minor = element_blank(),
        panel.background = element_rect(fill = "white", colour = "black"))

ggsave(output_file, plot = violin_plot, width = 12, height = 6, dpi = 300)
