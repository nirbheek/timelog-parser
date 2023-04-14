## Requirements

```sh
$ pip3 install --user regex
```

## Description

Timelog parser for a timelog text file in the following format:

```
== Month YYYY

date1: 2h30m of taskname-description, 15m of taskname-description2, 10m of taskname2-description3

date2: 2h30m of taskname-description, 15m of taskname-description2, 10m of taskname2-description3

...

expense: description of expense: cost
expense: description2 of expense2: unit_cost, quantity

== Month YYYY

...
```

* Report will aggregate everything inside the `<monthname_year>` block. Everything after `== ` is used as the heading for the report.
* Each day's entry must begin with `<word>: ` where `<word>` is ignored. The remaining line consists of `<time> of <task>` timelog entries separated by `, `.
* `<time>` is of the format `<number>h<number>m` or `<number>h` or `<number>m`
* `<task>` is of the format `<taskname>-<description>` where:
   - `<taskname>` must not contain any of: `<space>of<space>` or `,<space>` or `-`
   - `<description>` must not contain any of: `<space>of<space>` or `,<space>`
* By default, `<time>` is aggregated under `<taskname>`, but with the `--project-detail` option, aggregation will happen under `<taskname>-<description>`.
* Invalid daily entries are ignored

Example log (`test.txt`):

```
== Dec 2019

1st: 4h of gnome-glib macOS CI, 1h of misc-IRC

2nd: depression, no work

3rd: 15m of misc-email, 2h50m of mozilla-cerbero-uwp-porting-work

4th: sickness, no work

5th: 30m of misc-email-and-IRC, 3h15m of mozilla-cerbero-openssl-variant at 1430
```

This will be aggregated as:

```
$ ./parse-timelog.py test.txt 0 -d
Ignoring invalid/unknown entry 'depression'
Ignoring invalid/unknown entry 'no work'
Ignoring invalid/unknown entry 'sickness'
Ignoring invalid/unknown entry 'no work'
# Dec 2019
Project              Hours      Cost
mozilla               6h5m      0.00
gnome                 4h        0.00
misc                  1h45m     0.00
Total:               11h50m     0.00
```

Change the `HOURLY_RATE` variable to calculate the `Cost` column correctly. To see more details, pass `--project-detail`:

```
$ ./parse-timelog.py test.txt 0 --project-detail
Ignoring invalid/unknown entry 'depression'
Ignoring invalid/unknown entry 'no work'
Ignoring invalid/unknown entry 'sickness'
Ignoring invalid/unknown entry 'no work'
# Dec 2019
Project              Hours      Cost
gnome-glib macOS CI   4h        0.00
mozilla-cerbero-openssl-variant  3h15m     0.00
mozilla-cerbero-uwp-porting-work  2h50m     0.00
misc-IRC              1h        0.00
misc-email-and-IRC      30m     0.00
misc-email              15m     0.00
Total:               11h50m     0.00
```
