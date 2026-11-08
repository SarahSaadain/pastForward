import sys

def combine_endogenous_files(individual_files, combined_file_path):
    """
    Combines individual endogenous read files (which now include the 
    'Individual' column) into a single summary file.
    
    Args:
        individual_files (list): List of paths to individual endogenous read CSVs.
        combined_file_path (str): Path to the final combined CSV file.
    """
    if not individual_files:
        # Using sys.stderr for error messages, as recommended for Snakemake scripts
        print("Error: No individual endogenous read files found to combine.", file=sys.stderr)
        # Exiting with a non-zero status is often preferred in Snakemake if inputs are missing
        sys.exit(1) 

    # Sorting files ensures predictable output order
    individual_files = sorted(individual_files)

    with open(combined_file_path, "w") as combined_file:
        # **UPDATED HEADER:** Must include the 'Individual' column
        combined_file.write("filename,individual,mapped_reads,total_reads,proportion\n")

        for f in individual_files:
            try:
                with open(f, "r") as f_in:
                    # The first line is the header: "Filename,Individual,MappedReads,TotalReads,Proportion"
                    _ = f_in.readline()  
                    
                    # The second line is the data line we want to include
                    data_line = f_in.readline().strip()
                    
                    if data_line:
                        combined_file.write(data_line + "\n")
                    else:
                        print(f"Warning: Data line missing in file: {f}", file=sys.stderr)

            except FileNotFoundError:
                print(f"Error: Individual file not found: {f}", file=sys.stderr)
            except Exception as e:
                print(f"Error processing file {f}: {e}", file=sys.stderr)


    print(f"Successfully created combined endogenous reads file: {combined_file_path}")


if __name__ == "__main__":
    # Snakemake passes input files as a list/dict and output as a list.
    combine_endogenous_files(
        # Assuming snakemake.input is an iterable list of files
        snakemake.input,   
        snakemake.output[0]
    )