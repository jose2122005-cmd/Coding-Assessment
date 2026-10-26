# Exploratory Data Analysis & Cleaning

**Dataset:** `district_crashes.csv`, a TxDOT CRIS dataset for the Lubbock district.

The original CSV is not included in the repository because it is 77 MB. The results below were saved from a previous run. To run the script again, place `district_crashes.csv` in the project root.

## 1. Setup


```python
# The raw TxDOT file must be in the project root.
from pathlib import Path
import pandas as pd

CSV = Path("district_crashes.csv")
HEADER_LINES = 11   # non-data lines before the real header row 
pd.set_option("display.width", 120)
```

## 2. File structure
The task says the file has non-data lines at the top. Let's look at them.


```python
# Print the first lines (truncated) to see what has to be skipped.
# Line 12 is the real header row.
with open(CSV, encoding="utf-8-sig") as f:
    for i, line in enumerate(f, start=1):
        print(i, line.strip()[:110])
        if i == HEADER_LINES + 1:
            break
```

    1 "All crash data available using this tool represents reportable data collected from Texas Peace Officer's Cras
    2 
    3 "Query Result Counts:"
    4 "Your query returned a total of 24,261 Crashes containing 48,043 Units and 67,906 Persons"
    5 
    6 "Filters Applied to current Query:"
    7 "Crash Year Is In  2020 or 2021 or 2022 or 2023 or 2024 or 2025 or 2026"
    8 "TxDOT District Is Equal To LUBBOCK"
    9 "Crash Severity Is In A - SUSPECTED SERIOUS INJURY or B - SUSPECTED MINOR INJURY or K - FATAL INJURY or C - PO
    10 
    11 
    12 "Crash ID","Active School Zone Flag","Adjusted Average Daily Traffic Amount","Adjusted Percentage of Average D
    


```python
# Load everything as text (dtype=str) so pandas does not guess types silently
# (for example "0140" would become 140). utf-8-sig removes the invisible BOM.
raw = pd.read_csv(CSV, skiprows=HEADER_LINES, encoding="utf-8-sig", dtype=str, low_memory=False)
print("rows:", len(raw), "| columns:", raw.shape[1])
```

    rows: 67906 | columns: 94
    

## 3. What is one row? (grain)
`Crash ID` is repeated, so a row is probably not a crash. If rows are people, counting rows would inflate every metric.


```python
n_rows, n_crashes = len(raw), raw["Crash ID"].nunique()
print(f"rows: {n_rows:,} | distinct Crash IDs: {n_crashes:,} | avg rows per crash: {n_rows/n_crashes:.1f}")
print("max rows for a single crash:", raw.groupby("Crash ID").size().max())

# Impact of the grain: severity counted per row (wrong) vs per crash (right).
sev_code = lambda s: s.str.strip().str.upper().str[0]
crashes = raw.drop_duplicates("Crash ID")          # one row per crash
naive = sev_code(raw["Crash Severity"]).value_counts()
per_crash = sev_code(crashes["Crash Severity"]).value_counts()
print(pd.DataFrame({"naive (rows)": naive, "per crash": per_crash}).loc[["K", "A", "B", "C"]])
```

    rows: 67,906 | distinct Crash IDs: 24,261 | avg rows per crash: 2.8
    max rows for a single crash: 58
                    naive (rows)  per crash
    Crash Severity                         
    K                       1607        624
    A                       3842       1546
    B                      18793       7224
    C                      43664      14867
    

Is it safe to keep just one row per crash? Crash-level fields must not change between the rows of the same crash.


