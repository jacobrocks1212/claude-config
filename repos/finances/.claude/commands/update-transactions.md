---
description: Updates transactions.csv with new entries from a downloaded CSV file
args: [file_path]
---

You are tasked with updating the master transactions file with new entries from a downloaded CSV.

The user will provide a file path to a newly downloaded transactions CSV file: {{file_path}}

Follow these steps:

1. Read the master transactions file at: C:\Users\JacobMadsen\source\repos\finances\transactions.csv
2. Read the incoming transactions file at: {{file_path}}
3. Compare the two files to identify new transactions that exist in the incoming file but not in the master file
   - A transaction is considered "new" if it doesn't have an exact match (same Date, Account, Description, Category, Tags, and Amount) in the master file
   - Be careful with the comparison - some transactions may appear multiple times legitimately (e.g., recurring charges)
4. If new transactions are found:
   - Append them to the master transactions.csv file
   - Preserve the CSV format exactly
   - Report how many new transactions were added
5. If no new transactions are found, report that the master file is already up to date

IMPORTANT:
- Preserve the header row format
- Maintain proper CSV formatting with quotes where needed
- Sort is not required - just append new entries
- Report a summary of what was added (date range, count, categories)
