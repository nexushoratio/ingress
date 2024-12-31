See the [History](HISTORY.md) for more information.

# Ingress

This is a tool for working with Ingress data (well, actually, [IITC](https://iitc.app/) data).

It is in the process of being reworked after languishing nearly four years.  Current (2024-12-31) activities include:
* Modernizing use of SQLAlchemy
* Porting use of spatial libraries to Geoalchemy
* Finding replacements for old libraries

It is also serves as a way to learn the modern Python eco-system outside of my employer's custom development environment.

With the addition of new features, the commands are nest:
```
$ ingress
usage: ingress [-h] [-L {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
               [--log-dir LOG_DIR] [--db-dir DB_DIR] [--db-name DB_NAME]
               <command> ...

Perform a number of Ingress related functions.

Mostly this works on data saved via IITC, like bookmarks and drawtools.

Note: This tool is currently being updated to use geometry/geographic databases
instead of python libraries for certain calculations.  Commands marked with
"(V)" have been verified to work under those conditions.

Global flags:
  -h, --help
  -L {DEBUG,INFO,WARNING,ERROR,CRITICAL}, --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Minimal log level (Default: INFO)
  --log-dir LOG_DIR     Logging directory (Default:
                        /home/nexus/.local/state/ingress/log)
  --db-dir DB_DIR       Database directory (Default:
                        /home/nexus/.local/share/ingress)
  --db-name DB_NAME     Database file name (Default: ingress.db)

Commands:
  For more details: ingress <command> --help

  <command>             <command description>
    flatten             (V) Load portals from BOOKMARKS and save flat lists
                        using PATTERN.
    find-missing-labels
                        (V) Look through globs of bookmarks for missing
                        labels.
    merge               (V) Merge multiple bookmarks files into one.
    bookmark            (V) A family of commands for working with bookmarks in
                        the database.
    place               (V) A family of commands for working with places.
    geo                 (V) A family of commands for working with geometry.
    address             (V) A family of address commands.
    clean               (V) Clean and format a json file.
    portal              (V) A family of commands for working with portals.
    route               Calculate an optimal route between portals in a
                        bookmarks file.
```

```
$ ingress bookmark
usage: ingress bookmark [-h] <command> ...

(V) A family of commands for working with bookmarks in the database.

options:
  -h, --help  show this help message and exit

Commands:
  For more details: ingress bookmark <command> --help

  <command>   <command description>
    read      (V) Read an IITC style bookmark file.
    write     (V) Write an IITC style bookmark file.
    folder    (V) A family of commands for working with bookmark folders.
    map       (V) A family of commands for working with map bookmarks.
    portal    (V) A family of commands for working with portal bookmarks.
 ```

```
$ ingress place
usage: ingress place [-h] <command> ...

(V) A family of commands for working with places.

options:
  -h, --help  show this help message and exit

Commands:
  For more details: ingress place <command> --help

  <command>   <command description>
    list      (V) List specific places in the database.
    add       (V) Add a specific place to the database.
    set       (V) Update settings on a specific place in the database.
    del       (V) Delete one or more specific places from the database.
```

```
$ ingress geo
usage: ingress geo [-h] <command> ...

(V) A family of commands for working with geometry.

options:
  -h, --help  show this help message and exit

Commands:
  For more details: ingress geo <command> --help

  <command>   <command description>
    bounds    Create a drawtools file outlining portals in multiple bookmark
              folders.
    trim      Trim a bookmarks file to only include portals inside a boundary.
    cluster   Find clusters of portals together and save the results.
    donuts    (V) Automatically group portals into COUNT sized bookmarks
              files.
    ellipse   (V) Find a number of n-ellipse containing portals.
    update    Update the directions between portals in a bookmarks file.
```

```
$ ingress address
usage: ingress address [-h] <command> ...

(V) A family of address commands.

options:
  -h, --help  show this help message and exit

Commands:
  For more details: ingress address <command> --help

  <command>   <command description>
    update    (V) Update address related data for portals in a BOOKMARKS file.
    prune     (V) Remove portals from the database that do not match criteria.
    type      (V) A family of (address, type) commands.
```

```
$ ingress portal
usage: ingress portal [-h] <command> ...

(V) A family of commands for working with portals.

options:
  -h, --help  show this help message and exit

Commands:
  For more details: ingress portal <command> --help

  <command>   <command description>
    ingest    (V) Update the database with portals listed in a bookmarks file.
    expunge   (V) Remove portals listed in a bookmarks file from the database.
    export    (V) Export all portals as a bookmarks file.
    show      (V) Show portals selected, sorted and grouped by constraints.
```
