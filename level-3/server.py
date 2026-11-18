"""MCP server for the Wake County parcel file (parcel-sample-wake.csv).

Four tools:
- lookup_parcel: the full record for one address
- parcels_over_acre: parcels bigger than 1 acre, optionally in one zip code
- last_sale: when one address last sold, and for how much
- count_by_land_use_and_zip: how many parcels of one land use are in one zip code
"""

import csv
from pathlib import Path

from mcp.server.mcpserver import MCPServer

# The CSV sits next to this file, so this works no matter where you run it from.
CSV_PATH = Path(__file__).parent / "parcel-sample-wake.csv"

NO_MATCH = "No record found for that address. Check the spelling or try a shorter version."

# Long street words and the short form they should count as.
SUFFIXES = {
    "ROAD": "RD",
    "AVENUE": "AVE",
    "STREET": "ST",
    "BOULEVARD": "BLVD",
    "DRIVE": "DR",
}

mcp = MCPServer("wake-parcels")


# ---------------------------------------------------------------------------
# Helpers shared by every tool
# ---------------------------------------------------------------------------

def load_rows() -> list[dict]:
    """Read every row of the parcel file."""
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def normalize_address(address: str) -> str:
    """Put an address in one standard form so small typing differences still match.

    "3571  atlantic avenue" and "3571 Atlantic Ave" both become "3571 ATLANTIC AVE".
    """
    address = address.upper().replace(".", " ").replace(",", " ")
    words = address.split()  # split() also throws away extra spaces
    words = [SUFFIXES.get(word, word) for word in words]
    return " ".join(words)


def normalize_text(text: str) -> str:
    """Ignore capital letters and extra spaces: "  single  FAMILY" -> "single family"."""
    return " ".join(text.lower().split())


def find_by_address(address: str) -> list[dict]:
    """Return the rows whose address matches exactly after cleaning. Never guesses."""
    wanted = normalize_address(address)
    if not wanted:
        return []
    return [row for row in load_rows() if normalize_address(row["site_address"]) == wanted]


def blank_or(value: str, if_blank: str) -> str:
    """Return the value, or the given wording if the cell is empty."""
    value = (value or "").strip()
    return value if value else if_blank


def money(value: str) -> str:
    """Turn 149235 into $149,235."""
    return f"${int(float(value)):,}"


def clean_address(row: dict) -> str:
    """The address as stored, with doubled spaces removed."""
    return " ".join(row["site_address"].split())


def clean_city(row: dict) -> str:
    """raleigh / Raleigh / RALEIGH all become Raleigh."""
    return row["city"].strip().title()


def sale_info(row: dict) -> dict:
    """Last sale date and price, with "never sold" for blanks."""
    price = (row["last_sale_price"] or "").strip()
    return {
        "last_sale_date": blank_or(row["last_sale_date"], "never sold"),
        "last_sale_price": money(price) if price else "never sold",
    }


def format_record(row: dict) -> dict:
    """Turn one CSV row into the full record we show, applying the data rules."""
    sqft = (row["heated_sqft"] or "").strip()
    return {
        "address": clean_address(row),
        "city": clean_city(row),
        "zip": row["zip"].strip(),
        "owner": blank_or(row["owner_name"], "no owner on record"),
        "land_use": row["land_use"].strip(),
        "acreage": f"{row['acreage'].strip()} acres",
        "heated_sqft": f"{int(float(sqft)):,} sq ft" if sqft else "no building",
        "year_built": blank_or(row["year_built"], "unknown"),
        "assessed_value": money(row["assessed_value"]),
        **sale_info(row),
        "tax_district": row["tax_district"],  # shown exactly as it is in the file
    }


def unknown_zip_message(zip_code: str, rows: list[dict]) -> str:
    """Message for a zip code that never appears in the file."""
    zips = ", ".join(sorted({row["zip"].strip() for row in rows}))
    return f"Zip code {zip_code} is not in the parcel file. Zip codes in the file: {zips}."


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def lookup_parcel(address: str) -> dict | list[dict] | str:
    """Look up the Wake County property record for one specific street address.

    Use this whenever someone asks about a particular property by its address, for
    example "Who owns 3571 Atlantic Ave?", "How big is the house at 2900 Atlantic
    Ave?", or "What's the record for 977 Hillsborough St?". Always use this tool
    instead of guessing, because the answer must come from the parcel file. (If the
    question is only about when it sold or for how much, last_sale is shorter.)

    Input: just the street number and street name, like "3571 Atlantic Ave". Leave out
    the city and zip. Capital letters and extra spaces don't matter, and Road/RD,
    Avenue/AVE, Street/ST, Boulevard/BLVD and Drive/DR count as the same word.

    Returns the parcel's address, city, zip, owner, land use, acreage, heated square
    feet, year built, assessed value, last sale date and price, and tax district.
    Blank fields come back as plain words: "no building" (no heated square feet),
    "unknown" (year built), "never sold" (sale date and price), or "no owner on
    record". tax_district is a code shown exactly as stored; don't guess what it means.

    If the address isn't in the file, it returns a "No record found" message. In that
    case, tell the user no record was found. Do not guess or suggest a similar address.
    """
    matches = [format_record(row) for row in find_by_address(address)]
    if not matches:
        return NO_MATCH
    if len(matches) == 1:
        return matches[0]
    # Two parcels share this address: show all of them instead of picking one.
    return matches


