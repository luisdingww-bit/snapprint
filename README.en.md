# SnapPrint · 咔印3D

> Turn a photo into a **directly 3D-printable** model.
> Open source · Chinese-friendly · Apache-2.0 (commercial-friendly).

![license](https://img.shields.io/badge/license-Apache--2.0-green) ![mode](https://img.shields.io/badge/mode-Offline%20Relief%20%7C%20Hunyuan3D%20%7C%20TripoSR-blue) [![demo](https://img.shields.io/badge/online%20demo-snapprint--3d.surge.sh-ff5a3c)](https://snapprint-3d.surge.sh)

**🌐 Public Online Demo (no install): <https://snapprint-3d.surge.sh>** — a pure browser build with five modes (photo relief / 2D outline extrude / real 3D geometry / model import / 3DGS Gaussian splatting) + a 33-model library + slice-ready presets. Everything runs locally; your files never leave the browser.

---

## The problem it solves

There are already many "image-to-3D" open-source projects (TripoSR, InstantMesh, Wonder3D, Hunyuan3D…), but most stop at **emitting a bare mesh**. People who actually want to 3D-print still face a pile of friction:

- Non-watertight mesh → slicer errors
- Wrong units / wrong orientation → wrong size, extra supports
- No color → single-color prints only
- Hard environment / needs a GPU → ordinary users can't run it

**SnapPrint's differentiation: we don't compete on "whose 3D is the most general" — we finish the last mile from photo → printable product.**

## Core differentiation

| Dimension | Most image-to-3D projects | SnapPrint |
|-----------|---------------------------|-----------|
| **Focus** | General 3D generation | Vertical: **3D printing** (figures / toys / relief signage) |
| **Output** | Bare mesh | **Watertight, sliceable, millimeter-scaled, colored** |
| **Out-of-box** | Often needs GPU + complex env | Built-in **offline relief mode**, zero model deps, runs on CPU |
| **Friendliness** | Mostly English | **Chinese Web UI + Chinese docs + locally downloadable weights** |
| **License** | Many "non-commercial" | **Apache-2.0 (commercial-friendly)** |

## Features

- 🖼️ **Upload a photo → one-click generate**, entirely in the browser; parameters (size / base / relief height) tunable in real time
- 🧊 **Offline relief mode**: photo brightness → colored relief signage; zero deps, guaranteed to run
- 🤖 **AI mode (pluggable)**: a unified interface to Hunyuan3D / TripoSR and other open weights for more volumetric results
- 🔧 **Print-grade post-processing**: auto watertight repair, decimation, orientation, millimeter scaling
- 📦 **Multi-format export**: `OBJ` (geometry, all slicers) / `PLY` (vertex color) / `3MF` (color + print metadata)
- ⏳ **Async task queue**: long AI jobs return a `task_id` immediately; the UI polls a staged progress bar (decode → generate → post-process → export)
- 🖨️ **Slice-ready presets**: per common printers (Bambu / Creality / Prusa / Elegoo / Anycubic) + PLA/PETG/TPU, auto-recommending layer height, infill, supports and Brim from geometry; one-click export of a PrusaSlicer / OrcaSlicer-compatible `.ini` (built into the online Demo)
- 🦖 **Model Zoo**: base models Hunyuan3D-2 / TripoSR plus community-finetuned verticals (figure / jewelry / e-commerce); bring-your-own weights, plug-and-play
- 📦 **Batch generation**: `POST /api/batch` submits many images at once, each as its own async task
- 🔐 **API Key auth + rate limit**: for intranet / small-team deploys, set `SNAPRINT_API_KEY` and `SNAPRINT_RATE_LIMIT` to prevent abuse
- 🌍 **Multilingual**: one click on the top-right of the Web UI switches Chinese / English
- 🌐 **Chinese UI & docs** for domestic 3D-printing enthusiasts and creators

## Quick start (3 ways)

### Option 1: Start script (recommended for beginners)
```bash
# Any platform (after `pip install -r requirements.txt`)
python scripts/start_backend.py
# or a custom port
PORT=8080 python scripts/start_backend.py
```
Open http://localhost:8000 (don't want to self-host? Use the [Online Demo](https://snapprint-3d.surge.sh))

### Option 2: Docker
```bash
docker compose up --build
```

### Option 3: Manual
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

> The **offline relief mode** is the default — no GPU, no model weights to download.

## Enable AI mode (optional)

For a more volumetric "photo → real 3D" result, place open-source weights + inference code under `models/` and follow `docs/部署.md` to wire up Hunyuan3D or TripoSR. SnapPrint only defines a unified interface and is not tied to any single provider.

## Project structure

```
snapprint/
├── app/
│   ├── main.py          # FastAPI Web backend
│   ├── pipeline.py       # main pipeline entry run()
│   ├── advisor.py        # printability / support-advice analysis
│   ├── backends.py       # offline relief + AI-mode adapter layer
│   ├── postprocess.py    # watertight/decimate/orient/scale/export (the moat)
│   └── config.py         # default params (millimeter-level) + Model Zoo
├── frontend/index.html   # Chinese Web UI (zero build)
├── web/                  # pure-browser build (surge-hosted): 5 modes + library + presets
├── blender/SnapPrintBlender/  # Blender add-on (calls local backend)
├── comfyui/SnapPrintNode/     # ComfyUI custom nodes
├── scripts/              # start scripts
├── docs/                 # deploy / contribute / roadmap
├── outputs/              # generated 3D files
└── Dockerfile / docker-compose.yml
```

## Integrations: Blender add-on / ComfyUI nodes

SnapPrint exposes "photo → printable 3D" as a capability embeddable in other tools. The hub is the **local backend** (`python scripts/start_backend.py` → `http://localhost:8000`):

| Endpoint | Description |
|---|---|
| `POST /api/generate_async` | Submit generation, returns `task_id` immediately |
| `GET  /api/tasks/{id}` | Poll status / staged progress / result (with download links) |
| `POST /api/batch` | Batch generation, multiple files → list of `task_id`s |
| `POST /api/analyze` | Upload an image or mesh (stl/obj/ply/3mf) → printability / support-advice JSON |
| `GET  /api/models` | List the Model Zoo (with local-weight availability probe) |

**Security (intranet / small teams):** once `SNAPRINT_API_KEY` is set, the generate / analyze / batch endpoints require an `X-API-Key` header; `SNAPRINT_RATE_LIMIT=N` enables a per-client N-requests-per-minute limit. With neither set, everything is open (good for local / public Demo).

### Blender add-on
1. Copy the `blender/SnapPrintBlender/` folder into Blender's `scripts/addons/` directory;
2. Edit → Preferences → Add-ons → search `SnapPrint` → enable;
3. The **SnapPrint** panel appears in the sidebar: enter the backend URL, pick an image and mode, click "从图片生成浮雕 / Generate from image" to auto-generate and import the mesh; select a mesh and click "分析可打印性 / Analyze" to see layer height, infill, supports (type/density/threshold) and orientation advice.

### ComfyUI nodes
1. Place the `comfyui/SnapPrintNode/` folder into ComfyUI's `custom_nodes/` directory and restart ComfyUI;
2. Search `SnapPrint` to find **SnapPrint 生成 (图片→3D)** and **SnapPrint 分析 (可打印性)**;
3. The former takes `IMAGE` and outputs a mesh file path (chainable to later 3D nodes); the latter outputs a support/slice-advice JSON.

> All integrations share one geometry convention (overhang threshold 45°, support density/type, Brim, layer height/infill) — consistent with the Web slice-preset panel.

## Roadmap

See [docs/路线图.md](docs/路线图.md). v0.2 (async queue / public Demo / slice presets), v0.3 (auto support advice / Blender add-on / ComfyUI nodes) and v0.4 (Model Zoo / batch + API-Key rate limit / multilingual docs) are all complete ✅.

## License

[Apache-2.0](LICENSE) — commercial-friendly; contributions and integrations welcome.

---

⭐ If you find this project useful, a Star, Issue, or PR is appreciated. Let's make "photo → figure" easy for everyone.
