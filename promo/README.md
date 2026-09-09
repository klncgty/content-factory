# The film

A ~38s film about [Content Factory](../README.md), built with
[Remotion](https://remotion.dev) — React components rendered frame by frame,
so every claim on screen is a value in the codebase rather than a slide.

Direction is *Press Room*: graphite for the machine, newsprint for what it
makes, and colour reserved entirely for the three verdicts a guard can return
(`pass`, `warn`, `reject`). Nothing decorative is allowed to use those three.
Tokens live in [`src/brand.ts`](./src/brand.ts).

## The cut

| # | Scene | Frames | Beat |
|---|---|---|---|
| 1 | `Opening` | 80 | Wordmark, rule, one line of spec. |
| 2 | `Drift` | 165 | Knowledge says 5–8 °C; the draft says 6–8 °C. |
| 3 | `Pipeline` | 240 | Ten agents light in order; the Editor lights amber. |
| 4 | `Guards` | 230 | A draft is rejected at `GroundingGuard`, retried, published. |
| 5 | `Brands` | 165 | A brand is six files, none of them Python. |
| 6 | `Publish` | 195 | Markdown + images → commit → live. |
| 7 | `EndCard` | 145 | Address and the two numbers worth trusting. |

1220 frames less six 15-frame dissolves = **1130 frames (37.7s at 30fps)**.
Every scene is also registered on its own under the *Scenes* folder in the
Studio, so one plate can be re-timed without scrubbing the whole film.

## Working on it

```bash
npm install
npx remotion studio                                   # preview and edit
npx remotion still Guards --frame=84 --scale=0.5 out/check.png   # one-frame check
npx remotion render ContentFactoryPromo out/content-factory-promo.mp4 --codec=h264 --crf=20
```

The committed copies live in [`../docs/promo/`](../docs/promo). After a
re-render, refresh both:

```bash
cp out/content-factory-promo.mp4 ../docs/promo/
ffmpeg -y -i out/content-factory-promo.mp4 \
  -vf "fps=10,scale=720:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=4" \
  ../docs/promo/content-factory-promo.gif
```

Animation is driven by `useCurrentFrame()` and `interpolate()` only — CSS
`transition` and `animation` do not render. Keyframes stay inline in `style`
props so they remain editable in the Studio.

## Facts on screen

The film states numbers (397 tests, ten agents, a three-day cadence, the
5–8 °C / 6–8 °C drift). They are taken from the root `README.md` and
`.github/workflows/publish.yml`; if those change, the affected scene has to be
re-rendered rather than quietly left wrong. That is the same rule the engine
applies to its own articles.

## Sound

The film ships silent. To score it, drop an mp3 at `public/score.mp3` and add
an `<Audio>` to `src/ContentFactoryPromo.tsx`.
