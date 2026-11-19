"""MCP server for Wake County parcels, reading from the Supabase parcels table.

Four tools (the four questions from the dataset README):
- lookup_parcel: the full record for one address
- parcels_over_acre: parcels bigger than 1 acre, largest first
- last_sale: when one address last sold, and for how much
- count_by_land_use_and_zip: how many parcels of one land use are in one zip code

Two plain web pages:
- /                                    -> status page: says the service is running
- /parcels?address=3571 Atlantic Ave  -> that parcel's record, same lookup as lookup_parcel

Setup: the database password comes ONLY from the environment variable
DATABASE_URL (never from a file). On the host, set it in the dashboard. Locally,
in PowerShell:  $env:DATABASE_URL = "postgresql://..."
load_parcels.py must have been run first so the parcels table exists.

Run:
    python server.py          # for Claude Desktop (stdio). Tools only.
    python server.py --http   # web server on 0.0.0.0, port $PORT (8000 if unset)
                              #   status at /, tools at /mcp, web page at /parcels?address=...
"""

import os
import sys

import anyio
import psycopg
from mcp.server.mcpserver import MCPServer
from psycopg.rows import dict_row
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

# The exact same cleaning rule the loader used to build address_key.
# Importing it (instead of copying it) means the two can never drift apart.
from load_parcels import make_address_key

# The password comes only from the DATABASE_URL environment variable,
# never from this file or any other file.
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    sys.exit(
        "DATABASE_URL is not set. Set it as an environment variable "
        "(on the host: in its dashboard; locally: $env:DATABASE_URL = \"postgresql://...\")."
    )

NO_MATCH = "No parcel found for that address. Check the spelling or try a shorter version."

# Every column of the full record, in a sensible reading order.
# acreage is stored as REAL, which would come back as 0.41800001; going through
# numeric first brings it back as 0.418.
RECORD_COLUMNS = """
    pin, site_address, city, zip, zoning, land_use,
    acreage::numeric::float8 AS acreage,
    heated_sqft, year_built, assessed_value,
    last_sale_date, last_sale_price, tax_district, owner_name
"""

mcp = MCPServer("wake-parcels")


# ---------------------------------------------------------------------------
# Database helpers shared by every tool
# ---------------------------------------------------------------------------

