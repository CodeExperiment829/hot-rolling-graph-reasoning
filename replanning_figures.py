"""Manuscript panel layouts. All result marks and labels use fresh evaluations."""
import math

import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyBboxPatch, Polygon, Rectangle

from publishing import figure

NAVY, INK, BLUE, TEAL = "17395E", "182733", "2978BD", "29A79C"
ORANGE, RED, PALE, WHITE = "F08C38", "D64B51", "E9F2F9", "FFFFFF"
SCALE = .62


def canvas():
    fig = plt.figure(figsize=(1600 * SCALE / 72, 1000 * SCALE / 72), facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1], xlim=(0, 1600), ylim=(1000, 0), aspect="equal")
    ax.set_axis_off()
    return ax


def style(fill, stroke, lw, dash=False):
    return dict(facecolor="#" + fill if fill else "none", edgecolor="#" + stroke if stroke else "none",
                linewidth=lw * SCALE, linestyle="--" if dash else "-", clip_on=False)


def box(slide, name, x, y, w, h, fill=None, stroke=None, lw=1, radius=False, dash=False):
    kw = style(fill, stroke, lw, dash)
    if radius:
        patch = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={min(w*.1,h*.1,9)}", **kw)
    else:
        patch = Rectangle((x, y), w, h, **kw)
    patch.set_zorder(len(slide.get_children()) + 1)
    slide.add_patch(patch)


def poly(slide, name, points, fill, stroke=None, lw=1):
    slide.add_patch(Polygon(points, closed=True, zorder=len(slide.get_children()) + 1, **style(fill, stroke, lw)))


def oval(slide, name, x, y, w, h, fill, stroke=None, lw=1):
    slide.add_patch(Ellipse((x + w / 2, y + h / 2), w, h, zorder=len(slide.get_children()) + 1,
                            **style(fill, stroke, lw)))


def line(slide, name, x1, y1, x2, y2, color=INK, lw=1.4, dash=False, arrow=False):
    kw = dict(color="#" + color, lw=lw * SCALE, ls="--" if dash else "-", zorder=len(slide.get_children()) + 1)
    slide.plot([x1, x2], [y1, y2], solid_capstyle="butt", **kw)
    if arrow:
        a = math.atan2(y2 - y1, x2 - x1)
        size = 5 + lw
        tip = [(x2, y2)] + [(x2 - size * math.cos(a + angle), y2 - size * math.sin(a + angle))
                             for angle in (-.45, .45)]
        poly(slide, name, tip, color)


def txt(slide, name, text, x, y, w, h, size=18, bold=False, color=INK, rotation=0):
    slide.text(x + w / 2, y + h / 2, str(text), ha="center", va="center", linespacing=.99,
               rotation=-rotation, weight="bold" if bold else "normal", fontsize=size * SCALE,
               color="#" + color, zorder=len(slide.get_children()) + 1)


def clock_time(minute):
    return f"{10 + minute // 60:02d}:{minute % 60:02d}"


