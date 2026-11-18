"""Load parcel-sample-wake.csv into a Supabase (Postgres) table called parcels.

Follows the rules in data-decisions.md:
- column types (pin and zip are TEXT, acreage is REAL, money and sizes are INTEGER)
- blank cells are stored as empty (NULL), never 0
- city is cleaned to one spelling (raleigh / RALEIGH -> Raleigh)
- address_key holds a cleaned copy of site_address for lookups
  (uppercase, trimmed, single spaces, short street words, no periods or commas)

Setup (once):
    pip install "psycopg[binary]" python-dotenv
    Put this line in a file called .env next to this script (never commit it):
        DATABASE_URL=postgresql://...your Supabase connection string...

Run:
    python load_parcels.py

Safe to run more than once: rows are matched by pin and updated, not duplicated.
"""

import csv
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

HERE = Path(__file__).parent
CSV_PATH = HERE / "parcel-sample-wake.csv"

# Long street words and the short form they should count as (data-decisions.md).
SUFFIXES = {
    "ROAD": "RD",
    "STREET": "ST",
    "AVENUE": "AVE",
    "BOULEVARD": "BLVD",
    "DRIVE": "DR",
    "LANE": "LN",
}

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS parcels (
    pin             TEXT PRIMARY KEY,
    site_address    TEXT NOT NULL,
    address_key     TEXT NOT NULL,
    city            TEXT,
    zip             TEXT,
    zoning          TEXT,
    land_use        TEXT,
    acreage         REAL,
    heated_sqft     INTEGER,
    year_built      INTEGER,
    assessed_value  INTEGER,
    last_sale_date  TEXT,
    last_sale_price INTEGER,
    tax_district    TEXT,
    owner_name      TEXT
);
CREATE INDEX IF NOT EXISTS parcels_address_key_idx ON parcels (address_key);
"""

COLUMNS = [
    "pin", "site_address", "address_key", "city", "zip", "zoning", "land_use",
    "acreage", "heated_sqft", "year_built", "assessed_value", "last_sale_date",
    "last_sale_price", "tax_district", "owner_name",
]

# Insert a row; if that pin is already there, overwrite it with the new values.
INSERT_ROW = f"""
INSERT INTO parcels ({", ".join(COLUMNS)})
VALUES ({", ".join(["%s"] * len(COLUMNS))})
ON CONFLICT (pin) DO UPDATE SET
    {", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS if c != "pin")}
"""


def make_address_key(address: str) -> str:
    """Uppercase, trim, collapse double spaces, shorten street words, remove punctuation.

    "9696 Buck Jones Road" and "9696  BUCK JONES RD." both become "9696 BUCK JONES RD".
    """
    # Periods and commas become spaces (not deleted) so "RD." still matches RD and
    # "MAIN ST,RALEIGH" doesn't glue into one word. Same approach as server.py.
    address = address.upper().replace(".", " ").replace(",", " ")
    words = address.split()  # split() trims the ends and collapses spaces
    return " ".join(SUFFIXES.get(word, word) for word in words)


def text_or_none(value: str) -> str | None:
    """Trimmed text, or None (empty in the database) if the cell is blank."""
    value = (value or "").strip()
    return value or None


def int_or_none(value: str) -> int | None:
    """Whole number, or None if blank. Blank never becomes 0."""
    value = (value or "").strip()
    return int(float(value)) if value else None


def real_or_none(value: str) -> float | None:
    """Decimal number, or None if blank."""
    value = (value or "").strip()
    return float(value) if value else None


def clean_city(value: str) -> str | None:
    """raleigh / Raleigh / RALEIGH all become Raleigh."""
    value = text_or_none(value)
    return value.title() if value else None


def to_db_row(row: dict) -> tuple:
    """Turn one CSV row into the values for one database row, in COLUMNS order."""
    return (
        row["pin"].strip(),
        row["site_address"],                  # kept exactly as the county wrote it
        make_address_key(row["site_address"]),
        clean_city(row["city"]),
        text_or_none(row["zip"]),
        text_or_none(row["zoning"]),
        text_or_none(row["land_use"]),
        real_or_none(row["acreage"]),
        int_or_none(row["heated_sqft"]),
        int_or_none(row["year_built"]),
        int_or_none(row["assessed_value"]),
        text_or_none(row["last_sale_date"]),  # already YYYY-MM-DD in the file
        int_or_none(row["last_sale_price"]),
        text_or_none(row["tax_district"]),
        text_or_none(row["owner_name"]),
    )


def main() -> None:
    load_dotenv(HERE / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        sys.exit("DATABASE_URL is not set. Add it to level-3/.env (see the top of this file).")

    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        rows = [to_db_row(row) for row in csv.DictReader(f)]
    print(f"Read {len(rows)} rows from {CSV_PATH.name}")

    # The "with" block commits if everything works, and undoes everything if anything fails.
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE)
            cur.executemany(INSERT_ROW, rows)
            cur.execute("SELECT COUNT(*) FROM parcels")
            total = cur.fetchone()[0]

    print(f"Done. The parcels table now has {total} rows.")


if __name__ == "__main__":
    main()
