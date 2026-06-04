# Game Images

Create and edit game images: **create** (text-to-image), **adjust**, **tile**, **texture maps**, plus AI **zoom**, **extend** (outpaint), and **manipulate** (inpaint) with OpenAI, Gemini (Nano Banana), MiniMax, and Fal.ai providers.

## Setup

```bash
pip install -e .
```

## API keys

**Web UI:** open **Settings** (gear icon, top right) to add, change, or remove API keys. Keys are stored in `settings.json` next to your image library (plain text on disk; file permissions are restricted when possible).

**Environment variables** override stored keys (useful for CI or shells):

- **OpenAI**: API key and/or **Sign in with OpenAI** (OAuth). In Settings, choose **Use for OpenAI requests**: Automatic (prefer API key), API key only, or OAuth only. Environment variables apply to the selected type when set. OAuth callback uses `http://localhost:1455/auth/callback` by default.
- **Gemini** (Nano Banana image models): `GEMINI_API_KEY` or `GOOGLE_API_KEY`
- **MiniMax** (image generation): `MINIMAX_API_KEY`
- **Fal**: `FAL_KEY`

Do not commit `.env`, `settings.json`, or keys to the repo.

### Discovering models

In **Settings**, click **Discover models** once (or after adding keys). Game Images probes each configured provider and saves an **available models** catalog in `settings.json`. Create and Edit model dropdowns then only list models your keys can use. Before the first discovery run, sensible defaults are shown.

### OpenAI image models

The default is **`gpt-image-1.5`**. OpenAI is retiring **DALL·E 2 / DALL·E 3** on the Images API; if you pick a legacy DALL·E model and the API rejects it, Create automatically retries with GPT Image 1.5.

Override the default:

```bash
export OPENAI_IMAGE_MODEL=gpt-image-1.5
```

Other supported IDs: `gpt-image-1`, `gpt-image-1-mini`, and legacy `dall-e-2` / `dall-e-3` where still available.

## CLI

**Create** (text-to-image):

```bash
game-images create --prompt "Seamless dark asphalt texture" --width 1024 --height 1024 --provider openai -o base.png
```

**Adjust** (brightness, contrast, blur, rotate, flip, resize — no API key):

```bash
game-images adjust base.png --brightness 1.1 --contrast 1.2 -o tuned.png
game-images adjust base.png --resize-scale 0.5 -o half.png
game-images adjust base.png --width 512 --height 512 -o sized.png
```

**Tile** (seamless helpers):

```bash
game-images tile tuned.png --mode offset_x -o tiled.png
```

**Maps** (bump, normal, roughness, ao, height from albedo):

```bash
game-images maps tuned.png --type bump -o asphalt.bump.png
```

**Zoom** — zoom out (uniform outpaint on all sides) or zoom in (crop + optional AI enhance):

```bash
game-images zoom image.png --mode out --factor 1.5 --prompt "Continue forest and sky" --provider openai -o wider.png
game-images zoom image.png --mode in --factor 2 --enhance --prompt "Sharper pixel art, same style" -o tight.png
```

**Extend** (outpainting) — grow the image in one or more directions:

```bash
game-images extend image.png --direction north --amount 256 --prompt "Seamless sky" --provider openai -o out.png
```

Directions: `north`, `south`, `east`, `west`, or `all` (comma-separated for multiple). Use 128–256 px per step for cleaner borders.

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

Then open http://127.0.0.1:8000 . Use the **gear icon** (top right) to set API keys and run **Discover models** before Create / Zoom / Extend / Manipulate.

**Library → Projects → Edit → Create** flow:

1. **Library** — browse, import, and click a thumbnail to set the **active image**. Filter by **asset type** or **project**; badges show type and project membership.
2. **Projects** — group library assets for a game or level (many-to-many). Add assets from the library; open them in Edit from the project detail view.
3. **Edit** — tools shown depend on the asset’s **type** (capabilities). **Game asset workflows** suggest step sequences for textures, environments, and sprites.
4. **Create** — text-to-image without an existing source; the result becomes the active image.

### Asset types (pluggable)

Built-in types register capabilities used to show or hide Edit tools:

| Type | Extends | Extra capabilities |
|------|---------|-------------------|
| Image | — | All standard image edit tools |
| Texture | Image | Maps, seamless 2×2 preview, maps bundle |
| Skydome | Image | Equirectangular interior preview, lightmap stub |
| Background | Image | Same as Image today |

Import or assign a type in Library. Results inherit the source asset’s type when saved.

**Texture tools (Edit → Maps):** **Generate maps bundle** saves normal and roughness maps as linked library assets. When a project is open, derivatives are added with roles (`normal`, `roughness`) and `source_id` links back to the albedo.

**Preview modes** (Preview panel, when the asset type supports them):

| Mode | Asset types | Purpose |
|------|-------------|---------|
| Flat | All | Standard preview |
| Seamless 2×2 | Texture | Tile continuity check |
| Equirectangular (interior) | Skydome | Inside-sphere horizon preview |

**Skydome:** lightmap export is stubbed (`501`) until implemented.

To add a type in code, register an `AssetTypeDefinition` in `game_images/asset_types/builtin.py` (entry points planned for later).

### Projects

- **Projects page**: create projects, view assets grouped by type, add/remove library members, assign **roles** (albedo, normal, roughness, skydome_main, …).
- **Library**: filter by project; each thumbnail shows project chips.
- Derivative maps show **← from** parent filename when `source_id` is set.
- Deleting a project removes membership only — assets stay in the library.

**Zoom** — zoom out uses uniform outpaint (same idea as Extend on all sides). Zoom in crops using the dashed Preview box; optional **Enhance** runs inpaint on the crop without a mask.

Results from Create and Edit are saved to the library automatically.

### Image library

The Web UI uses a local **image library** instead of one-off file uploads. Images are stored on disk and indexed with metadata (prompt, tags, dimensions).

- **Library**: Browse and select images, or **Import** new ones. **Rename** updates the display filename (double-click a name in the grid, or use Rename in the library toolbar or active-image bar). Selection is restored on reload when possible.
- **Edit → Manipulate**: Select a mask from the library, create one in the mask editor (optionally save to library), or upload a file.
- **Prepare (shift)**: In-memory prep for Extend; not saved until a later operation writes to the library.

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
