# Wake Parcels

A web page and API for looking up Wake County, NC parcel records by street address.
Type an address and get the parcel's record: owner, acreage, zoning, land use,
assessed value and last sale.

**Live site:** https://wake-parcels.onrender.com
(Free hosting: the first visit after 15 idle minutes can take about a minute to load.)

## How it works
- **Data:** a sample of Wake County parcel records (`parcel-sample-wake.csv`),
  loaded into a Supabase Postgres table by `load_parcels.py`.
- **Server:** `server.py` serves the web page, a JSON API at
  `/parcels?address=...`, and MCP tools my AI assistant uses (Module 3.1).
- **Secrets:** the database connection string is never in this repo. The server
  reads it from the `DATABASE_URL` environment variable (on Render, set in the
  dashboard; on a laptop, loaded from a local `.env` file that Git ignores).
- **Deploys:** Render watches `main`. Every merge to `main` deploys automatically.

## Run it on a laptop (Windows PowerShell)
From the `level-3` folder:
```
pip install -r requirements.txt
# put your Supabase connection string in a .env file: DATABASE_URL=postgresql://...
python load_parcels.py        # only needed once, to create and fill the table
$env:DATABASE_URL = ((Get-Content .env | Select-String '^DATABASE_URL=').Line -split '=',2)[1].Trim('"')
python server.py --http
```
Then open http://localhost:8000.

## Other files
- `data-decisions.md`: column types and address-matching rules
- `scope.md`: project scope
- `commercial-use-note.md`: what would make this commercial rather than coursework