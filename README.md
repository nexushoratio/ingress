# Ingress
An old Ingress command line tool I used to work on.

Back when I played a lot of [Ingress](https://ingress.com/), I developed a tool to track new portals in the nine county [San Francisco Bay Area](https://en.wikipedia.org/wiki/San_Francisco_Bay_Area).

The game has some badges that can be obtained by visiting and capturing unique Portals (GPS points of interest in the game).  At the time, information on which Portals a player interacted with was not exposed in the game.  Also, Portals were constantly being added, removed, merged, moved, and edited in the game.  So I wrote a tool to help players track it.

My code consisted of multiple parts:
1. A plugin for [Ingress Intel Total Conversion, aka IITC](https://iitc.me/)
2. A commandline tool for processing information (this stuff here)
3. A Google Apps Script (aka, GAS) to provide a web UI for the information

## IITC

IITC itself was a [userscript](https://en.wikipedia.org/wiki/Userscript) for interacting with the Ingress [Intel map](https://intel.ingress.com/).  In consists of a main script that provided base features, then a bunch of feature specific add-ons (in the form of additional userscripts).  A couple of important add-ons here were *Bookmarks* and *Pan control*.

I wrote another add-on that simply specified a rectangular boundary for the Bay Area and then crawl it.  It would snap to the north-western corner, wait for all of the portal data to load, then add all present to the bookmarks.  It would then move east, with about 10% overlap, and repeat.  Once it reached the eastern boundary, it would return to the western boundary, go south with overlap, and repeat the scan process.  If let alone, the bookmarks would get too big to fit into memory, so once a certain number of portals were captured, it would pause.  I would then export the batch of bookmarks into a JSON file, clear them out, and resume.  This process would continue until it reach the south eastern corner.

And then I would start the whole crawling process over again.  Depending on how aggressive I was (which was pretty rare), I'd do one batch of portals each night.  Scanning was slow, so I just let it run overnight.  It would take several days to scan the whole region.

## This script

This script was the fun part.

Data about the portals was kept in an [SQLite](https://www.sqlite.org/) database using [SQLAlchemy](https://www.sqlalchemy.org/) as an Object Relational Mapper.

I would import the exported bookmark files and add them to the database using the timestamp of the file for the first-seen and last-seen values, as appropriate.  Another piece of meta-data added to portals was what *zip code* it was likely to be in.

After importing all of the bookmark files from a given scan, I would then doing some additional post-processing.  The portals were divided into clusters of sizes I deemed walkable, bikable, and drivable and at least 10 portals.  Due to how these clusters ended up looking, I started calling them donuts and using the terms bites and sprinkles in the code as well.

Eventually this data was uploaded to Apps Script and I would also generate a message about new Portals I would post to the Google+ community for my local team.

## Apps Script

Originally the Apps Script made use of the now deprecated `UiApp` feature.  This allowed one to build a user interface without having to use a typical HTML/CSS/JavaScript.  It could be described in server side code, tying widgets together.

It had, what I thought, was a nice table of all of the Portals.  Users could sort and filter across the various attributes (e.g., time discovered, time last seen, name, zip code, etc), toggle whether they had visited or captured a Portal and even make collections of Portals, seeding them with search results, and export them as IITC compatible bookmarks.  That way players could generate lists of Portals they wanted to visit.

I think there were other exports available as well, but I no longer have the code.

## Interesting aspects

### Number of portals
I do have the last set of Portals that I uploaded on Jan 27, 2019.  At the time, there were 51,050 Portals in the Bay Area.  According to [Ingress Fandom](https://ingress.fandom.com/wiki/Medal), that would be more than enough to earn both the *Explorer* and *Pioneer* badges without ever leaving the Bay Area.

### GIS
I stated at the beginning that I was interested in the *nine counties* making up the Bay Area.  And those don't form a nice rectangular boundary.  So I needed a way to filter Portals.  That research eventually led me to [ZIP Code Tabulation Area, aka ZCTAs](https://en.wikipedia.org/wiki/ZIP_Code_Tabulation_Area).  US ZIP Codes correspond to delivery points/addresses, and not geographical areas.  ZCTAs were created the Census Bureau to roughly map ZIP codes to geographical area.

ZCTA data is available as a [shapefile](https://en.wikipedia.org/wiki/Shapefile).  The data is huge, too large to regularly load into memory.  So zcta.py is used to preprocess that data into something I could use more easily.

As Portals are imported, the ZCTA boundaries are used to assign a ZIP code.  After a series of imports, I would query which codes are new.  I would then manually look those up to see if they were in a Bay Area county or not, and tag them as keep or not.  Then run a pruning operation that would delete portals if they were in an outside ZCTA.

All of that delved into using shapefiles, learning the [shapely](https://shapely.readthedocs.io/en/stable/) Python library for using geometric objects (is a point inside a ZCTA), cartographic projects with the [pyproj](https://pyproj4.github.io/pyproj/stable/) library, and probably some other stuff I've forgotten since then.

There is also a [TSP](https://en.wikipedia.org/wiki/Travelling_salesman_problem) solver.  I could import a bookmark file of Portals to visit, and find an efficient route for visiting them, and export that as a [KML](https://developers.google.com/kml) file.  I would then import that KML into [Google My Maps](https://www.google.com/maps/about/mymaps/).

I don't think Google Maps had a solver API at the time, but I could use the API to get best routes between any two points.  Since the free API had usage limits, I would prefetch as much info as I could to cache it.  Then during the actual solving, it the real value wasn't available, it would estimate it based upon straight-line distance.  I also wrote a Google Apps Script service to take the same REST API that GMaps used and ended up doubling my daily requests.  As seen at the top of the TSP solver, it wasn't the best on the market.  It was a port of a JavaScript solution someone did as a grad student project, I think.  But it worked well enough for this stuff.

### Apps Script

Since the data was mostly static, I uploaded it to GAS as code.  Basically, a JSON file modified to be a variable assignment.  Eventually this got to be too big, and I had to separate it out into a GAS style library project.  And eventually, into four different projects with the Portals equally divided amongst them.

## Summary

This was a fun project.  I probably spent more time on this than playing the game itself.

This is all Python2.  This, along with older libraries, and the fact that IITC itself looks defunct, it would probably take a lot of work to get this working again.  But, here for posterity.
