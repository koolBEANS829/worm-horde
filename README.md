# Worm Horde

A browser test of a horde of worms that climb walls and never stop coming for you. You can be the glowing orb they're after, the whole horde, or one worm in it. It's a test of how the worms look and behave, not a game yet.

Inspired by [this YouTube short](https://youtube.com/shorts/HJas6mdFDqI) about a horror-game worm enemy.

## Run it

Open `index.html` in a browser with WebGL 2. There's nothing to install and no server to start.

## Controls

| Key | Does |
|---|---|
| Click | Become the orb, then blast where the arrow points |
| WASD, mouse | Move and look |
| Shift, Space | Run, jump |
| 0 to 5 | Worm count: 1, 100, 500, 1000, 2000, 5000 |
| H | Be the horde, or back to the orb |
| B | Be a worm, or back to the orb |
| F | As the horde or a worm: the worms chase the orb or follow you |
| T | Dials: tune the worms while you play |
| C | Third or first person, as the orb |
| V | Show the dots and strings under the worms |
| L | Lights on or off |
| R | Respawn the worms |

Press 0 at least once. One worm crossing the room to reach you is the best test of the behaviour.

## Join the worms

While you're with the worms, the orb walks a set route on its own and you can't blast.

- **Be the horde (H):** the camera floats behind the worms' average position, and WASD steers a glowing dot that moves just like a worm. The horde chases the dot and strings out behind it. When the dot stops, they stop on arriving and spread out flat. Shift hurries. The horde starts out chasing the orb: pushing takes it back, and F sends it off again.
- **Be a worm (B):** you crawl as the gold worm, and climb walls by crawling into them. Shift hurries. Press F to switch the horde between chasing the orb and following you. They stop around you too, and can't push you, so you can always crawl away.

Worms only bunch up on the orb.

## Dials

Press T to open six sliders. They change the worms as you drag them, and your browser remembers them until you press Reset. The mouse is free while they're open, so drag the view to turn. WASD still works.

| Dial | Changes |
|---|---|
| Dot speed | How fast the dot moves, and your worm too |
| Worm speed | How fast every other worm crawls |
| Stream stretch | How far worms' speeds differ while chasing the dot, so how long the stream gets |
| Stop spacing | How spread out they lie once stopped |
| Wake delay | How long far-off worms wait before setting off when you push |
| Rest squirm | How much they wriggle once stopped |

## How it works

- **Dots on strings:** each worm is 12 dots moved with Verlet integration and held together by distance constraints.
- **Baked distance field:** the level is baked into a 3D grid at load, so a dot checks for walls with one lookup. Worm collision and the camera both use it.
- **Spatial hash:** a grid finds nearby dots for worm-on-worm collision without comparing every pair.
- **GPU tubes:** one instanced tube mesh, bent in the vertex shader from a texture of dot positions.
- **Steering:** every worm drives straight at you, climbing whatever is in the way. Nothing distracts it, a blast throws it but doesn't slow it, and it never stops pushing once it reaches you.

- **The dot:** it's the head of a worm with its body hidden, so it moves exactly like your worm does. When a push starts, the worms out front get the fast paces and the ones at the back get the slow ones, which stretches the horde into a stream.
- **Stopping:** worms stop within a set distance of the dot, and that distance grows with each worm that stops, so they spread out flat. Pushing wakes them from the dot outward, so a tap barely disturbs them.

To change how they behave, start with these constants in `index.html`: `DRIVE` (crawl strength), `WRITHE` (squirming inside a pile) and `AIM_NEAR` (the distance where worms stop fanning out and aim right at you). The dot also uses `DOT_WIDTH` and `STOP_R`. `DIALS` sets each dial's starting value and range, and `YOU_RUN` sets how much Shift adds.

`DOT_CONTROL = false` brings back an older horde control, where WASD moves an invisible spot and holding it pours out three arms. Its settings start with `SPOT_`, `ARM_` and `HOLD_`, and `check_views.py` switches to its checks automatically.

## Speed

On a laptop with a Ryzen 5 PRO 7530U and integrated graphics, 500 and 1,000 worms have held 60 FPS in good runs. The same code has also dropped to 36-60 FPS at 500 and 27-44 FPS at 1,000, and the cause of that swing hasn't been found.

## Tests

`python3 check.py SCREENSHOT_DIR` drives the page with real key presses and clicks in headless Chromium and Firefox, prints PASS or FAIL for each check, and saves screenshots. It needs Python [Playwright](https://playwright.dev/python/) with both browsers installed.

`python3 check_views.py SCREENSHOT_DIR` does the same for the horde and worm views. It takes about 5 minutes, or name parts after the directory to run only those.

Touch controls exist but haven't been tested.

## Credits

Uses [three.js](https://threejs.org) r158 (MIT licence, Copyright 2010-2023 Three.js Authors), included in `vendor/`. Fonts come from Google Fonts and fall back to system fonts offline.