```python
crash_cols = ["Crash Severity", "Crash Date", "Crash Time", "County",
              "Road Class", "Contributing Factors", "Latitude", "Longitude"]
grp = raw.groupby("Crash ID")
for c in crash_cols:
    print(f"{c:22s} crashes with conflicting values: {(grp[c].nunique(dropna=False) > 1).sum()}")
```

    Crash Severity         crashes with conflicting values: 0
    Crash Date             crashes with conflicting values: 0
    Crash Time             crashes with conflicting values: 0
    County                 crashes with conflicting values: 0
    Road Class             crashes with conflicting values: 0
    Contributing Factors   crashes with conflicting values: 0
    Latitude               crashes with conflicting values: 0
    Longitude              crashes with conflicting values: 0
    

## 4. Relevant columns
The CSV contains 94 columns, so I focused on the fields needed for this project instead of reviewing every column.

| Column | Used for |
|---|---|
| `Crash ID` | Identifying duplicate records |
| `Crash Severity` | Counting crashes by severity and filtering results |
| `Crash Date`, `Crash Time` | Analyzing crash patterns by year, month, weekday, and hour |
| `County`, `Road Class` | Filtering crashes |
| `Contributing Factors` | Finding the most common contributing factors |
| `Latitude`, `Longitude` | Displaying crash locations on the map |

**Columns left out:** `Crash Year` and `Hour of Day` were not needed because those values can be obtained from `Crash Date` and `Crash Time`. Person and vehicle columns were excluded because this project looks at crashes as a whole, rather than individual people or vehicles. Roadway geometry columns were also left out because they are not needed for the current analysis.

I used `Contributing Factors` instead of `Contributing Factor 1/2/3` because those fields are recorded per vehicle and are often empty. The combined field is more useful for this project because it lets me count contributing factors for each crash.


```python
for c in ["Contributing Factor 1", "Contributing Factor 2", "Contributing Factor 3"]:
    n = (raw[c].str.strip().str.upper() == "NO DATA").sum()
    print(f"{c}: 'No Data' in {n:,} of {len(raw):,} rows")
```

    Contributing Factor 1: 'No Data' in 32,361 of 67,906 rows
    Contributing Factor 2: 'No Data' in 62,276 of 67,906 rows
    Contributing Factor 3: 'No Data' in 67,228 of 67,906 rows
    

## 5. Data quality checks on the relevant columns (crash level)


```python
# Nulls and placeholder strings. The data uses text placeholders, not real NaN.
rows = []
for c in crash_cols:
    s = crashes[c]
    up = s.str.strip().str.upper()
    rows.append({"column": c, "NaN": int(s.isna().sum()), "'No Data'": int((up == "NO DATA").sum()),
                 "'NONE'": int((up == "NONE").sum()), "distinct": s.nunique()})
print(pd.DataFrame(rows).to_string(index=False))
```

                  column  NaN  'No Data'  'NONE'  distinct
          Crash Severity    0          0       0         4
              Crash Date    0          0       0      2484
              Crash Time    0          0       0      1435
                  County    0          0       0        17
              Road Class    0          0       0         7
    Contributing Factors    0          0     104      1301
                Latitude    0        849       0     14729
               Longitude    0        849       0     14548
    


```python
# There is inconsistent casing, test the categorical columns.
for c in ["Crash Severity", "County", "Road Class"]:
    s = crashes[c].dropna()
    print(f"{c:15s} distinct raw: {s.nunique():3d} | after trim+upper: {s.str.strip().str.upper().nunique():3d}")
print()
print(crashes["Crash Severity"].value_counts())
print()
print(crashes["Road Class"].value_counts())
print()
print("counties:", sorted(crashes["County"].unique()))
```

    Crash Severity  distinct raw:   4 | after trim+upper:   4
    County          distinct raw:  17 | after trim+upper:  17
    Road Class      distinct raw:   7 | after trim+upper:   7
    
    Crash Severity
    C - POSSIBLE INJURY             14867
    B - SUSPECTED MINOR INJURY       7224
    A - SUSPECTED SERIOUS INJURY     1546
    K - FATAL INJURY                  624
    Name: count, dtype: int64
    
    Road Class
    CITY STREET            10677
    US & STATE HIGHWAYS     9296
    FARM TO MARKET          1406
    INTERSTATE              1358
    NON TRAFFICWAY           782
    COUNTY ROAD              721
    OTHER ROADS               21
    Name: count, dtype: int64
    
    counties: ['BAILEY', 'CASTRO', 'COCHRAN', 'CROSBY', 'DAWSON', 'FLOYD', 'GAINES', 'GARZA', 'HALE', 'HOCKLEY', 'LAMB', 'LUBBOCK', 'LYNN', 'PARMER', 'SWISHER', 'TERRY', 'YOAKUM']
    