def draw_trace(e, r, full):
    slide = canvas()
    oa, ob = e["old_a"], e["old_b"]
    da0, da, db = e["da_old"], e["da"], e["db"]
    old_a_end, new_a_end = r["old"][1], r["fresh"][1]
    old_b_end, new_b_end = r["old"][3], r["fresh"][3]
    final_a, final_b = r["plan"]
    first_a = next(t for t in range(max(new_a_end, oa), e["max_a"] + 1)
                   if not e["lock"] or t + da <= e["lock"][0] or e["lock"][1] <= t)
    horizon = max(final_a + da, final_b + db, *e["lock"]) + 2
    if not r["expanded"] or r["open"] != ["a"] or set(full["open"]) != {"a", "b"}:
        raise ValueError("The illustrated event no longer follows the reserve-and-expand path")
    if full["plan"] != r["plan"] or not (full["ok"] and r["ok"]):
        raise ValueError("The paired event schedules disagree")
    initial = (12, 34, 392, 941)
    paths_x, paths_w = 418, 1170
    head_fill = "D7E8F6"
    note_fill = "F0F5FA"
    orange_ink = "C75F11"
    status_green = "DFEFE5"
    status_orange = "FCE6D2"

    def timeline(name, x, y, w, h, mode, snapshot=False):
        # All panels share a linear time axis. An orange
        # booking on the crew row can precede, as well as coincide with,
        # the maintenance of a machine.
        label_w = 84 if snapshot else 67
        left = x + label_w
        right = x + w - (14 if snapshot else 12)
        baseline = y + h - 37
        row_pitch = (baseline - y) / 3
        bar_h = min(27, 0.5 * row_pitch)
        ys = [y + (i + 0.5) * row_pitch for i in range(3)]
        axis_stroke = 1.35

        def px(minute):
            return left + (right - left) * minute / horizon

        def block(row, start, end, color, suffix):
            return box(slide, name + " | " + suffix, px(start), ys[row] - bar_h / 2,
                       px(end) - px(start), bar_h, color)

        def open_task(row, start, end, unit):
            box(slide, name + " | " + unit + " opened", px(start) - 1.2,
                ys[row] - bar_h / 2 - 1.2, px(end) - px(start) + 2.4,
                bar_h + 2.4, None, orange_ink, 2.0, False, True)

        label_pt = 20 if snapshot else 16
        for row, label in enumerate(("Unit A", "Unit B", "Shared\nCrew")):
            txt(slide, name + " | " + label.replace("\n", " "), label,
                x, ys[row] - 21, label_w - 4, 42, label_pt)

        if mode == "initial":
            block(0, 0, old_a_end, BLUE, "A operation")
            block(0, oa, oa + da0, TEAL, "A original maintenance")
            block(1, 0, old_b_end if mode == "initial" else new_b_end, BLUE, "B operation")
            block(1, ob, ob + db, TEAL, "B original maintenance")
            block(2, oa, oa + da0, ORANGE, "crew serving A")
            block(2, ob, ob + db, ORANGE, "crew serving B")
        else:
            final = mode == "final"
            b_start, b_end = (final_b, final_b + db) if final else (ob, ob + db)
            block(0, 0, new_a_end, BLUE, "A operation")
            if mode != "feedback":
                block(0, final_a if final else first_a, (final_a if final else first_a) + da, TEAL, "A maintenance")
            block(1, 0, old_b_end if mode == "initial" else new_b_end, BLUE, "B operation")
            block(1, b_start, b_end, TEAL, "B maintenance")
            block(2, *e["lock"], ORANGE, "external crew occupation")
            if final:
                block(2, final_a, final_a + da, ORANGE, "crew serving A")
            block(2, b_start, b_end, ORANGE, "crew serving B")
            if mode in ("first", "both"):
                open_task(0, first_a, first_a + da, "Unit A")
            if mode == "both":
                open_task(1, ob, ob + db, "Unit B")

        line(slide, name + " | vertical axis", left, y, left, baseline,
             NAVY, axis_stroke)
        line(slide, name + " | time axis", left, baseline, right + 1, baseline,
             NAVY, axis_stroke, False, True)
        if snapshot:
            line(slide, name + " | predicted release marker", px(old_a_end), y - 1,
                 px(old_a_end), baseline, orange_ink, 1.7, True)
        minutes = (0, old_a_end, new_a_end, final_b) if snapshot else (0, new_a_end, final_b)
        for minute in minutes:
            at = px(minute)
            # Keep narrow chart labels legible without changing time scale.
            offset = max(0, (49 - (px(final_b) - px(new_a_end))) / 2)
            label_offset = {new_a_end: -offset, final_b: offset}.get(minute, 0)
            line(slide, name + f" | tick {minute}", at, baseline, at, baseline + 6,
                 NAVY, axis_stroke)
            txt(slide, name + f" | tick label {minute}", clock_time(minute),
                at + label_offset - 25, baseline + 8, 50, 25, 16)
        return px(old_a_end), y

    def draw_path_frame(title, y, height):
        box(slide, title + " | boundary", paths_x, y + 22, paths_w, height - 22,
            None, NAVY, 1.6, True, True)
        title_w = 633
        title_x = paths_x + (paths_w - title_w) / 2
        box(slide, title + " | blue banner", title_x, y, title_w, 47,
            NAVY, None, radius=True)
        txt(slide, title, title, title_x + 3, y + 2, title_w - 6, 43,
            24, True, WHITE)

    def stage(name, title, x, y, w, h, mode, strategy):
        box(slide, name + " | stage frame", x, y, w, h,
            WHITE, NAVY, 1.5, True)
        box(slide, name + " | heading band", x + 3, y + 3, w - 6, 46,
            head_fill, None, radius=True)
        txt(slide, name + " | heading", title, x + 4, y + 4, w - 8, 43, 20, True)
        if mode == "feedback":
            box(slide, name + " | feedback note", x + 10, y + 62, w - 20, 86,
                note_fill, None, radius=True)
            txt(slide, name + " | feedback", f"Actual release:\nUnit A at {clock_time(new_a_end)}",
                x + 14, y + 65, w - 28, 80, 20)
        elif mode == "first" or (mode == "both" and strategy == "local"):
            box(slide, name + " | action note", x + 10, y + 59, w - 20, 110,
                note_fill, None, radius=True)
            action = "Unit B: fixed\nUnit A: opened" if mode == "first" else "Open both\nmaintenance tasks"
            txt(slide, name + " | action", action, x + 14, y + 62, w - 28, 65, 20)
            status = "Crew conflict" if mode == "first" else "Resolve conflict"
            status_w = min(202, w - 36)
            status_x = x + (w - status_w) / 2
            box(slide, name + " | status fill", status_x, y + 128, status_w, 34,
                status_orange if mode == "first" else status_green, None, radius=True)
            txt(slide, name + " | status", status, status_x + 2, y + 128,
                status_w - 4, 34, 18, True)
        elif mode == "final":
            box(slide, name + " | verified note", x + 10, y + 59, w - 20, 105,
                note_fill, None, radius=True)
            if strategy == "local":
                a, b, size = (f"Unit A maintenance\nat {clock_time(new_a_end)}",
                              f"Unit B maintenance\nat {clock_time(final_b)}", 18)
            else:
                a, b, size = (f"Unit A maintenance at {clock_time(new_a_end)}",
                              f"Unit B maintenance at {clock_time(final_b)}", 20)
            txt(slide, name + " | verified A time", a, x + 13, y + 61, w - 26, 47, size)
            txt(slide, name + " | verified B time", b, x + 13, y + 111, w - 26, 47, size)
        ty = y + 184
        timeline(name, x + 2, ty, w - 4, y + h - 7 - ty, mode)

    def transition(name, x1, x2, mid):
        shoulder = x1 + (x2 - x1) * 0.48
        poly(slide, name, [(x1, mid - 5), (shoulder, mid - 5),
             (shoulder, mid - 13), (x2, mid), (shoulder, mid + 13),
             (shoulder, mid + 5), (x1, mid + 5)], BLUE)

    ix, iy, iw, ih = initial
    box(slide, "Shared initial snapshot | frame", ix, iy, iw, ih,
        WHITE, NAVY, 1.8, True)
    box(slide, "Shared initial snapshot | heading band", ix + 3, iy + 3, iw - 6, 55,
        head_fill, None, radius=True)
    txt(slide, "Shared initial snapshot | title", "Shared Initial Snapshot (10:00)",
        ix + 5, iy + 4, iw - 10, 51, 23, True)
    box(slide, "Original predicted release | callout", 59, 115, 295, 72,
        WHITE, orange_ink, 1.3, True)
    txt(slide, "Original predicted release", f"Original predicted\nrelease of Unit A: {clock_time(old_a_end)}",
        63, 117, 287, 68, 20, True, orange_ink)
    mark_x, mark_y = timeline("Initial snapshot", 19, 219, 379, 212, "initial", True)
    line(slide, "Original predicted release | pointer", 218, 187, mark_x, mark_y - 4,
         orange_ink, 1.6, False, True)
    box(slide, "Event information | frame", 23, 449, 370, 245,
        note_fill, NAVY, 1.1, True)
    event = [(f"Event: {e['id']}", 459, 40, 22, True),
             ("Initial time: 10:00", 501, 36, 20, False),
             (f"Original prediction: release of\nUnit A at {clock_time(old_a_end)}", 546, 58, 20, False),
             (f"Actual (checker): release of\nUnit A at {clock_time(new_a_end)}", 615, 58, 20, False)]
    for text, top, height, fs, bold in event:
        txt(slide, "Event information | " + text.split(":")[0], text,
            27, top, 362, height, fs, bold)
    box(slide, "Timeline legend | frame", 23, 720, 370, 234,
        WHITE, NAVY, 1.1, True)
    legend = [(BLUE, "Operation (no crew)"), (TEAL, "Maintenance (requires crew)"),
              (ORANGE, "Crew occupation (shared)"), (None, "Task opened for adjustment")]
    for n, (swatch, label) in enumerate(legend):
        cy = 754 + 54 * n
        box(slide, "Legend | " + label + " | sample", 40, cy - 11, 49, 22,
            swatch, orange_ink if swatch is None else None, 1.7, False, swatch is None)
        txt(slide, "Legend | " + label, label, 95, cy - 19, 284, 38, 19)

    draw_path_frame("Local Strategy (Reserve-and-Expand)", 15, 466)
    draw_path_frame("Full-Graph Strategy", 511, 464)
    rows = [
        ("local", 84, 377, [("Feedback Received", "feedback"), ("First Attempt", "first"),
                             ("Expand Neighborhood", "both"), ("Final Verified Schedule", "final")]),
        ("full", 579, 376, [("Feedback Received", "feedback"), ("Open Both Tasks", "both"),
                             ("Final Verified Schedule", "final")])
    ]
    for strategy, y, height, stages in rows:
        inner_x, inner_w = paths_x + 13, paths_w - 26
        gap = 25 if strategy == "local" else 42
        stage_w = (inner_w - gap * (len(stages) - 1)) / len(stages)
        for index, (title, mode) in enumerate(stages):
            x = inner_x + index * (stage_w + gap)
            name = ("Local" if strategy == "local" else "Full graph") + " | " + title
            stage(name, title, x, y, stage_w, height, mode, strategy)
            if index < len(stages) - 1:
                transition(name + " | next stage", x + stage_w + 2,
                           x + stage_w + gap - 2, y + height * 0.53)

    figure("figure_09", slide.figure)


