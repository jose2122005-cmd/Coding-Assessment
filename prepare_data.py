from processing import CLEAN_PATH, load_crashes, save_clean

if __name__ == "__main__":
    # Load the crash data
    df = load_crashes()

    # Save the cleaned data
    save_clean(df)

    size_mb = CLEAN_PATH.stat().st_size / 1_000_000

    print(
        f"Saved {CLEAN_PATH} -> "
        f"{len(df):,} crashes, {size_mb:.1f} MB"
    )