### Contributing Factors
Looking at the distinct values suggests the column holds several factors joined together.


```python
f = crashes["Contributing Factors"].dropna()
parts = f.str.split(";").explode()
n_parts = f.str.count(";") + 1

print("distinct raw strings:", f.nunique(),
      "| distinct individual factors (trim+upper):", parts.str.strip().str.upper().nunique())
print(f"crashes with 2+ factors: {(n_parts > 1).sum():,} ({(n_parts > 1).mean():.1%}) | max factors in one crash: {n_parts.max()}")
print("factor entries with a leading space after ';':", int(parts.str.startswith(" ").sum()))
print("example:", f[n_parts > 1].iloc[0])
print()
print("Counting the raw column (wrong: ranks combinations):")
print(f.value_counts().head(3))

other = f.str.upper().str.contains(r"OTHER \(EXPLAIN IN NARRATIVE\)").sum()
print(f"\ncrashes with 'OTHER (EXPLAIN IN NARRATIVE)': {other:,} ({other/len(crashes):.1%})")
print("crashes with factor == 'NONE':", int((f.str.strip().str.upper() == "NONE").sum()))
```

    distinct raw strings: 1301 | distinct individual factors (trim+upper): 74
    crashes with 2+ factors: 6,128 (25.3%) | max factors in one crash: 9
    factor entries with a leading space after ';': 3750
    example: FAILED TO CONTROL SPEED;CELL/MOBILE DEVICE USE - TEXTING
    
    Counting the raw column (wrong: ranks combinations):
    Contributing Factors
    FAILED TO CONTROL SPEED                        4136
    FAILED TO YIELD RIGHT OF WAY - STOP SIGN       2020
    FAILED TO YIELD RIGHT OF WAY - TURNING LEFT    1987
    Name: count, dtype: int64
    
    crashes with 'OTHER (EXPLAIN IN NARRATIVE)': 1,604 (6.6%)
    crashes with factor == 'NONE': 104
    

### Dates, times and coordinates


```python
d = pd.to_datetime(crashes["Crash Date"], errors="coerce")
print("unparseable dates:", int(d.isna().sum()), "| range:", d.min().date(), "to", d.max().date())
print("crashes per year:", d.dt.year.value_counts().sort_index().to_dict())

t = pd.to_numeric(crashes["Crash Time"], errors="coerce")      # format HHMM, zero padded
print("time: non-numeric:", int(t.isna().sum()), "| outside 0-2359:", int((~t.between(0, 2359)).sum()),
      "| string lengths:", crashes["Crash Time"].str.len().unique().tolist())

lat = pd.to_numeric(crashes["Latitude"], errors="coerce")
lon = pd.to_numeric(crashes["Longitude"], errors="coerce")
valid = lat.between(25, 37) & lon.between(-107, -93)             # rough Texas bounding box
print("coordinates: missing ('No Data'):", int(lat.isna().sum()),
      "| present but zero/outside Texas:", int((lat.notna() & ~valid).sum()),
      "| valid:", int(valid.sum()))
```

    unparseable dates: 0 | range: 2020-01-01 to 2026-10-20
    crashes per year: {2020: 3351, 2021: 3971, 2022: 3716, 2023: 3673, 2024: 3452, 2025: 3444, 2026: 2654}
    time: non-numeric: 0 | outside 0-2359: 0 | string lengths: [4]
    coordinates: missing ('No Data'): 849 | present but zero/outside Texas: 0 | valid: 23412
    