def draw_reuse(counts, e, r, threshold):
    """Capacity reuse counts and downstream decisions, in slide points."""
    slide = canvas()
    actions = ["recompute" if v else "reuse" for v in r["updated"]]
    from math import cos, sin, pi

    def gear(name, cx, cy, r):
        def radial(theta, radius, dx=0, dy=0):
            return cx + r * radius * cos(theta) + dx, cy + r * radius * sin(theta) + dy
        def disc(label, radius, fill, stroke=None, dy=0):
            oval(slide, name + " / " + label, cx-r*radius,
                               cy-r*radius+dy, 2*r*radius, 2*r*radius,
                               fill, stroke, 0.7)
        def tooth(theta, dy=0):
            return [radial(theta + angle, radius, 0, dy) for angle, radius in
                    [(-.195, .69), (-.110, .968), (.102, .968), (.19, .69)]]
        for j in range(9):
            a = -pi/2 + j*2*pi/9
            poly(slide, f"{name} / tooth {j+1} depth",
                               tooth(a, r*.06), "28465B")
        disc("body depth", .804, "294958", dy=r*.06)
        for j in range(9):
            a = -pi/2+j*2*pi/9
            face = "8EAFBF" if sin(a)+cos(a)<0 else "698D9F"
            poly(slide, f"{name} / tooth {j+1}", tooth(a),
                               face, "385A6F", .7)
        disc("steel rim", .783, "779BAD", "345769")
        disc("raised boss highlight", .569, "B9D0D8", "BDCFD6")
        disc("bearing outer ring", .525, "385E74", "2E5366")
        disc("inner bore shadow", .349, "213B4A", "233D4D")
        disc("axle opening", .280, WHITE, dy=r*.02)

    def data_icon(name, x, y, width, height):
        front_w = width*.215
        side_w = width*.054
        rise = height*.043
        for j, fraction in enumerate([.42, .69, .95]):
            left = x+width*(.035 + j*.325)
            base = y+height*.97
            top = base - height*fraction
            prefix = f"{name} / bar {j+1}"
            box(slide, prefix+" front", left, top+rise, front_w,
                              base-top-rise, "297BB1", "225A7D", .6)
            poly(slide, prefix+" side",
                               [(left+front_w,top+rise),(left+front_w+side_w,top),
                                (left+front_w+side_w,base-rise),(left+front_w,base)],
                               "174C73", "215375", .6)
            poly(slide, prefix+" top",
                               [(left,top+rise),(left+side_w,top),
                                (left+front_w+side_w,top),(left+front_w,top+rise)],
                               "87BAD1", "4A8CAC", .6)

    def crew(name, x, y, w, h):
        # Each figure has a hard-hat shell and brim, shirt, collar and pocket.
        for j, (offset, drop, scale) in enumerate([(.02,.08,.86),(.59,.08,.86),(.286,0,1)]):
            gx, gy, gw, gh = x+w*offset, y+h*drop, w*.414*scale, h*scale
            prefix = f"{name} / technician {j+1}"
            def contour(label, points, fill, stroke=None):
                poly(slide, prefix+" / "+label,
                                   [(gx+gw*u,gy+gh*v) for u,v in points],
                                   fill, stroke, .55)
            def ellipse(label, u,v,s,t,fill,stroke=None):
                oval(slide, prefix+" / "+label,gx+gw*u,gy+gh*v,
                                   gw*s,gh*t,fill,stroke,.45)
            def seg(label, u,v,s,t,stroke,weight):
                line(slide,prefix+" / "+label,gx+gw*u,gy+gh*v,
                                   gx+gw*s,gy+gh*t,stroke,weight)
            contour("work jacket",[(.018,.99),(.049,.79),(.092,.717),(.30,.64),
                                    (.68,.64),(.906,.709),(.965,.79),(.992,.99)],
                    "24638C","214963")
            contour("left sleeve",[(.018,.99),(.049,.79),(.09,.722),(.21,.685),
                                    (.167,.99)],"347CAB")
            contour("right sleeve",[(.813,.684),(.916,.716),(.965,.79),(.992,.99),
                                     (.851,.99)],"194C72")
            contour("neck",[(.372,.548),(.63,.548),(.65,.662),(.505,.753),(.35,.661)],"E0AA7F")
            ellipse("left ear",.218,.385,.097,.15,"DCA278")
            ellipse("right ear",.689,.385,.097,.15,"DCA278")
            contour("face",[(.264,.286),(.736,.286),(.718,.487),(.663,.553),
                             (.565,.624),(.449,.634),(.344,.57),(.278,.492)],
                    "F1C5A0","BF9374")
            seg("left brow",.331,.404,.434,.407,"6F584E",.62)
            seg("right brow",.573,.406,.676,.403,"6F584E",.62)
            seg("nose",.511,.427,.493,.498,"C49470",.65)
            seg("mouth",.434,.55,.565,.55,"AB8067",.65)
            ellipse("hard hat shell",.213,.044,.573,.318,"2078AF","174F77")
            contour("hard hat ridge",[(.426,.060),(.455,.026),(.553,.026),(.585,.060),
                                       (.575,.248),(.446,.248)],"4A99C4","23658D")
            contour("hard hat brim",[(.149,.266),(.247,.248),(.760,.248),
                                      (.855,.272),(.851,.312),(.154,.312)],
                    "1B5E8C","1F5378")
            contour("left collar",[(.319,.625),(.496,.742),(.390,.79),(.267,.675)],"8FB1BF")
            contour("right collar",[(.676,.625),(.506,.742),(.599,.79),(.73,.675)],"6B96AE")
            seg("jacket placket",.50,.753,.50,.984,"153E62",.9)
            contour("chest pocket",[(.59,.825),(.779,.825),(.768,.902),(.681,.920),(.602,.899)],
                    "1D527A","235877")
            seg("pocket flap",.604,.838,.761,.838,"96B9CB",.75)

    legends = ["Valid reused", "Invalid reused", "Valid recomputed", "Invalid recomputed"]
    shades = [BLUE, ORANGE, TEAL, RED]
    for letter, heading, y, values in [
        ("a","Operating Decision Reuse",15,counts[0]),
        ("b","Completion Forecast Reuse",509,counts[1])
    ]:
        prefix = f"S3{letter}"
        x, w, h = 12, 795, 473
        box(slide,prefix+" frame",x,y,w,h,WHITE,NAVY,1.5)
        box(slide,prefix+" header band",x+1,y+1,w-2,54,PALE)
        txt(slide,prefix+" panel heading",f"({letter}) {heading}",x+7,y+4,w-14,44,22,True)
        left, top, baseline = 104, y+95, y+396
        span = baseline-top
        def vy(v):
            return baseline-span*v/140
        for tick in range(0,141,20):
            yy=vy(tick)
            line(slide,f"{prefix} y tick {tick}",left-6,yy,left,yy,INK,1.3)
            txt(slide,f"{prefix} y label {tick}",str(tick),left-52,yy-14,40,28,18)
        txt(slide,prefix+" count axis","Count",2,(top+baseline)/2-15,66,30,20,rotation=270)
        for code, cx, segments in [("RM-01",211,values),("RM-02",406,counts[2 if letter == "a" else 3])]:
            bar_w=112
            acc=0
            for label, v, shade in zip(legends,segments,shades):
                # Preserve exact segment geometry, including each zero-height segment.
                bar_top=vy(acc+v)
                box(slide,f"{prefix} {code} {label} ({v})",
                    cx-bar_w/2,bar_top,bar_w,span*v/140,shade)
                if v>3:
                    txt(slide,f"{prefix} {code} {label} label",str(v),
                        cx-bar_w/2,vy(acc+v/2)-14,bar_w,28,21,True,WHITE)
                elif v:
                    mid = vy(acc+v/2)
                    line(slide,f"{prefix} {v} leader",cx+bar_w/2,mid,
                         cx+bar_w/2+18,mid,"366B73",1.1)
                    txt(slide,f"{prefix} {code} {label} label",str(v),
                        cx+bar_w/2+20,mid-13,20,26,19,True)
                acc+=v
            txt(slide,f"{prefix} {code} total",str(acc),cx-45,vy(acc)-33,90,29,21,True)
            line(slide,f"{prefix} {code} tick",cx,baseline,cx,baseline+6,INK,1.3)
            txt(slide,f"{prefix} {code} category",code,cx-60,baseline+10,120,33,20)
        line(slide,prefix+" y axis",left,top,left,baseline,INK,1.6)
        line(slide,prefix+" x axis",left,baseline,495,baseline,INK,1.6)
        lx,ly,lw=513,y+140,278
        box(slide,prefix+" legend border",lx,ly,lw,173,WHITE,NAVY,.85,True)
        for idx,(label,shade) in enumerate(zip(legends,shades)):
            cy=ly+26+40*idx
            box(slide,f"{prefix} key {label}",lx+13,cy-8,32,16,shade)
            txt(slide,f"{prefix} legend {label}",label,lx+50,cy-14,lw-57,28,18)

    rx, ry, rw, rh=825,15,763,967
    box(slide,"S3c outer frame",rx,ry,rw,rh,WHITE,NAVY,1.5)
    box(slide,"S3c heading band",rx+1,ry+1,rw-2,54,PALE)
    txt(slide,"S3c title",f"(c) Decision Schematic for Event {e['id']}",
        rx+6,ry+4,rw-12,44,22,True)

    green_box,green_line = "E3F2E2","669565"
    red_box,red_line = "FBE6E7","C7757C"
    amber_box,amber_line = "FCECD7","C89049"
    tag_fill,tag_line="DBEAF5","5585AA"
    chain=[(e["id"],852),("RM-01",1114),("RM-02",1376)]
    for label,cx in chain:
        box(slide,"Event chain node "+label,cx,111,183,66,tag_fill,tag_line,1.2,True)
        txt(slide,"Event chain label "+label,label,cx+4,116,175,55,22,True)
    for (a,cx),(b,nx) in zip(chain,chain[1:]):
        line(slide,f"Event chain {a} to {b}",cx+184,144,nx-5,144,NAVY,2.0,arrow=True)

    def region(label,y,height):
        box(slide,label+" decision frame",841,y,731,height,None,"6397B9",1.15,True)
        box(slide,label+" title tab",862,y-19,139,43,tag_fill,tag_line,1.0,True)
        txt(slide,label+" title",label,867,y-16,129,36,21,True)

    region("RM-01",245,342)
    line(slide,"RM-01 horizontal divider",859,417,1552,417,"8FADC3",1.1,True)
    gear("RM-01 / steel gear",910,335,51)
    data_icon("RM-01 / capacity columns",863,461,91,89)
    line(slide,"RM-01 gear divider",974,285,974,391,"54728A",1.1)
    line(slide,"RM-01 forecast divider",974,450,974,554,"54728A",1.1)
    txt(slide,"Capacity lower bound",f"Updated lower bound on\ncapacity = {e['q']-e['unc']:.3f}",
        981,282,309,62,20)
    txt(slide,"Capacity threshold",f"Threshold = {threshold:.2f}",981,348,309,38,20)
    txt(slide,"Original forecast error",f"Original completion\nforecast error = {abs(r['fresh'][1]-r['old'][1])} min",
        981,449,309,63,20)
    txt(slide,"Forecast tolerance",f"Tolerance = {r['tol']} min",981,516,309,38,20)
    for yy,text_,fill,edge in [
            (280,f"Operating\ndecision: {actions[0]}",green_box,green_line),
            (449,f"Completion forecast:\n{actions[1]}",red_box,red_line)]:
        line(slide,"Judgment arrow "+str(yy),1292,yy+56,1322,yy+56,NAVY,2.3,arrow=True)
        box(slide,"RM-01 result card "+str(yy),1332,yy,224,111,fill,edge,1.1,True)
        txt(slide,"RM-01 result "+str(yy),text_,1338,yy+8,212,95,20,True)

    region("RM-02",637,324)
    for yy,text_,fill,edge in [
            (667,f"Operating decision: {actions[2]}",green_box,green_line),
            (766,f"Completion forecast: {actions[3]}",green_box,green_line),
            (865,f"Crew reservation: {'adjust' if r['plan'][1] != e['old_b'] else 'retain'}",amber_box,amber_line)]:
        box(slide,"RM-02 result card "+str(yy),1001,yy,551,68,fill,edge,1.1,True)
        txt(slide,"RM-02 "+text_,text_,1007,yy+5,539,58,21,True)
    gear("RM-02 / steel gear",922,701,39)
    data_icon("RM-02 / capacity columns",882,765,79,70)
    crew("RM-02 / maintenance crew",852,859,132,78)

    figure("figure_10", slide.figure)


