# The World Today — Sunday 22 November 2026 in one image

[![make.fun bounty](https://make.fun/badge/news-image-20261122.svg)](https://make.fun/bounty/news-image-20261122)
[![make.fun rank](https://make.fun/badge/news-image-20261122/Rizaltri13/news-image-20261122-r2/rank.svg)](https://make.fun/bounty/news-image-20261122)
[![make.fun reward](https://make.fun/badge/news-image-20261122/Rizaltri13/news-image-20261122-r2/reward.svg)](https://make.fun/bounty/news-image-20261122)

A one-page newspaper front page that sums up the world news of Sunday
22 November 2026 in a single 1024×1024 image. The lead story — Iran's
missile and drone strike on US bases in Bahrain — gets the hero
illustration, the masthead treatment and the standfirst; six more of
the day's stories run as tiles below it, and a wire ticker along the
foot of the page carries the rest.

## How it works

`main.py` is a standard-library-only Python 3 program. It decodes the
hero illustration (`hero.png`) with its own PNG reader, cover-crops it
into the front page's picture box, then draws the whole page — masthead,
date band, headline, standfirst, story tiles and ticker — with a
built-in 5×7 bitmap typeface, and writes the result as a PNG through
its own encoder with per-row adaptive filtering.

Run it the way the grader does:

```
mkdir -p out
MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Without `MAKEFUN_OUTPUT_DIR` it writes to `/output/entry.png`. The
program reads nothing but `hero.png`, touches no network, and is fully
deterministic: two runs write byte-identical files (the page is under
the 1 MiB cap, at 1024×1024).

## The day's stories

Lead: Iran strikes US bases in Bahrain (IRGC claims two Patriot radar
sites hit; Bahrain reports a fire at a civilian industrial site;
Washington has not confirmed damage). Tiles: COP31 in overtime over
fossil fuels · Mexico captures "El Chapo Isidro" · Russian ship
Sparta II burning in the Baltic · Hong Kong's election-committee vote ·
Zverev v Alcaraz for the Turin crown · double-tap strike on Kryvyi
Rih. Ticker: Bolsonaro in ICU · Al-Shabaab ambush in Somalia ·
Zelenskyy on NATO guarantees · EU–Indonesia trade deal · Trump's
20-year Iran deal remark.

Entry for the make.fun bounty
[news-image-20261122](https://make.fun/bounty/news-image-20261122).
MIT licensed.
