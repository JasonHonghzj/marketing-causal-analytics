# Hillstrom Email Marketing Experiment

Kevin Hillstrom released these data through the 2008 MineThatData E-Mail Analytics and Data Mining Challenge. Each row represents a customer. The raw CSV has no customer ID, and identical field values may belong to different customers. [Original experiment and field definitions](https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html)

## Data Dictionary

| Field | Definition |
| --- | --- |
| `segment` | Randomized assignment to the men's email, women's email, or no email |
| `conversion`, `visit` | Whether the customer purchased or visited the website within two weeks, 0 or 1 |
| `spend` | Spending per customer in the two-week window, in US dollars including zeros |
| `recency`, `history`, `history_segment` | Months since the last purchase, spending over the prior year, and the prior spending bracket |
| `channel`, `zip_code` | Purchase channel in the prior year and area category based on ZIP code |
| `mens`, `womens`, `newbie` | Whether the customer bought men's merchandise, bought women's merchandise, or was a new customer in the prior year |

The `mens` and `womens` flags record purchase history, and both can be 1. The source spells one `zip_code` category `Surburban`. The file has no send costs, contribution margins, unsubscribe data, or long-term outcomes. Hillstrom published the data for public analysis. No separate data license was located, so this project keeps the raw download locally and excludes it from Git.

## Download and Verify

The original download link timed out during initial setup. This project uses the Hillstrom CSV mirror listed by scikit-uplift, verified against the MD5 checksum it publishes. The analysis script checks the pinned SHA-256 on every run. [scikit-uplift download settings](https://github.com/maks-sh/scikit-uplift/blob/master/sklift/datasets/datasets.py#L503-L506)

```powershell
New-Item -ItemType Directory -Force -Path data/raw | Out-Null
curl.exe -fL "https://hillstorm1.s3.us-east-2.amazonaws.com/hillstorm_no_indices.csv.gz" -o data/raw/hillstrom.csv.gz
Get-FileHash -Algorithm SHA256 data/raw/hillstrom.csv.gz
```

The expected SHA-256 is `bab6578f60db5d792f1c2372c502f029152a5249cf5ea84390f3b7f885d7234f`. The compressed file contains the original 12 fields and is read directly by the analysis script.