def _s45_yaxis(slide, name, left, top, bottom, ticks, fmt, title, title_x):
    """Draw vertical ticks in data units. Rotation is around the text box center."""
    low, high = ticks[0], ticks[-1]
    def ypos(value):
        return bottom - (value - low) * (bottom - top) / (high - low)
    line(slide, f"{name} | vertical axis", left, top, left, bottom, INK, 1.8)
    for tick in ticks:
        y = ypos(tick)
        line(slide, f"{name} | y tick {fmt(tick)}", left - 7, y, left, y, INK, 1.25)
        txt(slide, f"{name} | y tick label {fmt(tick)}", fmt(tick),
            left - 67, y - 14, 55, 28, 18)
    center_y = (top + bottom) / 2
    # The horizontal box becomes tall and narrow after a 270 degree rotation.
    txt(slide, f"{name} | y title", title, title_x - 163, center_y - 15,
        326, 30, 19, rotation=270)
    return ypos


def _s45_xaxis(slide, name, left, right, bottom, categories, axis_title):
    step = (right - left) / len(categories)
    centers = [left + step * (index + .5) for index in range(len(categories))]
    line(slide, f"{name} | horizontal axis", left, bottom, right, bottom, INK, 1.8)
    for x, category in zip(centers, categories):
        line(slide, f"{name} | x tick {category}", x, bottom, x, bottom + 7, INK, 1.25)
        txt(slide, f"{name} | x label {category}", category,
            x - step / 2, bottom + 9, step, 27, 18)
    txt(slide, f"{name} | x title", axis_title, left, bottom + 39, right - left, 30, 19)
    return centers


