# Data decisions: parcels table

## Column types
| Column | Type | Why |
|---|---|---|
| pin | TEXT | ID, not a quantity. A number type would drop leading zeros (0763551410). Primary key. |
| site_address | TEXT | Words. |
| city | TEXT | Words. Cleaned to one spelling at load (raleigh/RALEIGH → Raleigh). |
| zip | TEXT | Looks like a number, but never used for math. |
| zoning | TEXT | Code like R-4 or CX-3: what the city allows on the parcel. |
| land_use | TEXT | Words: what is actually on the parcel now. |
| acreage | REAL | Decimals (0.418). INTEGER would round it to 0 without warning. |
| heated_sqft | INTEGER | Whole number. Blank = no building, stored empty (NULL), never 0. |
| year_built | INTEGER | Whole number. Blank = vacant land OR unknown year, stored empty. |
| assessed_value | INTEGER | Whole dollars, no cents. |
| last_sale_date | TEXT | Stored as YYYY-MM-DD so it still sorts and compares correctly. Blank = never sold. |
| last_sale_price | INTEGER | Whole dollars. Blank = never sold, stored empty, never 0. |
| tax_district | TEXT | Code for which governments tax the parcel (WAKE-RAL = county + Raleigh; WAKE = county only). |
| owner_name | TEXT | Words. Mixed casing; 4 rows blank. Searches must ignore case. 

## Address matching
Problem: a person types "9696 Buck Jones Road" but the record stores "9696  BUCK JONES RD".

Rule: before comparing, clean BOTH the typed address and the stored address the same way:
1. Uppercase everything
2. Trim spaces off the ends
3. Collapse double spaces into one
4. Shorten street words: ROAD→RD, STREET→ST, AVENUE→AVE, BOULEVARD→BLVD, DRIVE→DR, LANE→LN
5. Remove punctuation (periods, commas)

Storage: keep site_address exactly as the county wrote it, and add a second column,
address_key, holding the cleaned version. Lookups match against address_key.


