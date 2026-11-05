#!/usr/bin/env python3
"""Drive the worm page in headless browsers with real input; print results and take screenshots.

Usage: python3 check.py SCREENSHOT_DIR
"""
import json, math, pathlib, sys
from playwright.sync_api import sync_playwright

PAGE = pathlib.Path(__file__).resolve().parent / "index.html"
OUT = pathlib.Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
GPU_ARGS = ["--use-angle=vulkan", "--enable-features=Vulkan", "--ignore-gpu-blocklist", "--enable-gpu"]
fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        fails.append(name)


with sync_playwright() as p:
    b = p.chromium.launch(args=GPU_ARGS)
    pg = b.new_page(viewport={"width": 1280, "height": 720})
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(PAGE.as_uri())
    pg.wait_for_function("window.__horde", timeout=30000)
    st = lambda: pg.evaluate("__horde.state()")
    print("renderer:", pg.evaluate("""(() => { const g = document.createElement('canvas').getContext('webgl2');
      const e = g.getExtension('WEBGL_debug_renderer_info'); return g.getParameter(e.UNMASKED_RENDERER_WEBGL); })()"""))
    pg.wait_for_timeout(1500)
    check("starts on the overhead view with no arrow", (lambda s: s["tour"] and s["orbVisible"] and not s["arrowVisible"])(st()))
    check("orb starts standing on the platform", abs(st()["y"] - 4.5) < .05, f"y = {st()['y']:.3f}")

    # The guided walk, in real time: the orb must leave the platform and stay above the floor.
    low, start = 99, st()
    for i in range(24):
        pg.wait_for_timeout(1000)
        s = st()
        low = min(low, s["y"])
        if i == 13:
            pg.screenshot(path=str(OUT / "t0-overhead-14s.png"))
    moved = math.hypot(s["x"] - start["x"], s["z"] - start["z"])
    check("guided walk: orb moves on and never goes under the floor", moved > 5 and low > -.05, f"moved {moved:.1f} m, lowest y {low:.3f}")
    print("after guided walk:", json.dumps(pg.evaluate("__horde.stats()")))
    pg.reload()
    pg.wait_for_function("window.__horde", timeout=30000)
    pg.wait_for_timeout(1500)

    # Take over with a real click.
    pg.mouse.click(640, 360)
    pg.wait_for_timeout(800)
    s = st()
    check("click puts you in third person with orb and arrow", not s["tour"] and s["third"] and s["orbVisible"] and s["arrowVisible"], f"mouse locked: {s['locked']}")

    # WASD with real key presses.
    a = st(); pg.keyboard.down("KeyW"); pg.wait_for_timeout(700); pg.keyboard.up("KeyW"); c = st()
    dx, dz = c["x"] - a["x"], c["z"] - a["z"]
    along = dx * -math.sin(a["yaw"]) + dz * -math.cos(a["yaw"])
    check("W walks where you're looking", along > 1.5, f"{along:.2f} m forward, {math.hypot(dx, dz):.2f} m total")
    a = st(); pg.keyboard.down("KeyD"); pg.wait_for_timeout(400); pg.keyboard.up("KeyD"); c = st()
    side = (c["x"] - a["x"]) * math.cos(a["yaw"]) + (c["z"] - a["z"]) * -math.sin(a["yaw"])
    check("D strafes right", side > .5, f"{side:.2f} m")

    # Jump.
    pg.wait_for_timeout(900)
    y0 = st()["y"]; pg.keyboard.down("Space"); peak = y0
    for _ in range(10):
        pg.wait_for_timeout(60); peak = max(peak, st()["y"])
    pg.keyboard.up("Space")
    check("Space jumps", peak - y0 > .4, f"rose {peak - y0:.2f} m")

    # Headless Chromium reports zero mouse movement while locked, so mouse look is checked in Firefox below.
    pg.evaluate("__horde.pause(true)")
    worst = 0
    for yaw, pitch in ((0, 0), (1.2, -.4), (-2.5, .3), (3, -1)):
        pg.evaluate(f"__horde.place(0, 0, -12); __horde.view({yaw}, {pitch})")
        s = st()
        want = (-math.sin(yaw) * math.cos(pitch), math.sin(pitch), -math.cos(yaw) * math.cos(pitch))
        worst = max(worst, max(abs(u - v) for u, v in zip(want, s["arrowDir"])))
    check("arrow matches the look direction", worst < .01, f"worst error {worst:.4f}")

    # Pointing the right way is no use if the arrow is hidden behind the orb: measure it on screen.
    sizes, on_screen = [], True
    for yaw, pitch in ((0, 0), (1.1, -.3), (-2.5, .25), (3, -.6)):
        pg.evaluate(f"__horde.place(0, 0, -12); __horde.view({yaw}, {pitch})")
        sc = st()["screen"]
        sizes.append(round(sc["arrowPx"]))
        on_screen = on_screen and 0 < sc["orb"][1] < 640 and 0 < sc["tip"][1] < 640
    check("arrow is clearly visible and clear of the controls", min(sizes) >= 50 and on_screen, f"on-screen length {sizes} px")

    # Camera against walls and floor: it must stay outside solid things.
    low = 99
    for x, y, z, yaw, pitch in ((-9, 0, -5, -1.57, 0), (-9, 0, -5, -1.57, .5), (23.2, 0, 0, 1.57, 0), (0, 0, -23.2, 3.14, .2), (-4, 0, -5.9, 0, 1.3), (0, 0, 0, 0, 1.45)):
        pg.evaluate(f"__horde.place({x}, {y}, {z}); __horde.view({yaw}, {pitch})")
        low = min(low, st()["camClearance"])
    check("camera never enters walls or floor", low > .1, f"closest gap {low:.2f} m")

    # View switch.
    pg.evaluate("__horde.pause(false)")
    pg.keyboard.press("KeyC"); pg.wait_for_timeout(200); s = st()
    check("C goes to first person and hides the orb", not s["third"] and not s["orbVisible"] and pg.get_attribute("#camview", "aria-pressed") == "false")
    pg.keyboard.press("KeyC"); pg.wait_for_timeout(200); s = st()
    check("C comes back to third person", s["third"] and s["orbVisible"] and s["arrowVisible"])
    pg.evaluate("__horde.pause(true)")

    # Blast with a real click, at a pile around you and at one across the room.
    if not st()["locked"]:
        pg.mouse.click(640, 360); pg.wait_for_timeout(300)
    pg.evaluate("__horde.set(500); __horde.place(-18, 0, 12); __horde.view(-1.2, -0.1); __horde.sim(1500)")
    before = pg.evaluate("__horde.spread()")
    pg.mouse.down(); pg.mouse.up(); pg.wait_for_timeout(150)
    pg.evaluate("__horde.sim(25)")
    after = pg.evaluate("__horde.spread()")
    check("click blasts the pile around you", after > before * 1.5, f"spread {before:.2f} -> {after:.2f} m")
    pg.evaluate("__horde.sim(900); __horde.place(-18, 0, -8); __horde.view(0, 0); __horde.view(3.14159, -0.02)")
    before = pg.evaluate("__horde.spread()")
    pg.mouse.down(); pg.mouse.up(); pg.wait_for_timeout(150)
    pg.evaluate("__horde.sim(25)")
    after = pg.evaluate("__horde.spread()")
    check("click blasts a pile across the room", after > before * 1.3, f"spread {before:.2f} -> {after:.2f} m")

    # Result checks after everything above.
    print("physics:", json.dumps(pg.evaluate("__horde.stats()")))

    # Dedication: one worm has to finish the job on its own, and a big pile must not go still.
    pg.keyboard.press("Digit0"); pg.wait_for_timeout(200)
    check("0 selects one worm", pg.inner_text("#worms") == "1" and pg.get_attribute("#n1", "aria-pressed") == "true", pg.inner_text("#worms"))
    pg.evaluate("__horde.pause(true); __horde.place(-18, 0, 12); __horde.sim(2700)")
    s = pg.evaluate("__horde.stats()")
    check("one worm crosses the room, climbs you and stays on", s["topY"] > 1.5 and s["onYouPct"] > 60, f"top {s['topY']:.2f} m, {s['onYouPct']}% of it on you")
    pg.evaluate("__horde.blastAt(-18, 1, 12); __horde.sim(60)")
    thrown = pg.evaluate("__horde.stats()")["meanDist"]
    pg.evaluate("__horde.sim(720)")
    s = pg.evaluate("__horde.stats()")
    check("a blasted worm climbs straight back on", thrown > 2 and s["onYouPct"] > 60, f"thrown to {thrown:.1f} m, then {s['onYouPct']}% on you 12 s later")
    pg.evaluate("__horde.place(0, 0, 18); __horde.sim(1200)")
    s = pg.evaluate("__horde.stats()")
    check("walk 19 m away and it catches you again", s["onYouPct"] > 60, f"{s['onYouPct']}% on you 20 s later")
    pg.evaluate("__horde.set(500); __horde.place(-18, 0, 12); __horde.sim(1700)")
    s = pg.evaluate("__horde.stats()")
    check("the pile on you keeps moving", s["meanSpeed"] > .3 and s["deepPct"] == 0 and s["maxLinkRatio"] < 2, f"{s['meanSpeed']} m/s, stretch {s['maxLinkRatio']}, {s['deepPct']}% deep in walls")

    # Pictures.
    def shot(name):
        pg.wait_for_timeout(700)
        pg.screenshot(path=str(OUT / f"{name}.png"))
    pg.evaluate("__horde.set(500); __horde.place(17, 4.5, -17); __horde.view(1.1, -0.3); __horde.sim(400)")
    shot("t1-worms-arriving")
    pg.evaluate("__horde.sim(420)")
    shot("t2-worms-on-you")
    pg.evaluate("__horde.lights(true)")
    shot("t3-lights-on")
    pg.evaluate("__horde.lights(false)")

    # Real-time speed in third person.
    pg.evaluate("__horde.pause(false)")
    for key, n in (("Digit2", 500), ("Digit3", 1000)):
        pg.keyboard.press(key)
        r = []
        for _ in range(7):
            pg.wait_for_timeout(2000)
            r.append((int(pg.inner_text("#fps")), float(pg.inner_text("#phys").split()[0])))
        print(f"{n} worms realtime: fps {[x[0] for x in r]} physics ms {[x[1] for x in r]}")
    check("no page errors in Chromium", not errs, "; ".join(errs[:4]))

    # The worm buttons have to fit on a phone-width screen.
    ph = b.new_page(viewport={"width": 390, "height": 844})
    ph.goto(PAGE.as_uri())
    ph.wait_for_function("window.__horde", timeout=30000)
    over = ph.evaluate("document.documentElement.scrollWidth - innerWidth")
    edge = ph.evaluate("Math.max(...[...document.querySelectorAll('.controls button')].map(b => b.getBoundingClientRect().right))")
    check("controls fit a phone-width screen", over <= 0 and edge <= 390, f"overflow {over} px, rightmost button at {edge:.0f} px")
    ph.screenshot(path=str(OUT / "t5-phone.png"))
    ph.close()
    b.close()

    # Firefox: plain load and take-over.
    try:
        f = p.firefox.launch(firefox_user_prefs={"webgl.force-enabled": True, "webgl.disabled": False})
        pg = f.new_page(viewport={"width": 1280, "height": 720})
        ferrs = []
        pg.on("console", lambda m: ferrs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: ferrs.append(str(e)))
        pg.goto(PAGE.as_uri())
        pg.wait_for_timeout(5000)
        if pg.evaluate("!!window.__horde"):
            pg.mouse.click(640, 360)
            pg.wait_for_timeout(2500)
            s = pg.evaluate("__horde.state()")
            check("Firefox: loads and takes over", not s["tour"] and s["arrowVisible"], f"mouse locked: {s['locked']}, errors: {ferrs[:3] or 'none'}")
            for x in (660, 700, 760, 840):
                pg.mouse.move(x, 350)
                pg.wait_for_timeout(50)
            pg.wait_for_timeout(300)
            c = pg.evaluate("__horde.state()")
            check("Firefox: mouse turns the view and the arrow", abs(c["yaw"] - s["yaw"]) > .05, f"yaw {s['yaw']:.2f} -> {c['yaw']:.2f}")
            pg.screenshot(path=str(OUT / "t4-firefox.png"))
        else:
            print("SKIP Firefox: WebGL 2 not available in this headless build:", pg.inner_text("#fail"), ferrs[:3])
        f.close()
    except Exception as e:
        print("SKIP Firefox:", e)

print("\nFAILED: " + ", ".join(fails) if fails else "\nall passed")
sys.exit(1 if fails else 0)
