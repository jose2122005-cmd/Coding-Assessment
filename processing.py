from pathlib import Path

import pandas as pd


CSV_PATH = Path(__file__).parent / "district_crashes.csv"
CLEAN_PATH = Path(__file__).parent / "data" / "crashes_clean.csv.gz"

# Skip the first 11 lines of the CSV
HEADER_LINES_TO_SKIP = 11

# Columns needed for the analysis
USE_COLS = [
    "Crash ID",
    "Crash Severity",
    "Crash Date",
    "Crash Time",
    "County",
    "Road Class",
    "Contributing Factors",
    "Latitude",
    "Longitude",
]

# Values that should be treated as missing
MISSING_TOKENS = {"", "NO DATA", "NAN", "NONE", "NULL", "N/A", "UNKNOWN"}

# Ignore this factor when counting causes
EXCLUDED_FACTORS = {"OTHER (EXPLAIN IN NARRATIVE)"}

SEVERITY_ORDER = ["K", "A", "B", "C"]
SEVERITY_LABELS = {
    "K": "Fatal injury",
    "A": "Suspected serious injury",
    "B": "Suspected minor injury",
    "C": "Possible injury",
}


def _clean_text(series: pd.Series) -> pd.Series:
    # Clean up text and handle missing values
    s = series.astype("string").str.strip().str.upper()
    return s.mask(s.isin(MISSING_TOKENS))


def load_crashes(path: Path = CSV_PATH) -> pd.DataFrame:
    # Load the CSV and clean the crash data
    df = pd.read_csv(
        path,
        skiprows=HEADER_LINES_TO_SKIP,
        encoding="utf-8-sig",
        usecols=USE_COLS,
        dtype=str,
    )

    # Keep only one row per crash
    df = df.drop_duplicates(subset="Crash ID", keep="first").copy()

    for col in ["Crash Severity", "County", "Road Class", "Contributing Factors"]:
        df[col] = _clean_text(df[col])

    # Extract the severity letter
    df["severity"] = df["Crash Severity"].str[0]
    df.loc[~df["severity"].isin(SEVERITY_ORDER), "severity"] = pd.NA

    # Convert the crash date and extract its parts
    df["date"] = pd.to_datetime(df["Crash Date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["weekday"] = df["date"].dt.day_name()

    # Get the hour from the crash time
    time_num = pd.to_numeric(df["Crash Time"], errors="coerce")
    df["hour"] = (time_num // 100).where(time_num.between(0, 2359))

    # Convert coordinates to numeric values
    for col in ["Latitude", "Longitude"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Remove coordinates that are zero or outside the expected range
    bad_coords = (
        (df["Latitude"] == 0)
        | (df["Longitude"] == 0)
        | ~df["Latitude"].between(25, 37)
        | ~df["Longitude"].between(-107, -93)
    )
    df.loc[bad_coords, ["Latitude", "Longitude"]] = pd.NA

    return df.rename(
        columns={
            "Crash ID": "crash_id",
            "County": "county",
            "Road Class": "road_class",
            "Contributing Factors": "factors_raw",
            "Latitude": "lat",
            "Longitude": "lon",
        }
    ).drop(columns=["Crash Severity", "Crash Date", "Crash Time"])


def save_clean(df: pd.DataFrame, path: Path = CLEAN_PATH) -> None:
    # Save the cleaned data to a compressed CSV
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, compression="gzip")


def get_data(path: Path = CLEAN_PATH) -> pd.DataFrame:
    # Load the cleaned data
    if not path.exists():
        raise FileNotFoundError(
            f"Clean data file not found: {path}. Run 'py prepare_data.py' first."
        )

    return pd.read_csv(
        path,
        compression="gzip",
        parse_dates=["date"],
        dtype={"crash_id": "string"},
    )


def apply_filters(
    df: pd.DataFrame,
    county: str | None = None,
    year: int | None = None,
    severity: str | None = None,
    road_class: str | None = None,
) -> pd.DataFrame:
    # Filter crashes based on the selected values
    if county:
        df = df[df["county"] == county.strip().upper()]
    if year:
        df = df[df["year"] == int(year)]
    if severity:
        df = df[df["severity"] == severity.strip().upper()]
    if road_class:
        df = df[df["road_class"] == road_class.strip().upper()]
    return df


def severity_counts(df: pd.DataFrame) -> dict:
    # Count crashes for each severity level
    counts = df["severity"].value_counts()
    return {s: int(counts.get(s, 0)) for s in SEVERITY_ORDER}


def top_factors(df: pd.DataFrame, n: int = 5) -> list[dict]:
    # Find the most common contributing factors
    factors = (
        df[["crash_id", "factors_raw"]]
        .dropna()
        .assign(factor=lambda d: d["factors_raw"].str.split(";"))
        .explode("factor")
    )

    factors["factor"] = _clean_text(factors["factor"])
    factors = factors.dropna(subset=["factor"])
    factors = factors[~factors["factor"].isin(EXCLUDED_FACTORS)]
    factors = factors.drop_duplicates(subset=["crash_id", "factor"])

    total = len(df)
    top = factors["factor"].value_counts().head(n)

    return [
        {
            "factor": name,
            "crashes": int(count),
            "pct_of_crashes": float(round(100 * count / total, 1)) if total else 0.0,
        }
        for name, count in top.items()
    ]


def temporal_patterns(df: pd.DataFrame) -> dict:
    # Count crashes by year, month, weekday, and hour
    weekdays = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    def to_dict(series: pd.Series, keys) -> dict:
        counts = series.value_counts()
        return {str(k): int(counts.get(k, 0)) for k in keys}

    years = sorted(df["year"].dropna().unique())

    return {
        "by_year": to_dict(df["year"], years),
        "by_month": to_dict(df["month"], range(1, 13)),
        "by_weekday": to_dict(df["weekday"], weekdays),
        "by_hour": to_dict(df["hour"], range(24)),
    }


if __name__ == "__main__":
    data = load_crashes()

    print(f"Unique crashes: {len(data):,}")
    print("By severity:", severity_counts(data))

    print("Top 5 factors:")
    for item in top_factors(data):
        print(
            f"  {item['factor']}: {item['crashes']:,} "
            f"({item['pct_of_crashes']}%)"
        )

    print("By year:", temporal_patterns(data)["by_year"])