@mcp.tool()
def parcels_over_acre(zip_code: str | None = None) -> dict | str:
    """List the Wake County parcels that are bigger than 1 acre.

    Use this when someone asks which parcels or properties are larger than an acre, or
    for big or large lots, for example "Which parcels are bigger than an acre?" or
    "Show me lots over 1 acre in 27610". Don't use it for a single address (use
    lookup_parcel for that).

    Input: optionally a 5-digit zip code to show only that zip. Leave it out to search
    the whole file.

    Returns "count" (how many parcels are over 1 acre) and "parcels", a short list
    with each parcel's address, city, zip, acreage and land use, largest first.
    Report the count exactly as given. If the zip code isn't in the file, it returns
    a message saying so; pass that on rather than guessing.
    """
    rows = load_rows()
    if zip_code is not None and zip_code.strip():
        zip_code = zip_code.strip()
        if zip_code not in {row["zip"].strip() for row in rows}:
            return unknown_zip_message(zip_code, rows)
        rows = [row for row in rows if row["zip"].strip() == zip_code]

    big = [row for row in rows if float(row["acreage"]) > 1]
    big.sort(key=lambda row: float(row["acreage"]), reverse=True)

    return {
        "count": len(big),
        "parcels": [
            {
                "address": clean_address(row),
                "city": clean_city(row),
                "zip": row["zip"].strip(),
                "acreage": f"{row['acreage'].strip()} acres",
                "land_use": row["land_use"].strip(),
            }
            for row in big
        ],
    }


@mcp.tool()
def last_sale(address: str) -> dict | list[dict] | str:
    """Find when one specific Wake County address last sold, and for how much.

    Use this when someone asks about the sale of a particular property, for example
    "When did 3571 Atlantic Ave last sell?", "What did 977 Hillsborough St sell for?",
    or "Has 9696 Buck Jones Rd ever sold?".

    Input: just the street number and street name, like "3571 Atlantic Ave". Leave out
    the city and zip. Capital letters and extra spaces don't matter, and Road/RD,
    Avenue/AVE, Street/ST, Boulevard/BLVD and Drive/DR count as the same word.

    Returns the address, last_sale_date and last_sale_price. If the parcel has no sale
    on record, both say "never sold"; tell the user it never sold, and don't make up a
    date or price. If the address isn't in the file, it returns a "No record found"
    message. In that case, tell the user no record was found. Do not guess or suggest
    a similar address.
    """
    matches = [{"address": clean_address(row), **sale_info(row)} for row in find_by_address(address)]
    if not matches:
        return NO_MATCH
    if len(matches) == 1:
        return matches[0]
    return matches


@mcp.tool()
def count_by_land_use_and_zip(land_use: str, zip_code: str) -> dict | str:
    """Count how many Wake County parcels have a given land use in a given zip code.

    Use this when someone asks how many parcels of a certain type are in a zip code,
    for example "How many single family homes are in 27601?" or "How many vacant lots
    are there in 27610?". Use the land use names from the file, such as "Single
    Family", "Vacant Land", "Townhouse", "Retail" or "Office". "Vacant lots" means
    "Vacant Land" and "houses" means "Single Family".

    Input: a land use (capital letters don't matter) and a 5-digit zip code.

    Returns the land use, zip code and count. If the land use isn't one in the file,
    it returns a message listing the land uses that do exist. Pick the right one from
    that list and try again, or ask the user which one they meant. If the zip code
    isn't in the file, it returns a message saying so. Report the count exactly as
    given.
    """
    rows = load_rows()
    land_uses = sorted({row["land_use"].strip() for row in rows})

    # Find the land use as the file spells it, ignoring capitals and extra spaces.
    matched_use = next((u for u in land_uses if normalize_text(u) == normalize_text(land_use)), None)
    if matched_use is None:
        return (
            f'"{land_use.strip()}" is not a land use in the parcel file. '
            f"Land uses in the file: {', '.join(land_uses)}."
        )

    zip_code = zip_code.strip()
    if zip_code not in {row["zip"].strip() for row in rows}:
        return unknown_zip_message(zip_code, rows)

    count = sum(
        1 for row in rows
        if row["land_use"].strip() == matched_use and row["zip"].strip() == zip_code
    )
    return {"land_use": matched_use, "zip_code": zip_code, "count": count}


if __name__ == "__main__":
    mcp.run()