def _s45_bars(slide, name, centers, values, colors, bottom, ypos, width, fmt):
    for index, (x, value, color) in enumerate(zip(centers, values, colors), 1):
        top = ypos(value)
        if top == bottom:
            # An editable zero-height mark at the origin, with no invented value.
            line(slide, f"{name} | zero bar {index}", x - width / 2, bottom,
                 x + width / 2, bottom, color, 1.7)
        else:
            box(slide, f"{name} | bar {index} ({fmt(value)})", x - width / 2, top,
                width, bottom - top, fill=color)
        txt(slide, f"{name} | value {index}", fmt(value),
            x - width / 2 - 8, top - 34, width + 16, 30, 20, True)


def draw_intensity(data, savings, full_cost):
    slide = canvas()
    groups = ["Zero", "(0, 0.10]", "(0.10, 0.25]", ">0.25"]
    category_colors = ["639EDD", BLUE, TEAL, ORANGE]
    for left, width, key in [(14, 790, "a"), (816, 770, "b")]:
        box(slide, f"S4{key} | panel", left, 15, width, 972, WHITE, NAVY, 1.9, radius=True)
    txt(slide, "S4a | heading", "(a) Replanning Cost vs. Production\nDisturbance Intensity",
        28, 32, 762, 86, 22, True)
    txt(slide, "S4b | heading", "(b) P95 Time Spent Solving\nand Checking",
        830, 32, 742, 86, 22, True)

    x1, x2, ytop, base = 133, 779, 176, 623
    ypos = _s45_yaxis(slide, "S4a", x1, ytop, base, list(range(0, 25, 4)), str,
                      "Replanning Cost (units)", 51)
    centers = _s45_xaxis(slide, "S4a", x1, x2, base, groups, "Production Disturbance Intensity")
    line(slide, "S4a | full-graph benchmark", x1 + 1, ypos(full_cost),
         x2, ypos(full_cost), RED, 2, dash=True)
    txt(slide, "S4a | benchmark label", f"Full-graph recomputation = {full_cost:g} units",
        x1 + 9, ypos(full_cost) - 43, x2 - x1 - 18, 32, 20, True)
    _s45_bars(slide, "S4a", centers, [float(g["cost_mean"]) for g in data], category_colors,
              base, ypos, 112, lambda v: "0" if v == 0 else f"{v:.2f}")

    # Repeat the category key in the table, as its column spacing differs from the plot.
    table_rows = [
        ["Metric", *groups],
        ["Number of Cases", *[g["n"] for g in data]],
        ["Events Requiring Expansion\nto Both Maintenance Tasks", *[g["expanded"] for g in data]],
    ]
    widths = [286, 106, 114, 134, 106]
    row_top = 741
    for row, (values, height) in enumerate(zip(table_rows, [57, 66, 90])):
        x = 36
        for col, (value, width) in enumerate(zip(values, widths)):
            label = f"S4a | table row {row + 1} column {col + 1}"
            fill = PALE if row == 0 or col == 0 else WHITE
            box(slide, f"{label} | cell", x, row_top, width, height, fill, NAVY, .9)
            txt(slide, f"{label} | text", value, x + 3, row_top + 2,
                width - 6, height - 4, 17 if col == 0 or row == 0 else 20, col == 0 or row == 0)
            x += width
        row_top += height

    stats = [
        f"Mean savings = {savings['mean_saving']:.2f} units per case",
        f"95% interval = {savings['shift_bootstrap_95'][0]:.2f}–{savings['shift_bootstrap_95'][1]:.2f} units",
        f"Exogenous-change cases mean cost = {savings['disturbed_cost_per_case']:.2f} units",
        f"Reduction vs full recomputation = {savings['disturbed_reduction_pct']:.1f}%",
    ]
    box(slide, "S4b | summary background", 848, 131, 706, 190, PALE, "7BA8CE", 1.1, radius=True)
    for row, value in enumerate(stats):
        txt(slide, f"S4b | summary {row + 1}", value, 862, 142 + 41 * row, 678, 38, 19,
            False)
    times = [g["p95_ms"] for g in data]
    step = max(.02, math.ceil(max(times) / 7.6 / .01) * .01)
    x1, x2, ytop, base = 951, 1560, 383, 867
    ypos = _s45_yaxis(slide, "S4b", x1, ytop, base, [i * step for i in range(9)],
                      lambda v: f"{v:.3f}", "P95 Time (ms)", 852)
    centers = _s45_xaxis(slide, "S4b", x1, x2, base, groups, "Production Disturbance Intensity")
    _s45_bars(slide, "S4b", centers, times, category_colors,
              base, ypos, 105, lambda v: f"{v:.3f}")


    figure("figure_11", slide.figure)


