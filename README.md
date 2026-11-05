# Worm Horde

A browser test of a horde of worms that climb walls and never stop coming for you. You're a glowing orb. It's a test of how the worms look and behave, not a game yet.

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
| C | Third or first person |
| V | Show the dots and strings under the worms |
| L | Lights on or off |
| R | Respawn the worms |

Press 0 at least once. One worm crossing the room to reach you is the best test of the behaviour.

## How it works

- **Dots on strings:** each worm is 12 dots moved with Verlet integration and held together by distance constraints.
- **Baked distance field:** the level is baked into a 3D grid at load, so a dot checks for walls with one lookup. Worm collision and the camera both use it.
- **Spatial hash:** a grid finds nearby dots for worm-on-worm collision without comparing every pair.
- **GPU tubes:** one instanced tube mesh, bent in the vertex shader from a texture of dot positions.
- **Steering:** every worm drives straight at you, climbing whatever is in the way. Nothing distracts it, a blast throws it but doesn't slow it, and it never stops pushing once it reaches you.

To change how they behave, start with these constants in `index.html`: `DRIVE` (crawl strength), `WRITHE` (squirming inside a pile) and `AIM_NEAR` (the distance where worms stop fanning out and aim right at you).

## Speed

On a laptop with a Ryzen 5 PRO 7530U and integrated graphics, 500 and 1,000 worms have held 60 FPS in good runs. The same code has also dropped to 36-60 FPS at 500 and 27-44 FPS at 1,000, and the cause of that swing hasn't been found.

## Tests

`python3 check.py SCREENSHOT_DIR` drives the page with real key presses and clicks in headless Chromium and Firefox, prints PASS or FAIL for each check, and saves screenshots. It needs Python [Playwright](https://playwright.dev/python/) with both browsers installed.

Touch controls exist but haven't been tested.

## Credits

Uses [three.js](https://threejs.org) r158 (MIT licence, Copyright 2010-2023 Three.js Authors), included in `vendor/`. Fonts come from Google Fonts and fall back to system fonts offline.