def query(sql: str, params: tuple = ()) -> list[dict]:
    """Run one read-only query against Supabase and return the rows as dicts.

    Blank cells were stored as NULL, so they come back as None (empty), never 0.
    prepare_threshold=None keeps this working through Supabase's connection pooler.
    """
    with psycopg.connect(DATABASE_URL, row_factory=dict_row, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def find_by_address(address: str) -> list[dict]:
    """Return the parcels whose address_key matches the cleaned typed address. Never guesses."""
    key = make_address_key(address or "")
    if not key:
        return []
    return query(
        f"SELECT {RECORD_COLUMNS} FROM parcels WHERE address_key = %s ORDER BY pin",
        (key,),
    )


def one_or_all(matches: list[dict]) -> dict | list[dict] | str:
    """No match -> the no-parcel message; one -> that record; two or more -> all of them."""
    if not matches:
        return NO_MATCH
    if len(matches) == 1:
        return matches[0]
    # Two parcels share this address: show all of them instead of picking one.
    return matches


def all_zips() -> list[str]:
    return [r["zip"] for r in query("SELECT DISTINCT zip FROM parcels WHERE zip IS NOT NULL ORDER BY zip")]


def unknown_zip_message(zip_code: str, zips: list[str]) -> str:
    return f"Zip code {zip_code} is not in the parcels table. Zip codes in the table: {', '.join(zips)}."


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def lookup_parcel(address: str) -> dict | list[dict] | str:
    """Look up the Wake County property record for one specific street address.

    Use this whenever someone asks about a particular property by its address, for
    example "Who owns 3571 Atlantic Ave?", "How big is the house at 2900 Atlantic
    Ave?", or "What's the record for 977 Hillsborough St?". Always use this tool
    instead of guessing, because the answer must come from the parcels table. (If the
    question is only about when it sold or for how much, last_sale is shorter.)

    Input: just the street number and street name, like "3571 Atlantic Ave". Leave out
    the city and zip. Capital letters, extra spaces, periods and commas don't matter,
    and Road/RD, Avenue/AVE, Street/ST, Boulevard/BLVD, Drive/DR and Lane/LN count as
    the same word.

    Returns pin, site_address, city, zip, zoning, land_use, acreage, heated_sqft,
    year_built, assessed_value (whole dollars), last_sale_date (YYYY-MM-DD),
    last_sale_price (whole dollars), tax_district and owner_name.
    A blank field comes back empty (null), never 0. Read it as: heated_sqft empty =
    no building; year_built empty = unknown; last_sale_date and last_sale_price
    empty = never sold; owner_name empty = no owner on record. Never turn an empty
    field into 0 or a made-up value. tax_district is a code shown exactly as stored;
    don't guess what it means.

    If the address isn't in the table, it returns a "No parcel found" message. In that
    case, tell the user no parcel was found. Do not guess or suggest a similar address.
    """
    return one_or_all(find_by_address(address))


@mcp.tool()
def parcels_over_acre(zip_code: str | None = None) -> dict | str:
    """List every Wake County parcel bigger than 1 acre, largest first.

    Use this when someone asks which parcels or properties are larger than an acre, or
    for big or large lots, for example "Which parcels are bigger than an acre?" or
    "Show me lots over 1 acre in 27610". Don't use it for a single address (use
    lookup_parcel for that).

    Input: optionally a 5-digit zip code to show only that zip. Leave it out to search
    every parcel.

    Returns "count" (how many parcels are over 1 acre) and "parcels", each with
    site_address, city, zip, acreage and land_use, largest acreage first. Report the
    count exactly as given. If the zip code isn't in the table, it returns a message
    saying so; pass that on rather than guessing.
    """
    sql = (
        "SELECT site_address, city, zip, acreage::numeric::float8 AS acreage, land_use "
        "FROM parcels WHERE acreage > 1"
    )
    params: tuple = ()

    if zip_code is not None and zip_code.strip():
        zip_code = zip_code.strip()
        zips = all_zips()
        if zip_code not in zips:
            return unknown_zip_message(zip_code, zips)
        sql += " AND zip = %s"
        params = (zip_code,)

    rows = query(sql + " ORDER BY acreage DESC", params)
    return {"count": len(rows), "parcels": rows}


@mcp.tool()
def last_sale(address: str) -> dict | list[dict] | str:
    """Find when one specific Wake County address last sold, and for how much.

    Use this when someone asks about the sale of a particular property, for example
    "When did 3571 Atlantic Ave last sell?", "What did 977 Hillsborough St sell for?",
    or "Has 9696 Buck Jones Rd ever sold?".

    Input: just the street number and street name, like "3571 Atlantic Ave". Leave out
    the city and zip. Capital letters, extra spaces, periods and commas don't matter,
    and Road/RD, Avenue/AVE, Street/ST, Boulevard/BLVD, Drive/DR and Lane/LN count as
    the same word.

    Returns site_address, last_sale_date (YYYY-MM-DD) and last_sale_price (whole
    dollars). If both are empty (null), the parcel has never sold: tell the user it
    never sold, and don't make up a date or price. If the address isn't in the table,
    it returns a "No parcel found" message. In that case, tell the user no parcel was
    found. Do not guess or suggest a similar address.
    """
    matches = [
        {
            "site_address": row["site_address"],
            "last_sale_date": row["last_sale_date"],
            "last_sale_price": row["last_sale_price"],
        }
        for row in find_by_address(address)
    ]
    return one_or_all(matches)


@mcp.tool()
def count_by_land_use_and_zip(land_use: str, zip_code: str) -> dict | str:
    """Count how many Wake County parcels have a given land use in a given zip code.

    Use this when someone asks how many parcels of a certain type are in a zip code,
    for example "How many single family homes are in 27601?" or "How many vacant lots
    are there in 27610?". Use the land use names from the table, such as "Single
    Family", "Vacant Land", "Townhouse", "Retail" or "Office". "Vacant lots" means
    "Vacant Land" and "houses" means "Single Family".

    Input: a land use (capital letters and extra spaces don't matter) and a 5-digit
    zip code.

    Returns land_use, zip_code and count. If the land use isn't one in the table, it
    returns a message listing the land uses that do exist. Pick the right one from
    that list and try again, or ask the user which one they meant. If the zip code
    isn't in the table, it returns a message saying so. Report the count exactly as
    given.
    """
    land_uses = [
        r["land_use"]
        for r in query("SELECT DISTINCT land_use FROM parcels WHERE land_use IS NOT NULL ORDER BY land_use")
    ]

    # Find the land use as the table spells it, ignoring capitals and extra spaces.
    wanted = " ".join((land_use or "").lower().split())
    matched_use = next((u for u in land_uses if " ".join(u.lower().split()) == wanted), None)
    if matched_use is None:
        return (
            f'"{(land_use or "").strip()}" is not a land use in the parcels table. '
            f"Land uses in the table: {', '.join(land_uses)}."
        )

    zip_code = (zip_code or "").strip()
    zips = all_zips()
    if zip_code not in zips:
        return unknown_zip_message(zip_code, zips)

    count = query(
        "SELECT COUNT(*) AS n FROM parcels WHERE land_use = %s AND zip = %s",
        (matched_use, zip_code),
    )[0]["n"]
    return {"land_use": matched_use, "zip_code": zip_code, "count": count}


# ---------------------------------------------------------------------------
# Status page: /
# ---------------------------------------------------------------------------

STATUS_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Wake Parcels</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 40rem; margin: 3rem auto; padding: 0 1rem; line-height: 1.5; }
    code { background: #f2f2f2; padding: 0.1rem 0.3rem; border-radius: 4px; }
  </style>
</head>
<body>
  <h1>Wake Parcels</h1>
  <p>&#9989; The service is running.</p>
   <form action="/parcels" method="get">
    <label for="address">Look up a Wake County parcel by address:</label><br>
    <input id="address" name="address" placeholder="3571 Atlantic Ave" required>
    <button type="submit">Look up</button>
  </form>
</body>
</html>
"""


@mcp.custom_route("/", methods=["GET"])
async def status_page(request: Request) -> HTMLResponse:
    """Simple page so you (and the host's health check) can see the service is up."""
    return HTMLResponse(STATUS_PAGE)


# ---------------------------------------------------------------------------
# Plain web page: /parcels?address=3571 Atlantic Ave
# ---------------------------------------------------------------------------

@mcp.custom_route("/parcels", methods=["GET"])
async def parcels_page(request: Request) -> JSONResponse:
    """Same lookup and cleaning as lookup_parcel, shown in the browser as JSON."""
    address = request.query_params.get("address", "")
    if not address.strip():
        return JSONResponse(
            {"message": "Add an address to the link, like /parcels?address=3571 Atlantic Ave"}
        )

    # The database call is slow-ish, so run it off the web server's main loop.
    matches = await anyio.to_thread.run_sync(find_by_address, address)
    if not matches:
        # A normal (200) response with a plain message, not an error page.
        return JSONResponse({"message": f"No parcel found for {address.strip()!r}."})
    return JSONResponse(matches[0] if len(matches) == 1 else matches)


if __name__ == "__main__":
    if "--http" in sys.argv:
        # The host tells us which port to use through PORT. 0.0.0.0 means
        # "accept connections from outside this machine", which a host needs.
        mcp.run("streamable-http", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
    else:
        mcp.run()
