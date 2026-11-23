# pbots (11-22): strip-gl.prc plus vertex-data paging: 32 MB of vertex data stays resident, the rest is kept
# compressed in RAM (never paged to disk: C: is a QLC SSD). The two tinydisplay runs died on a vertex-buffer
# assertion at the avatar pick; with pandagl and the window off from the chooser (nothing is ever uploaded) this
# is the safe way to try it.
fake-texture-image /c/Dev/Toontown/pirates-harness/pbot/prc/fake.png
compressed-textures 0
model-cache-textures 0
want-water-reflection 0
want-water-reflection-show-through-only 0
want-water-reflect-all 0
want-avatar-shadows 0
texture-scale 0.125
max-resident-vertex-data 33554432
max-compressed-vertex-data -1
max-disk-vertex-data 0
vertex-data-compression-level 1
