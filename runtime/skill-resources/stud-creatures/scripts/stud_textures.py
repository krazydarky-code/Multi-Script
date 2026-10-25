"""Make your own stud textures for Roblox (a colour map and a normal map, one stud per tile), so you do not depend on
anyone else's uploads:

    blender -b --factory-startup -P scripts/stud_textures.py -- OUT_FOLDER [size]

Writes stud_color.png (near white: Roblox tints it with each part's Color) and stud_normal.png. Upload both in
Studio (Asset Manager > Images or the Creator Hub) and put their ids in the setup script (COLOR_MAP / NORMAL_MAP).
"""
import bpy, os, sys
import numpy as np

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
out = os.path.abspath(argv[0] if argv else 'textures')
size = int(argv[1]) if len(argv) > 1 else 256
os.makedirs(out, exist_ok=True)

xs = (np.arange(size) + 0.5) / size
X, Y = np.meshgrid(xs, xs)
d = np.maximum(np.abs(X - 0.5), np.abs(Y - 0.5))          # square distance from the cell centre
groove = np.clip((0.5 - d) / 0.045, 0, 1)                 # low groove at the cell border
stud = np.clip((0.31 - d) / 0.05, 0, 1)                   # raised square stud in the middle
height = 0.5 * groove + 0.5 * stud

# colour: almost white, a little darker in the groove and on the stud's lower edges
shade = 0.86 + 0.14 * groove
gy, gx = np.gradient(height)
shade = np.clip(shade - 0.25 * np.clip(gy, 0, None) * size / 8 + 0.1 * np.clip(-gy, 0, None) * size / 8, 0.6, 1.0)
col = np.stack([shade, shade, shade, np.ones_like(shade)], axis=-1)

# normal map (OpenGL style, +Y up) from the height field
strength = 6.0
nx = -gx * size / strength
ny = -gy * size / strength
nz = np.ones_like(nx)
n = np.stack([nx, ny, nz], axis=-1)
n /= np.linalg.norm(n, axis=-1, keepdims=True)
nor = np.concatenate([n * 0.5 + 0.5, np.ones_like(nz)[..., None]], axis=-1)


def save(name, rgba, linear):
    img = bpy.data.images.new(name, size, size, alpha=False, float_buffer=False)
    if linear:
        img.colorspace_settings.name = 'Non-Color'
    img.pixels.foreach_set(rgba.astype(np.float32).ravel())
    path = os.path.join(out, name + '.png')
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    print('wrote', path)


save('stud_color', col, False)
save('stud_normal', nor, True)
