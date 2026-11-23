# pbots (11-22): strip.prc WITHOUT the software renderer. MEAS1 (paging on) and MEAS2 (paging off) both died at the
# avatar pick on "Assertion failed: _contexts == nullptr (geomVertexArrayData.cxx:279)" with load-display p3tinydisplay:
# the game's vertex buffers are freed while the tiny GSG still holds a prepared context for them, something pandagl
# never does in the hundreds of hidden runs so far. So the GPU stays (pandagl), everything else is stripped:
# stand-in 8x8 textures, no reflections or shadows, 1/8 texture scale.
fake-texture-image /c/Dev/Toontown/pirates-harness/pbot/prc/fake.png
compressed-textures 0
model-cache-textures 0
want-water-reflection 0
want-water-reflection-show-through-only 0
want-water-reflect-all 0
want-avatar-shadows 0
texture-scale 0.125
