See the [History](HISTORY.md) for more information.

# Ingress

This is a tool for working with Ingress data (well, actually, [IITC](https://iitc.app/) data).

It is currently in the process of being reworked after languishing nearly four years, including porting to Python 3.

It is also serving as a way to learn the modern Python eco-system outside of my previous employer's custom programming environment.

Currently (2023-12-29), the tool can do nothing more than run `--help`, but this should change fairly quickly.

The following are most of the historical commands that I plan on refreshing:
```
usage: ingress [-h] [-L {debug,info,warning,error,critical}] <command> ...

Perform a number of Ingress related functions.

Mostly this works on data saved via IITC, like saved bookmarks and drawtools.

Global flags:
  -h, --help
  -L {debug,info,warning,error,critical}, --log-level {debug,info,warning,error,critical}
                        Minimal log level

Commands:
  For more details: ingress <command> --help

  <command>             <command description>
    ingest              Update the database with portals listed in a bookmarks
                        file.
    expunge             Remove portals listed in a bookmarks file from the
                        database.
    export              Export all portals as a bookmarks file.
    flatten             Load portals from BOOKMARKS and write out as lists
                        using PATTERN.
    find-missing-labels
                        Look through globs of bookmarks for missing labels.
    merge               Merge multiple bookmarks files into one.
    update              Update the locations and directions for portals in a
                        bookmarks file.
    bounds              Create a drawtools file outlining portals in multiple
                        bookmarks files.
    trim                Trim a bookmarks file to only include portals inside a
                        boundary.
    cluster             Find clusters of portals together and save the
                        results.
    donuts              Automatically group portals into COUNT sized bookmarks
                        files.
    clean               Clean and format a json file.
    show                Show portals sorted by date.
    route               Calculate an optimal route between portals listed in a
                        bookmarks file.
```