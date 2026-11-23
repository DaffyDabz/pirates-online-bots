# pbots (11-22): the low-memory bot game. walker.py appends this file to its MUTE page when BOT_PRC names it, so
# every line here wins over config/general.prc and the game_options page (MUTE is re-applied after every load).
# Software renderer: no GPU driver, no graphics memory. The game still gets a real (tiny, hidden) window, which
# PiratesBase needs (getPointer, requestProperties). m_measure.py's run() then stops the window drawing at all.
load-display p3tinydisplay
aux-display p3tinydisplay
# Every texture load through the TexturePool reads this one 8x8 picture instead of the real file: the models keep
# their texture slots (code that asks a texture its size still gets one), the picture bytes are gone.
fake-texture-image /c/Dev/Toontown/pirates-harness/pbot/prc/fake.png
compressed-textures 0
model-cache-textures 0
# The game's own lowest options (PiratesBase reads these at init).
want-water-reflection 0
want-water-reflection-show-through-only 0
want-water-reflect-all 0
want-avatar-shadows 0
texture-scale 0.125
# Vertex-data paging (max-resident-vertex-data...) lives in strip-paging.prc: MEAS1 (01:02) died at the avatar pick
# with "Assertion failed: _contexts == nullptr (geomVertexArrayData.cxx:279)" with it on; tried apart.
