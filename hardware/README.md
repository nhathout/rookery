# hardware/

Source and output for the printed enclosure. Prose lives in
[`docs/hardware/`](../docs/hardware/).

| | |
|---|---|
| [`generate.py`](generate.py) | The penguin. Builds all six parts from a pixel map and a page of named dimensions, then measures what it built |
| [`stl/`](stl/) | Its output: six STLs and two per-colour 3MF plates, committed so you can print without installing anything |

Nothing in `stl/` is hand-edited. To change a dimension, edit the constants at
the top of `generate.py` and re-run it:

```bash
pip install trimesh manifold3d shapely numpy
python3 generate.py
```

Parameters, flags and the self-check list:
[docs/hardware/enclosure.md](../docs/hardware/enclosure.md).

Everything else about the hardware:
[docs/hardware/README.md](../docs/hardware/README.md) — parts, pinout, wiring,
printing, assembly.
