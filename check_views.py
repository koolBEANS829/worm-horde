#!/usr/bin/env python3
"""Check the two ways of joining the horde, with real key presses in headless Chromium.

Usage: python3 check_views.py SCREENSHOT_DIR [PART ...]

A full run takes about 5 minutes. Name parts to run only those, in their usual order; they share
one page, so include the parts that set up what a later one needs. An unknown name lists them all.
"""
import math, pathlib, statistics, sys
from playwright.sync_api import sync_playwright

PAGE = pathlib.Path(__file__).resolve().parent / "index.html"
OUT = pathlib.Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
GPU_ARGS = ["--use-angle=vulkan", "--enable-features=Vulkan", "--ignore-gpu-blocklist", "--enable-gpu"]
LOOK_PLUS_X = -math.pi / 2   # yaw that looks along +x
fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        fails.append(name)


def part(name, fn):
    """A crash inside a group of checks counts as a failure and doesn't stop the others."""
    try:
        fn()
    except Exception as e:
        check(name, False, "crashed: " + str(e).splitlines()[0])


with sync_playwright() as p:
    b = p.chromium.launch(args=GPU_ARGS)
    pg = b.new_page(viewport={"width": 1280, "height": 720})
    pg.set_default_timeout(3000)
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(PAGE.as_uri())
    pg.wait_for_function("window.__horde", timeout=30000)
    pg.wait_for_timeout(500)
    ev = pg.evaluate
    st = lambda: ev("__horde.state()")
    you = lambda: ev("__horde.you()")
    stats = lambda: ev("__horde.stats()")
    centre = lambda: ev("__horde.centre()")
    press = lambda key: (pg.keyboard.press(key), pg.wait_for_timeout(100))
    pressed = lambda sel: pg.get_attribute(sel, "aria-pressed") == "true"

    def shot(name):
        pg.wait_for_timeout(500)
        pg.screenshot(path=str(OUT / f"{name}.png"), timeout=20000)   # usually under a second, but it once took over 3 s on a busy machine

    def hold(key, steps):
        pg.keyboard.down(key)
        ev(f"__horde.sim({steps})")
        pg.keyboard.up(key)

    def chase():
        if st()["order"] == "follow":
            press("KeyF")

    def horde_entry():
        ev("__horde.pause(true)")
        press("KeyH")
        s = st()
        check("H joins the horde: no arrow, the orb stays in sight",
              s.get("mode") == "horde" and s["orbVisible"] and not s["arrowVisible"] and pressed("#hordeview"))
        check("the horde starts out chasing, with the switch showing", s["order"] == "chase" and pg.is_visible("#order") and not pressed("#order"))

    def orb_walks():
        ev("__horde.dwell(0); __horde.pause(false)")
        a = st()
        pg.wait_for_timeout(3000)
        c = st()
        walked = math.hypot(c["x"] - a["x"], c["z"] - a["z"])
        check("the orb walks its route by itself", walked > 3, f"{walked:.1f} m in 3 s")
        ev("__horde.dwell(60)")
        a = st()
        pg.keyboard.down("KeyW"); pg.wait_for_timeout(800); pg.keyboard.up("KeyW")
        c = st()
        moved = math.hypot(c["x"] - a["x"], c["z"] - a["z"])
        check("WASD doesn't move the orb", moved < .05, f"{moved:.2f} m")
        ev("__horde.dwell(0); __horde.pause(true)")
        chase()

    def horde_camera():
        ev(f"__horde.set(500); __horde.place(-20, 0, 12); __horde.sim(1500); __horde.view({LOOK_PLUS_X}, -.45)")
        s, c = st(), centre()
        gap = math.dist(s["cam"], [c["x"], c["y"], c["z"]])
        # Look direction for this yaw and pitch, worked out by hand: mostly +x and tipped down.
        look = (math.cos(.45), -math.sin(.45), 0)
        ahead = sum(u * (v - w) for u, v, w in zip(look, (c["x"], c["y"], c["z"]), s["cam"]))
        check("the camera floats behind the horde's average position", 4 < gap < 16 and ahead > 3, f"{gap:.1f} m away, {ahead:.1f} m ahead")
        shot("v1-horde-view")

    def arms():
        before = centre()
        pg.keyboard.down("KeyW")
        ev("__horde.sim(210)")
        leads, closest = [], []
        for _ in range(4):        # tips, because the arms share a crowded root on purpose; several moments, because the waves swing them
            ev("__horde.sim(30)")
            tips, c = ev("__horde.armTips()"), centre()
            leads.append(max(t["x"] for t in tips) - c["x"])
            closest.append(min(math.hypot(a["x"] - b["x"], a["z"] - b["z"]) for a, b in zip(tips, tips[1:])))
        h = stats()
        pg.keyboard.up("KeyW")
        along = c["x"] - before["x"]
        check("pushing takes the horde off its chase", st()["order"] == "follow" and pressed("#order"))
        check("holding W pours the horde the way you're looking", along > 4, f"average moved {along:.1f} m")
        check("the horde splits into separate arms", statistics.median(closest) > 3, f"closest arm tips {[round(v, 1) for v in closest]} m")
        check("the arms stretch out ahead of the horde's middle", statistics.median(leads) > 4, f"lead {[round(v, 1) for v in leads]} m")
        check("arms pour along the ground instead of rising through the air", h["above1mPct"] < 25, f"{h['above1mPct']}% of dots above 1 m")
        ev(f"__horde.view({LOOK_PLUS_X}, -.45)")
        shot("v2-arms-pouring")
        ev(f"__horde.lights(true); __horde.view({LOOK_PLUS_X}, -.8)")
        shot("v2b-arms-lights-on")
        ev("__horde.lights(false)")

    def arms_wave():
        pg.keyboard.down("KeyW")
        ev("__horde.sim(240)")
        a = ev("__horde.armTips()")
        ev("__horde.sim(120)")
        c = ev("__horde.armTips()")
        pg.keyboard.up("KeyW")
        swings = [abs(u["z"] - v["z"]) for u, v in zip(a, c)]     # looking along +x, z is side to side
        check("the arms wave from side to side", max(swings) > 1, f"tips swung {[round(s, 1) for s in swings]} m in 2 s")

    def let_go():
        a = centre()
        ev("__horde.sim(180)")
        b = centre()
        tips = ev("__horde.armTips()")
        ev("__horde.sim(180)")
        d = centre()
        slid = math.hypot(b["x"] - a["x"], b["z"] - a["z"])
        wander = math.hypot(d["x"] - b["x"], d["z"] - b["z"])
        reach = max(math.hypot(t["x"] - b["x"], t["z"] - b["z"]) for t in tips)
        # Arms 13 m long take a while to gather, so this allows some settling. The stay-put check below is the strict one.
        check("letting go stops the horde where it is", slid < 2 and wander < 1, f"moved {slid:.1f} m in the first 3 s, then {wander:.2f} m in the next 3 s")
        check("letting go pulls the arms back in", reach < 4, f"tips within {reach:.1f} m of the middle")
        press("KeyF")
        check("F sends a horde you're holding after the orb", st()["order"] == "chase" and not pressed("#order"))
        ev("__horde.sim(1000)")
        h = stats()
        check("released, everything goes for the orb", h["near6Pct"] > 60, f"{h['near6Pct']}% within 6 m")

    def fine_moves():
        # The orb goes 32 m off to the side, so any pull toward it shows up as movement along -z.
        chase()
        ev(f"__horde.place(-20, 0, 12); __horde.sim(800); __horde.view({LOOK_PLUS_X}, -.45); __horde.place(-20, 0, -20)")
        c0 = centre()
        press("KeyF")
        check("F takes hold of a chasing horde", st()["order"] == "follow" and pressed("#order"))
        ev("__horde.sim(300)")
        a = centre()
        lean = c0["z"] - a["z"]
        check("a horde you're holding leans toward the orb", .3 < lean < 2, f"{lean:.2f} m")
        ev("__horde.sim(360)")
        b = centre()
        idle = math.hypot(b["x"] - a["x"], b["z"] - a["z"])
        check("left alone, it stays put however far off the orb is", idle < .3, f"moved {idle:.2f} m in 6 s")
        squirm = stats()["meanSpeed"]
        check("left alone, it keeps squirming", squirm > .2, f"{squirm} m/s")
        a = centre()
        hold("KeyW", 12)
        ev("__horde.sim(180)")
        b = centre()
        tap = b["x"] - a["x"]
        check("a 0.2 s tap moves it a little, and it stays there", .08 < tap < .8, f"{tap:.2f} m")
        a = centre()
        for _ in range(5):
            hold("KeyW", 12)
            ev("__horde.sim(18)")
        ev("__horde.sim(180)")
        b = centre()
        taps = b["x"] - a["x"]
        check("taps add up", .6 < taps < 2.5, f"five taps moved it {taps:.2f} m")

    def mid_chase():
        chase()
        ev(f"__horde.place(-20, 0, 12); __horde.sim(800); __horde.view({LOOK_PLUS_X}, -.45); __horde.place(-20, 0, -20); __horde.sim(60)")
        a = centre()
        hold("KeyW", 12)
        ev("__horde.sim(180)")
        b = centre()
        pulled = a["z"] - b["z"]    # with no keys it goes about 7 m in these 3 s
        check("a tap in the middle of a chase takes the horde back at once", st()["order"] == "follow" and pulled < 1.5, f"{pulled:.2f} m further toward the orb")

    def reverse():
        # Pour one way, then turn right round without letting go: the arms have to re-form the other way.
        # A fresh pile in a known place: starting from where mid-chase leaves the horde, the arms came out messier
        # every time, probably from running into the pillar at (-15, 9).
        chase()
        ev(f"__horde.place(-20, 0, 12); __horde.sim(800); __horde.view({LOOK_PLUS_X}, -.45)")
        pg.keyboard.down("KeyW")
        ev("__horde.sim(360)")
        pg.keyboard.up("KeyW")
        pg.keyboard.down("KeyS")
        turned = centre()
        # The waves swing the tips about 2 m each way, so one instant can catch two of them close together.
        # Take the middle of several moments. Stop at 3.5 s: any later and the room's end wall squashes the arms.
        ev("__horde.sim(120)")
        leads, closest = [], []
        for _ in range(4):
            ev("__horde.sim(30)")
            tips, c = ev("__horde.armTips()"), centre()
            leads.append(c["x"] - min(t["x"] for t in tips))
            closest.append(min(math.hypot(a["x"] - b["x"], a["z"] - b["z"]) for a, b in zip(tips, tips[1:])))
        pg.keyboard.up("KeyS")
        back = turned["x"] - c["x"]
        check("turning right round makes the arms re-form the other way", back > 2 and statistics.median(leads) > 3 and statistics.median(closest) > 3,
              f"average went back {back:.1f} m, tips out front {[round(v, 1) for v in leads]} m, closest tips {[round(v, 1) for v in closest]} m")
        chase()
        ev("__horde.sim(1000)")

    def pile_here():
        chase()
        ev(f"__horde.set(500); __horde.place(-20, 0, 12); __horde.sim(1000); __horde.view({LOOK_PLUS_X}, -.45)")

    def dot_take():
        pile_here()
        ev("__horde.place(-20, 0, -20); __horde.sim(60)")      # the orb goes 32 m off to the side, and they set off after it
        check("no dot while they're chasing", not st().get("dot"))
        a = centre()
        pg.keyboard.down("KeyW")
        ev("__horde.sim(1)")
        s, y, c = st(), you(), centre()
        check("pushing takes the horde off its chase and shows the dot", s["order"] == "follow" and s["dot"] and pressed("#order"))
        check("the dot starts among the worms", math.hypot(y["x"] - c["x"], y["z"] - c["z"]) < 3, f"{math.hypot(y['x'] - c['x'], y['z'] - c['z']):.1f} m from the middle")
        ev("__horde.sim(12)")
        pg.keyboard.up("KeyW")
        ev("__horde.sim(180)")
        b = centre()
        check("the horde stops heading for the orb at once", a["z"] - b["z"] < 2, f"{a['z'] - b['z']:.2f} m further toward it, about 7 m with no keys")

    def dot_moves():
        pile_here()
        press("KeyF")
        ev("__horde.sim(240)")
        a = you()
        hold("KeyW", 120)
        c = you()
        walked = c["x"] - a["x"]
        check("W moves the dot the way a worm crawls", walked > 5, f"{walked:.1f} m in 2 s")
        ev("__horde.sim(60)")
        a = you()
        ev("__horde.sim(120)")
        c = you()
        still = math.dist((a["x"], a["y"], a["z"]), (c["x"], c["y"], c["z"]))
        check("letting go stops the dot dead", still < .3, f"moved {still:.2f} m in 2 s")
        a = you()
        pg.keyboard.down("ShiftLeft"); hold("KeyW", 120); pg.keyboard.up("ShiftLeft")
        ran = you()["x"] - a["x"]
        check("Shift hurries the dot", ran > walked * 1.25, f"{ran:.1f} m against {walked:.1f} m")
        ev(f"__horde.putYou(-14, .2, 0); __horde.sim(30)")     # long wall at x = -10, 4 m tall
        pg.keyboard.down("KeyW")
        top, over = 0, you()["x"]
        for _ in range(60):
            ev("__horde.sim(10)")
            y = you()
            top = max(top, y["y"])
            over = y["x"]
            if over > -9.4:
                break
        pg.keyboard.up("KeyW")
        check("the dot climbs walls and goes over the top", 3.5 < top < 5.5 and over > -9.4, f"top {top:.1f} m, got to x = {over:.1f}")

    def stream():
        pile_here()
        press("KeyF")
        ev("__horde.sim(240)")
        before, wide = centre(), ev("__horde.spread()")
        pg.keyboard.down("KeyW")
        ev("__horde.sim(300)")
        y, c = you(), centre()
        far = ev("__horde.spread()")
        pg.keyboard.up("KeyW")
        check("the horde follows the dot", c["x"] - before["x"] > 3, f"average moved {c['x'] - before['x']:.1f} m in 5 s")
        check("the dot pulls out ahead of the horde", y["x"] - c["x"] > 5, f"{y['x'] - c['x']:.1f} m ahead")
        # With no pace differences this stays at 1.0 times. Working runs have measured from 1.3 to 1.5 times.
        check("the horde strings out behind it", far > wide * 1.15, f"spread {wide:.1f} -> {far:.1f} m")
        ev(f"__horde.view({LOOK_PLUS_X}, -.45)")
        shot("v2-stream-after-the-dot")

    def arrive():
        ev("__horde.sim(1500)")
        h, d = stats(), ev("__horde.meanToYou()")
        check("the horde reaches the dot", d < 13, f"{d:.1f} m from it on average")
        check("they stop instead of bunching up", h["above1mPct"] < 5 and h["topY"] < 1.5, f"{h['above1mPct']}% of dots above 1 m, highest {h['topY']:.1f} m")
        a = centre()
        ev("__horde.sim(180)")
        b = centre()
        moved = math.hypot(b["x"] - a["x"], b["z"] - a["z"])
        check("then they stay put", moved < .2, f"average moved {moved:.2f} m in 3 s")
        h = stats()
        check("stopped worms barely move, but aren't frozen", .001 < h["meanSpeed"] < .3, f"{h['meanSpeed']} m/s")
        ev(f"__horde.view({LOOK_PLUS_X}, -.45)")
        shot("v3-stopped-at-the-dot")

    def orb_bunches():
        press("KeyF")
        ev("__horde.sim(1500)")
        h, s = stats(), st()
        check("F sends them after the orb, and the dot goes away", s["order"] == "chase" and not s["dot"])
        check("they still bunch up on the orb", h["near6Pct"] > 60 and h["above1mPct"] > 20, f"{h['near6Pct']}% within 6 m, {h['above1mPct']}% of dots above 1 m")

    def dot_tap():
        pile_here()
        press("KeyF")
        ev("__horde.sim(400)")
        a, y0 = centre(), you()
        hold("KeyW", 12)
        ev("__horde.sim(60)")
        b, y1 = centre(), you()
        check("a 0.2 s tap moves the dot a little", .15 < y1["x"] - y0["x"] < 1.5, f"{y1['x'] - y0['x']:.2f} m")
        moved = math.hypot(b["x"] - a["x"], b["z"] - a["z"])
        check("a tap leaves the horde nearly still", moved < .3, f"average moved {moved:.2f} m")

    def strafe():
        before = centre()
        hold("KeyD", 240)     # looking along +x, right is +z
        c = centre()
        check("D pours to the right of where you're looking", c["z"] - before["z"] > 3, f"{c['z'] - before['z']:.1f} m")
        chase()
        ev("__horde.sim(800)")

    def no_blast():
        if not st()["locked"]:
            pg.mouse.click(640, 360); pg.wait_for_timeout(300)
        before = ev("__horde.spread()")
        pg.mouse.down(); pg.mouse.up(); pg.wait_for_timeout(100)
        ev("__horde.sim(25)")
        after = ev("__horde.spread()")
        check("clicking doesn't blast", st()["locked"] and after < before * 1.2, f"spread {before:.2f} -> {after:.2f} m, mouse locked: {st()['locked']}")

    def c_ignored():
        third = st()["third"]
        press("KeyC")
        s = st()
        check("C does nothing while you're with the worms", s["third"] == third and s["mode"] != "orb" and not pg.is_visible("#camview"))

    def horde_clearance():
        chase()
        low = 99
        for x, z in ((-11.5, 0), (23, 23), (-4, 3), (0, -23)):
            ev(f"__horde.set(100); __horde.place({x}, 0, {z}); __horde.sim(1500); __horde.view({LOOK_PLUS_X}, -.45)")
            low = min(low, st()["camClearance"])
        check("the horde camera stays out of walls", low > .1, f"closest gap {low:.2f} m")

    def leave_horde():
        press("KeyH")
        s = st()
        check("H again goes back to being the orb", s["mode"] == "orb" and s["third"] and s["arrowVisible"] and not pressed("#hordeview"))

    def orb_gets_unstuck():
        # Behind walls and off the route: wherever you leave the orb, it has to find its way on.
        out = []
        for x, z in ((-12, 0), (-7, -5), (7, 3), (0, 12), (13, 18)):
            ev(f"__horde.place({x}, 0, {z})")
            press("KeyH")
            ev("__horde.dwell(0)")
            a = st()
            ev("__horde.walk(600)")
            c = st()
            out.append(round(math.hypot(c["x"] - a["x"], c["z"] - a["z"]), 1))
            press("KeyH")
        check("from anywhere you left it, the orb walks on", min(out) > 8, f"{out} m in 10 s")

    def worm_entry():
        ev("__horde.set(100); __horde.place(20, 0, -8)")
        check("the follow switch stays hidden while you're the orb", not pg.is_visible("#order"))
        press("KeyB")
        s = st()
        check("B makes you a worm: no arrow, the orb stays in sight",
              s["mode"] == "worm" and s["orbVisible"] and not s["arrowVisible"] and pressed("#wormview"))
        check("you start out chasing, with the switch showing", s["order"] == "chase" and pg.is_visible("#order") and not pressed("#order"))

    def crawl():
        ev(f"__horde.putYou(-20, .2, 20); __horde.view({LOOK_PLUS_X}, -.2)")
        ev("__horde.sim(30)")
        a = you()
        hold("KeyW", 120)
        c = you()
        walked = c["x"] - a["x"]
        check("W crawls your worm where you're looking", walked > 3, f"{walked:.1f} m along, {abs(c['z'] - a['z']):.1f} m sideways in 2 s")
        ev("__horde.sim(60)")
        a = you()
        ev("__horde.sim(120)")
        c = you()
        still = math.dist((a["x"], a["y"], a["z"]), (c["x"], c["y"], c["z"]))
        check("letting go stops your worm", still < .3, f"drifted {still:.2f} m in 2 s")
        ev(f"__horde.putYou(-20, .2, 20); __horde.sim(30)")
        a = you()
        pg.keyboard.down("ShiftLeft"); hold("KeyW", 120); pg.keyboard.up("ShiftLeft")
        ran = you()["x"] - a["x"]
        check("Shift hurries", ran > walked * 1.25, f"{ran:.1f} m against {walked:.1f} m")

    def turn():
        ev(f"__horde.putYou(-20, .2, 20); __horde.view(0, -.2); __horde.sim(30)")   # yaw 0 looks along -z
        a = you()
        hold("KeyW", 90)
        c = you()
        check("your worm goes where you turn", a["z"] - c["z"] > 2, f"{a['z'] - c['z']:.1f} m along -z")

    def climb():
        ev(f"__horde.putYou(-14, .2, 0); __horde.view({LOOK_PLUS_X}, -.2); __horde.sim(30)")   # long wall at x = -10, 4 m tall
        pg.keyboard.down("KeyW")
        top, over = 0, you()["x"]
        for _ in range(60):
            ev("__horde.sim(10)")
            y = you()
            top = max(top, y["y"])
            over = y["x"]
            if over > -9.4:   # past the far face of that wall
                break
        pg.keyboard.up("KeyW")
        check("crawling into a wall climbs it and takes you over the top", 3.5 < top < 5.5 and over > -9.4, f"top {top:.1f} m, got to x = {over:.1f}")

    def chase_follow():
        ev("__horde.set(200); __horde.place(20, 0, -8); __horde.putYou(-20, .2, 20); __horde.sim(2400)")
        h, d = stats(), ev("__horde.meanToYou()")
        check("Chase: the horde goes for the orb and leaves you behind", h["near6Pct"] > 60 and d > 20, f"{h['near6Pct']}% within 6 m of the orb, {d:.1f} m from you on average")
        press("KeyF")
        check("F flips the switch to Follow", st()["order"] == "follow" and pressed("#order"))
        ev("__horde.sim(1500)")
        # You're at (-20, 20) and the horde comes from the orb's corner: look along (+.82, -.57).
        ev("__horde.view(-.96, -.2)")
        shot("v4-horde-coming-for-you")
        ev("__horde.sim(1100)")
        h, d = stats(), ev("__horde.meanToYou()")
        check("Follow: the horde comes to you and forgets the orb", d < 9 and h["near6Pct"] < 10, f"{d:.1f} m from you on average, {h['near6Pct']}% near the orb")
        check("Follow: they stop around you instead of bunching up", h["above1mPct"] < 5, f"{h['above1mPct']}% of dots above 1 m")
        press("KeyF")
        ev("__horde.sim(2400)")
        h, d = stats(), ev("__horde.meanToYou()")
        check("F again: back to chasing the orb", st()["order"] == "chase" and h["near6Pct"] > 60 and d > 20, f"{h['near6Pct']}% near the orb")

    def trail():
        ev("__horde.set(200); __horde.putYou(-20, .2, 20); __horde.place(20, 0, -8)")
        press("KeyF")
        ev("__horde.sim(1800)")
        ev(f"__horde.view({LOOK_PLUS_X}, -.2)")
        pg.keyboard.down("KeyW")
        ev("__horde.sim(240)")
        d0 = ev("__horde.meanToYou()")
        ev("__horde.sim(200)")
        pg.keyboard.up("KeyW")
        a = you()["x"]
        behind = ev("__horde.meanBehindYou()")
        check("followers trail along behind you", behind > .5, f"{behind:.1f} m behind on average, {d0:.1f} m away mid-crawl, head at x = {a:.1f}")
        press("KeyF")

    def free_of_pile():
        ev("__horde.set(500); __horde.place(20, 0, -8); __horde.putYou(-20, .2, 20)")
        press("KeyF")
        ev(f"__horde.sim(2000); __horde.view({LOOK_PLUS_X}, -.2)")
        a = you()
        hold("KeyW", 180)
        c = you()
        out = math.hypot(c["x"] - a["x"], c["z"] - a["z"])
        check("you can crawl straight out of a pile of 500", out > 3, f"{out:.1f} m in 3 s")
        ev(f"__horde.sim(240); __horde.view({LOOK_PLUS_X}, -.3)")
        shot("v3-worm-in-the-pile")
        press("KeyF")

    def worm_clearance():
        low = 99
        for x, y, z, yaw in ((-10.7, .2, 0, 1.57), (23.3, .2, 0, 1.57), (0, .2, -23.3, 3.14), (-4, .2, 1.5, 3.14)):
            ev(f"__horde.putYou({x}, {y}, {z}); __horde.sim(5); __horde.view({yaw}, -.1)")
            low = min(low, st()["camClearance"])
        check("the worm camera stays out of walls", low > .1, f"closest gap {low:.2f} m")

    def one_worm():
        press("Digit0")
        ev("__horde.putYou(-20, .2, 20)")
        a = you()
        hold("KeyW", 60)
        check("worm view still works with one worm: it's you", st()["mode"] == "worm" and you()["x"] != a["x"])

    def leave_worm():
        press("KeyB")
        s = st()
        check("B again goes back to being the orb", s["mode"] == "orb" and s["third"] and s["arrowVisible"] and not pg.is_visible("#order"))

    def orb_blasts_again():
        ev("__horde.set(500); __horde.place(-18, 0, 12); __horde.view(-1.2, -0.1); __horde.sim(1500)")
        if not st()["locked"]:
            pg.mouse.click(640, 360); pg.wait_for_timeout(300)
        before = ev("__horde.spread()")
        pg.mouse.down(); pg.mouse.up(); pg.wait_for_timeout(100)
        ev("__horde.sim(25)")
        after = ev("__horde.spread()")
        check("as the orb, clicking blasts again", after > before * 1.5, f"spread {before:.2f} -> {after:.2f} m")

    def set_dial(name, value):
        ev(f"(() => {{ const e = document.getElementById('dial-{name}'); e.value = {value}; e.dispatchEvent(new Event('input', {{ bubbles: true }})); }})()")

    def dial_pile(n=200):
        chase()
        # Long enough for fresh worms to arrive from across the room. Any shorter and their arrival swamps what's being measured.
        ev(f"__horde.set({n}); __horde.place(-20, 0, 12); __horde.sim(1500); __horde.view({LOOK_PLUS_X}, -.45)")
        press("KeyF")
        ev("__horde.sim(120)")

    def dials():
        ev("__horde.pause(true)")
        if st()["mode"] != "horde":
            press("KeyH")
        if not st()["locked"]:
            pg.mouse.click(640, 360); pg.wait_for_timeout(300)
        check("the dials stay out of sight until you ask", not pg.is_visible("#dials"))
        press("KeyT")
        check("T opens the dials and frees the mouse", pg.is_visible("#dials") and not st()["locked"] and pressed("#dialsbtn"))
        shot("v7-dials")

        # A real drag on a real slider.
        box = pg.locator("#dial-dot").bounding_box()
        before = pg.input_value("#dial-dot"), pg.inner_text("#dial-dot-value")
        pg.mouse.move(box["x"] + box["width"] * .35, box["y"] + box["height"] / 2)
        pg.mouse.down()
        pg.mouse.move(box["x"] + box["width"] * .8, box["y"] + box["height"] / 2, steps=5)
        pg.mouse.up()
        after = pg.input_value("#dial-dot"), pg.inner_text("#dial-dot-value")
        check("dragging a dial changes it and shows the new value", after[0] != before[0] and after[1] != before[1], f"{before[1]} -> {after[1]}")
        check("dragging a dial doesn't grab the mouse", not st()["locked"])

        dial_pile()
        a = you()
        hold("KeyW", 60)
        check("WASD still steers with the dials open", you()["x"] - a["x"] > .5, f"{you()['x'] - a['x']:.1f} m")

        # Each dial has to change what the worms do while it's being turned, not just its number.
        def dot_run(v):
            dial_pile()
            set_dial("dot", v)
            a = you()
            hold("KeyW", 60)
            return you()["x"] - a["x"]
        slow, fast = dot_run(.6), dot_run(2.5)
        check("Dot speed: the dot goes faster", fast > slow * 1.8, f"{slow:.1f} -> {fast:.1f} m in 1 s")
        set_dial("dot", 1.3)

        def crawl_run(v):
            dial_pile()
            set_dial("crawl", v)
            a = centre()
            hold("KeyW", 180)
            return centre()["x"] - a["x"]
        slow, fast = crawl_run(.5), crawl_run(1.6)
        check("Worm speed: the horde crawls faster", fast > slow * 1.5, f"{slow:.1f} -> {fast:.1f} m in 3 s")
        set_dial("crawl", 1)

        def stretch_run(v):
            set_dial("stretch", v)
            dial_pile(500)
            wide = ev("__horde.spread()")
            hold("KeyW", 300)
            return ev("__horde.spread()") / wide
        flat, long = stretch_run(0), stretch_run(.8)
        check("Stream stretch: the stream gets longer", long > flat * 1.2, f"stretches {flat:.2f} times -> {long:.2f} times")
        set_dial("stretch", .4)

        def stop_run(v):
            set_dial("stop", v)
            dial_pile()
            hold("KeyW", 180)
            ev("__horde.sim(900)")
            return ev("__horde.meanToYou()")
        tight, loose = stop_run(.15), stop_run(1.4)
        check("Stop spacing: they lie further apart", loose > tight * 1.4, f"{tight:.1f} -> {loose:.1f} m from the dot on average")
        set_dial("stop", .6)

        def wake_run(v):
            set_dial("wake", v)
            dial_pile()
            ev("__horde.sim(120)")
            a = centre()
            hold("KeyW", 60)
            return math.hypot(centre()["x"] - a["x"], centre()["z"] - a["z"])
        none, long = wake_run(0), wake_run(.5)
        check("Wake delay: far worms set off later", none > long * 1.3, f"horde moved {none:.2f} m in 1 s with none, {long:.2f} m with a long one")
        set_dial("wake", .12)

        def squirm_run(v):
            set_dial("squirm", v)
            dial_pile()
            ev("__horde.sim(120)")
            return stats()["meanSpeed"]
        still, lively = squirm_run(0), squirm_run(1)
        check("Rest squirm: stopped worms wriggle more", lively > still * 1.5, f"{still} -> {lively} m/s")

        # Settings survive a reload, and Reset really resets.
        set_dial("dot", 2.2)
        pg.reload()
        pg.wait_for_function("window.__horde", timeout=30000)
        check("the dials survive a reload", pg.input_value("#dial-dot") == "2.2", pg.input_value("#dial-dot"))
        press("KeyT")
        pg.click("#dialsreset")
        wanted = {"dot": "1.3", "crawl": "1", "stretch": "0.4", "stop": "0.6", "wake": "0.12", "squirm": "0.2"}
        got = {k: pg.input_value(f"#dial-{k}") for k in wanted}
        check("Reset puts every dial back", got == wanted, str(got))
        pg.reload()
        pg.wait_for_function("window.__horde", timeout=30000)
        check("a reset survives a reload too", pg.input_value("#dial-dot") == "1.3", pg.input_value("#dial-dot"))
        press("KeyT")
        press("KeyT")
        check("T again closes the dials", not pg.is_visible("#dials") and not pressed("#dialsbtn"))

    def dials_lock():
        press("KeyH")
        if not st()["locked"]:
            pg.mouse.click(640, 360); pg.wait_for_timeout(300)
        press("KeyT")
        pg.wait_for_timeout(1300)     # Chromium refuses to lock the mouse again straight after an unlock
        press("KeyT")
        pg.wait_for_timeout(200)
        check("closing the dials takes the mouse back", st()["locked"])
        press("KeyH")

    def speed():
        ev("__horde.pause(false)")
        for mode_key, label in (("KeyH", "horde view"), ("KeyB", "worm view")):
            press(mode_key)
            for key, n in (("Digit2", 500), ("Digit3", 1000)):
                press(key)
                pg.keyboard.down("KeyW")
                r = []
                for _ in range(4):
                    pg.wait_for_timeout(2000)
                    r.append((int(pg.inner_text("#fps")), float(pg.inner_text("#phys").split()[0])))
                pg.keyboard.up("KeyW")
                print(f"{label}, {n} worms realtime: fps {[x[0] for x in r]} physics ms {[x[1] for x in r]}")
            press(mode_key)

    # The spot-and-arms checks still fit the older control, which index.html keeps switched off behind DOT_CONTROL.
    control = (("dot-take", dot_take), ("dot-moves", dot_moves), ("stream", stream), ("arrive", arrive), ("orb-bunches", orb_bunches), ("dot-tap", dot_tap))
    if st().get("control") == "spot":
        control = (("arms", arms), ("arms-wave", arms_wave), ("let-go", let_go), ("fine-moves", fine_moves), ("mid-chase", mid_chase), ("reverse", reverse), ("strafe", strafe))
    parts = (("horde-entry", horde_entry), ("orb-walks", orb_walks), ("horde-camera", horde_camera)) + control + (("no-blast-horde", no_blast), ("c-horde", c_ignored),
             ("horde-clearance", horde_clearance), ("leave-horde", leave_horde), ("orb-unstuck", orb_gets_unstuck),
             ("worm-entry", worm_entry), ("crawl", crawl), ("turn", turn), ("climb", climb), ("chase-follow", chase_follow),
             ("trail", trail), ("free-of-pile", free_of_pile), ("no-blast-worm", no_blast), ("worm-clearance", worm_clearance),
             ("one-worm", one_worm), ("leave-worm", leave_worm), ("orb-blasts", orb_blasts_again), ("dials", dials), ("dials-lock", dials_lock), ("speed", speed))
    only = sys.argv[2:]
    unknown = set(only) - {n for n, _ in parts} - {"firefox"}
    if unknown:
        sys.exit(f"unknown parts {sorted(unknown)}; choose from: " + " ".join(n for n, _ in parts) + " firefox")
    for name, fn in parts:
        if not only or name in only:
            part(name, fn)
    check("no page errors", not errs, "; ".join(errs[:4]))
    b.close()

    # Headless Chromium reports no mouse movement under pointer lock, so mouse steering has to be checked here.
    def firefox():
        f = p.firefox.launch(firefox_user_prefs={"webgl.force-enabled": True, "webgl.disabled": False})
        fp = f.new_page(viewport={"width": 1280, "height": 720})
        fp.set_default_timeout(3000)
        ferrs = []
        fp.on("console", lambda m: ferrs.append(m.text) if m.type == "error" else None)
        fp.on("pageerror", lambda e: ferrs.append(str(e)))
        fp.goto(PAGE.as_uri())
        fp.wait_for_function("window.__horde", timeout=30000)
        fe = fp.evaluate
        fp.keyboard.press("KeyB")
        fp.wait_for_timeout(500)
        s = fe("__horde.state()")
        check("Firefox: B works straight after the page loads", s["mode"] == "worm", f"mouse locked: {s['locked']}")
        if not s["locked"]:
            fp.mouse.click(640, 360); fp.wait_for_timeout(500)
        for x in (660, 700, 760, 840):
            fp.mouse.move(x, 350); fp.wait_for_timeout(50)
        fp.wait_for_timeout(200)
        c = fe("__horde.state()")
        check("Firefox: the mouse turns the view as a worm", abs(c["yaw"] - s["yaw"]) > .05, f"yaw {s['yaw']:.2f} -> {c['yaw']:.2f}, mouse locked: {c['locked']}")
        a = fe("__horde.you()")
        fp.keyboard.down("KeyW"); fp.wait_for_timeout(1500); fp.keyboard.up("KeyW")
        d = fe("__horde.you()")
        moved = math.hypot(d["x"] - a["x"], d["z"] - a["z"])
        look = (-math.sin(c["yaw"]), -math.cos(c["yaw"]))
        along = (d["x"] - a["x"]) * look[0] + (d["z"] - a["z"]) * look[1]
        check("Firefox: W crawls the way the mouse turned you", along > 1, f"{along:.1f} m along the view, {moved:.1f} m in all in 1.5 s")
        fp.screenshot(path=str(OUT / "v5-firefox-worm.png"))
        fp.keyboard.press("KeyH")
        fp.wait_for_timeout(300)
        a = fe("__horde.centre()")
        fp.keyboard.down("KeyW"); fp.wait_for_timeout(4000)
        d = fe("__horde.centre()")
        fp.screenshot(path=str(OUT / "v6-firefox-horde.png"))
        fp.keyboard.up("KeyW")
        s = fe("__horde.state()")
        check("Firefox: H straight from worm view, and W leads the horde", s["mode"] == "horde" and s["dot"] and math.hypot(d["x"] - a["x"], d["z"] - a["z"]) > 1.5, f"average moved {math.hypot(d['x'] - a['x'], d['z'] - a['z']):.1f} m in 4 s")
        check("Firefox: no page errors", not ferrs, "; ".join(ferrs[:4]))
        f.close()

    if not only or "firefox" in only:
        part("firefox", firefox)

print("\nFAILED: " + ", ".join(fails) if fails else "\nall passed")
sys.exit(1 if fails else 0)
