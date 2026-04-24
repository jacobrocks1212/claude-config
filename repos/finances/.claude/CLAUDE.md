# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Personal finance tracking and analysis system. The master data file is `transactions.csv`, exported from Empower Personal Dashboard.

## Data Schema

**transactions.csv** contains 6 columns:
- `Date`: Transaction date (YYYY-MM-DD format)
- `Account`: Bank account description (e.g., "Credit Card ( ) - Ending in 4770")
- `Description`: Merchant/transaction description
- `Category`: Spending category (Restaurants, Groceries, Travel, Paychecks/Salary, etc.)
- `Tags`: Optional tags (currently unused)
- `Amount`: Transaction amount (negative for expenses, positive for income)

## Key Workflows

### Updating Transactions

Use the `/update-transactions` command to merge new transaction exports:

```
/update-transactions "C:\Users\JacobMadsen\Downloads\new-export.csv"
```

**How it works:**
- Compares incoming CSV against master `transactions.csv`
- Identifies new transactions (exact match on all 6 fields)
- Appends new entries while preserving format
- Legitimate duplicates (recurring charges) are expected and handled correctly

**Important:** This is append-only. Never modify or delete existing transactions to maintain audit trail.

## Architecture Notes

- **Single Source of Truth**: `transactions.csv` is the master ledger
- **Data Portability**: CSV format allows easy import into analysis tools, Excel, databases
- **No Backend Yet**: Analysis and reporting features are planned but not implemented
- **AI-Assisted**: Leverage Claude for data manipulation and future analysis features

## Future Development Considerations

When building analysis features:
- Respect the append-only nature of transactions.csv
- Consider date ranges carefully (data spans 2024-2025)
- Account for legitimate duplicate transactions (recurring charges, subscriptions)
- Negative amounts = expenses, positive = income/refunds
- Some transactions have empty Tags field
