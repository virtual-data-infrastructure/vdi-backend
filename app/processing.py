import csv
import hashlib
import os
import re

def match_filters(string, filters):
    # assume string contains x whitespace-separated columns
    # filter: col0@@@filter0@@@col1@@@filter1@@@...(e.g., first, filter 0 is
    #         applied to column 0, then filter 1 to col 1, ...)
    #         col0, col1 are values provided via the API call (e.g., from the
    #         frontend; actual col0 values are in the range [0,num_cols_in_row])
    # examples:
    #  - single filter: "12@@@^open$@@@13@@@^/cvmfs/software\.eessi\.io"
    #  - two filters: [ "12@@@^open$@@@13@@@^/cvmfs/software\.eessi\.io",
    #                   "12@@@^openat$@@@14@@@^/cvmfs/software\.eessi\.io" ]
    #    to illustrate that the pathname is stored in a different column for
    #    different calls
    row = re.split(r'\s+', string.strip())
    
    for filter_items in filters:
        # construct arrays for cols and regexs
        filters_splitted = filter_items.split('@@@')
        cols = filters_splitted[::2]
        regexs = filters_splitted[1::2]
        # print(f"filter line '{filter_items}' contains {len(cols)} columns and {len(regexs)} regexs")
        # iterate over [0, len(regexs)] using regexs because there could be a column without a regex
        # when all regex in a filter match we return True (matches == len(regexs))
        # when or differently formulated if any regex
        #   doesn't match we return False otherwise True
        matches = 0
        for ridx in range(len(regexs)):
            # print(f"try to match column {cols[ridx]} with regex '{regexs[ridx]}'")
            if re.search(regexs[ridx], row[int(cols[ridx])]):
                matches = matches + 1
        if (matches == len(regexs)):
            return True
    # none of the filters matched
    return False

# Function to process the file and filter out irrelevant information
def process_file(file_path, filters):
    processed_lines = []

    # Read the original file and filter lines
    with open(file_path, 'r', newline='', encoding='utf-8') as file:
        for line in file:
            if not match_filters(line, filters):
                processed_lines.append(line)

    # Define the path for the processed file
    processed_dir = os.path.dirname(file_path.replace('raw_logs', 'processed_logs'))
    if not os.path.exists(processed_dir):
        os.makedirs(processed_dir)
    processed_path = os.path.join(processed_dir, os.path.basename(file_path))
    
    # Save the filtered content to the new file
    with open(processed_path, 'w', newline='', encoding='utf-8') as processed_file:
        for line in processed_lines:
            processed_file.write(line)
    
    return processed_path

# Function to calculate the checksum of a file
def calculate_checksum(file_path):
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as file:
        buf = file.read()
        hasher.update(buf)
    return hasher.hexdigest()