## 6. Cleaning decisions

| Finding | What I did | Reason |
|---|---|---|
| 11 extra lines at the top and a BOM | Used `skiprows=11` and `encoding="utf-8-sig"` | So pandas reads the file correctly |
| Multiple rows for the same crash | Kept one row per `Crash ID`, using the first record | The analysis counts crashes, not people. The crash-level fields were consistent across duplicate rows (see Section 3) |
| Missing values such as `No Data`, `NONE`, and blanks | Trimmed spaces, converted text to uppercase, and treated these values as missing | Keeps missing values consistent |
| Severity labels contain both a letter and a description | Kept the first letter and accepted only K, A, B, or C | Makes severity easier to filter and count |
| A crash can have multiple contributing factors | Split the values at `;` and counted each factor once per crash | Counts individual factors instead of whole combinations |
| Factors such as `OTHER (EXPLAIN IN NARRATIVE)` and `NONE` | Left them out of the rankings | They do not identify a specific contributing factor |
| Crash times use the `HHMM` format | Extracted the hour by dividing by 100 and taking the integer part; accepted values from 0 to 2359 | Needed to group crashes by hour |
| Missing or invalid coordinates | Set the coordinates to missing but kept the crash in the dataset | A missing location should not affect the crash counts |
| Data from 2026 is incomplete | Kept the available records and noted that the year is partial | The dataset includes crashes through October 2026 |

Some checks, such as handling different capitalization, zero coordinates, and dates that cannot be parsed, did not affect any records in this file. I kept those checks in place in case a future TxDOT export contains those issues.

## 7. Apply the cleaning pipeline and validate


```python
# Run the rules implemented in processing.py.
import processing as p
clean = p.load_crashes()

with open(CSV, encoding="utf-8-sig") as fh:
    header_text = "".join(next(fh) for _ in range(HEADER_LINES))
print("file header mentions 24,261 crashes:", "24,261" in header_text)

print("clean crashes:", len(clean))
print("severity:", p.severity_counts(clean))
print("top factors:")
for item in p.top_factors(clean):
    print("  ", item)
print("by year:", p.temporal_patterns(clean)["by_year"])
```

    file header mentions 24,261 crashes: True
    clean crashes: 24261
    severity: {'K': 624, 'A': 1546, 'B': 7224, 'C': 14867}
    top factors:
       {'factor': 'FAILED TO CONTROL SPEED', 'crashes': 5559, 'pct_of_crashes': 22.9}
       {'factor': 'FAILED TO YIELD RIGHT OF WAY - STOP SIGN', 'crashes': 2428, 'pct_of_crashes': 10.0}
       {'factor': 'FAILED TO YIELD RIGHT OF WAY - TURNING LEFT', 'crashes': 2346, 'pct_of_crashes': 9.7}
       {'factor': 'FAILED TO DRIVE IN SINGLE LANE', 'crashes': 2334, 'pct_of_crashes': 9.6}
       {'factor': 'UNSAFE SPEED', 'crashes': 2034, 'pct_of_crashes': 8.4}
    by year: {'2020': 3351, '2021': 3971, '2022': 3716, '2023': 3673, '2024': 3452, '2025': 3444, '2026': 2654}
    


```python
# Sanity checks (the notebook fails loudly if any rule breaks).
assert len(clean) == raw["Crash ID"].nunique()
assert sum(p.severity_counts(clean).values()) == len(clean)
print("all checks passed")
```

    all checks passed
    

## 8. Limitations
- All counts are based on crashes, not the number of people injured.

- About 3.5% of crashes have missing coordinates and cannot be shown on the map, but they are still included in the other results.

- The 2026 data only covers part of the year, so comparisons with previous full years should be made carefully.

- Contributing factors are reported by officers. The rankings show how often each factor is reported, not whether it directly caused a crash.