def draw_tolerance(data):
    slide = canvas()
    categories = [f"{r['tolerance']} min" for r in data]
    axis_title = "Completion Forecast Tolerance"
    for name, x, y, w, h in [("a", 14, 14, 782, 475), ("b", 807, 14, 779, 475),
                              ("c", 14, 503, 1572, 484)]:
        box(slide, f"S5{name} | panel", x, y, w, h, WHITE, NAVY, 1.65)
    txt(slide, "S5a | heading", "(a) Reuse Count vs. Completion Forecast Tolerance",
        27, 24, 756, 50, 22, True)
    txt(slide, "S5b | heading", "(b) Mean Replanning Cost vs. Completion Forecast Tolerance",
        818, 24, 757, 50, 22, True)
    txt(slide, "S5c | heading", "(c) Events Passing Whole-Graph Verification vs. Tolerance",
        28, 512, 1544, 50, 22, True)

    x1, x2, top, base = 126, 777, 103, 391
    ypos = _s45_yaxis(slide, "S5a", x1, top, base, list(range(300, 481, 20)),
                      str, "Reuse Count (out of 480)", 49)
    centers = _s45_xaxis(slide, "S5a", x1, x2, base, categories, axis_title)
    _s45_bars(slide, "S5a", centers, [r["reuse_count"] for r in data],
              [BLUE] * 5, base, ypos, 90, str)
    box(slide, "S5a | incorrect reuse box", 162, 112, 242, 41, PALE, BLUE, 1.1, radius=True)
    txt(slide, "S5a | incorrect reuse note", "Incorrect reuse = " + ", ".join(map(str, sorted({r["incorrect_reuses"] for r in data}))), 167, 114, 232, 37, 18, True)

    x1, x2 = 919, 1565
    ypos = _s45_yaxis(slide, "S5b", x1, top, base, [i / 2 for i in range(11, 19)],
                      lambda v: f"{v:.1f}", "Mean Replanning Cost (units)", 845)
    centers = _s45_xaxis(slide, "S5b", x1, x2, base, categories, axis_title)
    values = [float(r["cost_mean"]) for r in data]
    pts = [(x, ypos(value)) for x, value in zip(centers, values)]
    poly(slide, "S5b | area beneath cost curve", pts + [(centers[-1], base - 1),
         (centers[0], base - 1)], "DCF2EF")
    for i, ((xa, ya), (xb, yb)) in enumerate(zip(pts, pts[1:]), 1):
        line(slide, f"S5b | cost segment {i}", xa, ya, xb, yb, "138675", 2.6)
    for i, ((x, y), value) in enumerate(zip(pts, values), 1):
        oval(slide, f"S5b | cost marker {i}", x - 6, y - 6, 12, 12, WHITE, "138675", 2)
        txt(slide, f"S5b | cost value {i}", f"{value:.2f}", x - 49, y - 41, 98, 30, 20, True)

    x1, x2, top, base = 141, 1391, 610, 893
    ypos = _s45_yaxis(slide, "S5c", x1, top, base, list(range(80, 121, 5)),
                      str, "Events Passing Verification", 53)
    centers = _s45_xaxis(slide, "S5c", x1, x2, base, categories, axis_title)
    values = [r["verified"] for r in data]
    _s45_bars(slide, "S5c", centers, values, [ORANGE] * 5, base, ypos, 150, str)
    for i, (index, x, y, count) in enumerate([(j, 896 if j == 3 else 1254, 563 if j == 3 else 614, r["feasible_failures"]) for j, r in enumerate(data) if r["feasible_failures"]], 1):
        w, h = 303, 69
        box(slide, f"S5c | annotation {i} background", x, y, w, h, "FFF4E9",
            "D47423", 1.1, radius=True)
        txt(slide, f"S5c | annotation {i}", f"{count} failed cases had feasible\nsolutions within the window",
            x + 5, y + 3, w - 10, h - 6, 18, True)
        # Aim at the right shoulder of the bar, away from the centered numeric label.
        line(slide, f"S5c | arrow to {categories[index]}", x + w * .67, y + h,
             centers[index] + 49, ypos(values[index]) - 2, "CB6A1D", 1.7, arrow=True)

    figure("figure_12", slide.figure)
