"""Turn the "Brain Areas" glTF model into the points of the landing-page brain.

Model: "Brain Areas" by Versal, CC BY 4.0
(https://sketchfab.com/3d-models/brain-areas-d64608a3978b47d8a39c5a15795ca8c4).
The model itself is not kept in the repository: download it from Sketchfab (glTF) and run

    python scripts/brain_points.py path/to/scene.gltf

It samples points on the surface of every part (more on larger areas), turns them so the brain
is seen from the left with the front to the right, scales them to [-1, 1] and writes them,
rounded, to landingpage/brain-points.js. No dependencies beyond the standard library.
"""

import json
import random
import struct
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "landingpage" / "brain-points.js"
COUNT = 4200
SEED = 7


def read_accessor(gltf, binary, index):
    accessor = gltf["accessors"][index]
    view = gltf["bufferViews"][accessor["bufferView"]]
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3}[accessor["type"]]
    kind, size = {5126: ("f", 4), 5125: ("I", 4), 5123: ("H", 2)}[accessor["componentType"]]
    stride = view.get("byteStride", size * width)
    values = []
    for i in range(accessor["count"]):
        start = offset + i * stride
        values.append(struct.unpack_from("<" + kind * width, binary, start))
    return values


def matmul(a, b):
    # 4x4 column-major (glTF) matrices
    return [sum(a[r + 4 * k] * b[k + 4 * c] for k in range(4)) for c in range(4) for r in range(4)]


def apply(m, p):
    x, y, z = p
    return (
        m[0] * x + m[4] * y + m[8] * z + m[12],
        m[1] * x + m[5] * y + m[9] * z + m[13],
        m[2] * x + m[6] * y + m[10] * z + m[14],
    )


IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def meshes_with_matrix(gltf):
    """(mesh index, world matrix) for every node with a mesh."""
    found = []

    def walk(index, parent):
        node = gltf["nodes"][index]
        matrix = matmul(parent, node.get("matrix", IDENTITY))
        if "mesh" in node:
            found.append((node["mesh"], matrix, node.get("name", "")))
        for child in node.get("children", []):
            walk(child, matrix)

    for root in gltf["scenes"][gltf.get("scene", 0)]["nodes"]:
        walk(root, IDENTITY)
    return found


def area(a, b, c):
    ux, uy, uz = (b[i] - a[i] for i in range(3))
    vx, vy, vz = (c[i] - a[i] for i in range(3))
    cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    return 0.5 * (cx * cx + cy * cy + cz * cz) ** 0.5


def main(path):
    gltf_path = Path(path)
    gltf = json.loads(gltf_path.read_text(encoding="utf-8"))
    binary = (gltf_path.parent / gltf["buffers"][0]["uri"]).read_bytes()
    triangles = []  # (a, b, c, part, area)
    for part, (mesh_index, matrix, name) in enumerate(meshes_with_matrix(gltf)):
        for primitive in gltf["meshes"][mesh_index]["primitives"]:
            positions = [apply(matrix, p) for p in read_accessor(gltf, binary, primitive["attributes"]["POSITION"])]
            indices = [i[0] for i in read_accessor(gltf, binary, primitive["indices"])]
            for t in range(0, len(indices), 3):
                a, b, c = (positions[indices[t + k]] for k in range(3))
                triangles.append((a, b, c, part, area(a, b, c)))
        print(f"part {part}: {name}")

    rng = random.Random(SEED)
    weights = [t[4] for t in triangles]
    chosen = rng.choices(triangles, weights=weights, k=COUNT)
    points = []
    for a, b, c, part, _ in chosen:
        r1, r2 = rng.random(), rng.random()
        if r1 + r2 > 1:
            r1, r2 = 1 - r1, 1 - r2
        points.append(tuple(a[i] + r1 * (b[i] - a[i]) + r2 * (c[i] - a[i]) for i in range(3)) + (part,))

    xs, ys, zs = ([p[i] for p in points] for i in range(3))
    print("bounds x", min(xs), max(xs), "y", min(ys), max(ys), "z", min(zs), max(zs))
    # Seen from the left: the model's front-back axis becomes x (front to the right), its up
    # axis becomes y (down positive, as on the canvas) and its left-right axis becomes depth.
    centre = [(min(v) + max(v)) / 2 for v in (xs, ys, zs)]
    span = max(max(v) - min(v) for v in (xs, ys, zs)) / 2
    mapped = [
        (
            (p[2] - centre[2]) / span,
            -(p[1] - centre[1]) / span,
            (p[0] - centre[0]) / span,
            p[3],
        )
        for p in points
    ]
    flat = []
    for x, y, z, part in mapped:
        flat += [round(x, 3), round(y, 3), round(z, 3), part]
    OUT.write_text(
        "// Points sampled from \"Brain Areas\" by Versal (CC BY 4.0), made by scripts/brain_points.py.\n"
        "// x, y, z in [-1, 1] (front to the right, y down) and the part of the brain, repeated.\n"
        "window.BRAIN_POINTS = " + json.dumps(flat, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    print(f"{len(mapped)} points -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "scene.gltf")
