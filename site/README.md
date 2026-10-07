# Website

The knowledge tool's product page uses the Amplifier Smart Tools family theme. Page content
lives in `site.json`. `site/theme/` is a versioned copy of the family theme (version 0.1.0, MIT
licensed; see `site/theme/LICENSE`), taken from the decisioncraft page, which carries its local
changes (demo links, an install band). The only change here: `family.json` registers this page
under the key `knowledge`.

## Build and preview

```sh
python3 scripts/build-examples.py       # example graphs -> site/assets/*.html (no model)
python3 scripts/record-demos.py         # demo videos and posters -> docs/images (Playwright + ffmpeg)
python3 -m venv .work/site-venv
.work/site-venv/bin/python -m pip install -r site/requirements.txt
.work/site-venv/bin/python site/theme/build.py
python3 -m http.server 8000 --directory _site --bind 127.0.0.1
```

Open http://127.0.0.1:8000. Output goes to `_site/` (ignored by Git). The example graphs in
`site/assets/` are copied into the page's assets, so "Open the example graph" links work offline.

## Demos

`scripts/record-demos.py [scene ...]` records gaps, evidence, path, time, agent and words, then
cuts `docs/images/trailer.mp4` from them. `scripts/record-live.py GRAPH STOPFILE` records the live
view while real agents write to GRAPH (the live demo was four Claude Code agents extracting the
Amplifier docs), then speeds it up. Every scene drives a real view with real clicks;
the agent scene replays real command output captured from the example graph at record time.
