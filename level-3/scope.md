**Scope**

**What it does**

This connector lets Claude look up real property records from a Wake County parcel file instead of guessing. You can ask it four kinds of questions:

What’s the record for a specific address?  
Which parcels are bigger than an acre?  
When did a parcel last sell, and for how much?  
How many parcels of a certain type are in a certain zip code?

The data is messy, so the connector follows a few rules to keep its answers honest. It ignores extra spaces and capital letters, and it treats “Road” and “RD” (and similar pairs) as the same word, so a typed address still finds its record. It counts “raleigh,” “Raleigh,” and “RALEIGH” as one city. When a field is blank, it says so plainly instead of filling in a number. A vacant lot shows “no building,” not zero square feet. A parcel that has never sold shows “never sold,” not a made-up price. If an address isn’t in the file at all, the connector says “No record found,” so Claude doesn’t invent an answer.

**What it doesn’t do**

It only reads the data and never changes or adds anything. It doesn’t search by owner name, and it doesn’t pull from the internet or any other database. Everything comes from the one parcel file. One column, tax\_district, doesn’t explain itself, so the connector shows it as-is without guessing what it means.

**How I’ll know it works**

I’ll ask Claude “Who owns 3571 Atlantic Ave?” and check that it answers NELSON, LISA & DONALD, which matches the file. I’ll try a sloppier version, like “3571 atlantic avenue,” and make sure it finds the same record. I’ll ask about an address that isn’t in the file and confirm it says no record was found. Finally, I’ll ask one question of each of the four types and check every answer against the spreadsheet. make this human but neat