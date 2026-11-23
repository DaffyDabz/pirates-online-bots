# pbots (11-22): strip.prc plus vertex-data paging: 32 MB stays resident, the rest is kept compressed in RAM (never
# paged to disk: C: is a QLC SSD). MEAS1 (01:02) died at the avatar pick with this on ("Assertion failed:
# _contexts == nullptr, geomVertexArrayData.cxx:279"); kept apart until a run proves it safe.
load-display p3tinydisplay
aux-display p3tinydisplay
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
