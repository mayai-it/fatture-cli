# Social preview image

GitHub renders the configured image at 1280×640 in link unfurls (Twitter/X,
Slack, LinkedIn, etc.) and at the top of the repo when someone shares the URL.

## Source

`docs/social-preview.svg` — vector source, edit this when the wordmark or
tagline changes.

## Upload procedure (manual — GitHub has no API for this)

1. Convert SVG to PNG at exactly **1280×640**.

   With ImageMagick:

   ```bash
   magick -background none -density 200 \
     -resize 1280x640 \
     docs/social-preview.svg docs/social-preview.png
   ```

   With `rsvg-convert`:

   ```bash
   rsvg-convert -w 1280 -h 640 docs/social-preview.svg -o docs/social-preview.png
   ```

   With Inkscape:

   ```bash
   inkscape docs/social-preview.svg --export-type=png \
     --export-width=1280 --export-height=640 \
     --export-filename=docs/social-preview.png
   ```

2. Verify dimensions:

   ```bash
   file docs/social-preview.png   # expect: PNG image data, 1280 x 640
   ```

3. Open https://github.com/mayai-it/fatture-cli/settings → scroll to
   **Social preview** → **Upload an image** → drop `docs/social-preview.png`.

4. Test the unfurl by pasting the repo URL into a Slack or X draft. GitHub's
   CDN may cache the previous image for a few minutes.

## Design notes

- Background: `#08091B` (matches mayai.it body color).
- Wordmark in a monospaced sans, no gradients, no glow effects.
- The four-pointed star is a placeholder for the MayAI mark. Replace with the
  canonical SVG when available — the placement and 80×80 bounding box should
  stay the same so the layout grid still works.
- 1280×640 is the GitHub spec; the same image works for X / LinkedIn / Slack
  unfurls without re-cropping.
