# Game Images

Create and edit game images: **create** (text-to-image), **adjust**, **tile**, **texture maps**, plus AI **extend** (outpaint) and **manipulate** (inpaint) with OpenAI and Fal.ai providers.

## Setup

```bash
pip install -e .
```

## API keys (environment)

- **OpenAI**: set `OPENAI_API_KEY`
- **Fal (Gemini)**: set `FAL_KEY`

Do not commit `.env` or keys to the repo.

### Using a different OpenAI image model

The default model is `dall-e-2` (works on all accounts). To use newer GPT image models when your account has access:

```bash
export OPENAI_IMAGE_MODEL=gpt-image-1.5
```

Other options: `gpt-image-1`, `gpt-image-1-mini`. These support non-square images, larger sizes, and often better quality. If you get an error like “Value must be 'dall-e-2'”, your account or region only has DALL·E 2; keep the default or omit `OPENAI_IMAGE_MODEL`.

## CLI

**Create** (text-to-image):

```bash
game-images create --prompt "Seamless dark asphalt texture" --width 1024 --height 1024 --provider openai -o base.png
```

**Adjust** (brightness, contrast, blur, rotate, flip — no API key):

```bash
game-images adjust base.png --brightness 1.1 --contrast 1.2 -o tuned.png
```

**Tile** (seamless helpers):

```bash
game-images tile tuned.png --mode offset_x -o tiled.png
```

**Maps** (bump, normal, roughness, ao, height from albedo):

```bash
game-images maps tuned.png --type bump -o asphalt.bump.png
```

**Extend** (outpainting) — grow the image in one or more directions:

```bash
game-images extend image.png --direction north --amount 256 --prompt "Seamless sky" --provider openai -o out.png
```

Directions: `north`, `south`, `east`, `west` (comma-separated for multiple).

**Manipulate** (inpainting) — edit the image (or a masked region) with a prompt:

```bash
game-images manipulate image.png --prompt "Add a red hat" --provider fal -o out.png
```

Optional mask (PNG; transparent = area to edit):

```bash
game-images manipulate image.png --prompt "Add a hat" --mask mask.png -o out.png
```

## Web UI

Run the local web interface:

```bash
game-images serve
```

Then open http://127.0.0.1:8000 . Use **Create** for new images, **Adjust** / **Tile** / **Maps** for local processing, and **Extend** / **Manipulate** for AI edits. Results are saved to the library automatically.

### Image library

The Web UI uses a local **image library** instead of one-off file uploads. Images are stored on disk and indexed with metadata (prompt, tags, dimensions).

- **Image area**: Browse and select images from the library, or **Import** new ones. Shifted images are not saved until you add them.
- **Manipulate**: Select a mask from the library, create one in the mask editor (optionally save to library), or upload a file.
- **Results**: Generated images are automatically added to the library with prompt and source metadata.

**Library location**: Set `GAME_IMAGES_LIBRARY` to a directory path. Default: `~/.local/share/game-images` (Linux/macOS) or `%LOCALAPPDATA%/game-images` (Windows). Fallback: `./library/` in the project root.

Alternatively, from the project root:

```bash
uvicorn web.app:app --host 127.0.0.1 --port 8000
```

(Requires `pip install -e .` so that `game_images` is importable.)

## Python API

```python
from game_images import extend_image, manipulate_image

# Extend north by 128px
out = extend_image(
    image_bytes,
    directions=["north"],
    amount_px=128,
    prompt="Seamless sky and trees",
    provider_name="openai",
)

# Edit with a prompt
out = manipulate_image(image_bytes, "Add a red hat", provider_name="fal")
```
