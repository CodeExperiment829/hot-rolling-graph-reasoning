"""Full-line timing and crew occupancy for the baseline and updated speed limit."""
import json
import shutil
import subprocess

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

from publishing import ROOT, figure


def clock(minute):
    return f"{10+minute//60:02d}:{minute%60:02d}"


def gantt(config, base, revised):
    fig, ax = plt.subplots(figsize=(10.8, 3.6), layout="constrained")
    color = {"F4":"#427994", "F6":"#58a18f"}
    for y, s in enumerate([revised, base]):
        lo, hi = config["crewBlock"]
        ax.barh(y,hi-lo,left=lo,height=.46,color="#efdab9",hatch="//",edgecolor="#ac845a")
        ax.text((hi+lo)/2,y,"Crew\nbooked",ha="center",va="center",fontsize=9)
        for job in s["bookings"]:
            t, end = job["start"],job["end"]
            ax.barh(y, end-t,left=t,height=.46,color=color[job["id"]])
            ax.text((end+t)/2,y,f"{job['id']}\n{clock(t)}–{clock(end)}",ha="center",va="center",color="white",fontsize=9)
        ax.plot(s["restart"],y,marker="D",color="#313c49",ms=6)
        ax.annotate(f"Restart {clock(s['restart'])}",(s["restart"],y),xytext=(0,20),textcoords="offset points",ha="center")
    ax.set_yticks([0,1],["Revised","Baseline"])
    ax.set_xticks(range(base["release"]-2,config["deadline"]+1,2),[clock(i) for i in range(base["release"]-2,config["deadline"]+1,2)])
    ax.set_ylim(-.55,1.6)
    ax.set_title("(c)  Maintenance sequence and production restart", loc="left",fontweight="bold")
    ax.spines[["top","right","left"]].set_visible(False)
    fixed=next(job for job in base["bookings"] if job["id"]=="F6")
    obstacles=[tuple(config["crewBlock"]), (fixed["start"],fixed["end"])]
    latest=config["deadline"]-config["restartMin"]
    free=longest=0
    for minute in range(revised["release"],latest):
        free=free+1 if all(not (a<=minute<b) for a,b in obstacles) else 0
        longest=max(free,longest)
    required=next(job["duration"] for job in config["jobs"] if job["id"]=="F4")
    ax.set_xlabel(f"Production clock\nKeeping the F6 reservation leaves a {longest} min gap. F4 needs {required} min.")
    figure("figure_05",fig)


def choices(config, revised):
    latest = config["deadline"] - config["restartMin"]
    start, end = config["crewBlock"]
    durations = [j["duration"] for j in config["jobs"]]
    slots = [[m for m in range(revised["release"],latest-d+1) if m+d <= start or m >= end] for d in durations]
    f4, f6 = slots
    da,db = durations
    grid = [[max(0,min(a+da,b+db)-max(a,b)) for b in f6] for a in f4]
    restarts = [(i,j,max(a+da,b+db)+config["restartMin"]) for i,a in enumerate(f4)
                for j,b in enumerate(f6) if grid[i][j] == 0]
    if len(restarts) != revised["feasibleCount"] or min(v for _,_,v in restarts) != revised["restart"]:
        raise ValueError("Independent crew matrix disagrees with scheduler")
    return f4,f6,grid,restarts


def feedback(config,base,new,rows,cols,grid,restarts):
    fig = plt.figure(figsize=(13,6.8),layout="constrained")
    gs=fig.add_gridspec(2,2,width_ratios=[1.7,1],height_ratios=[1.65,1])
    graph=fig.add_subplot(gs[0,:])
    graph.axis("off")
    graph.set(xlim=(-.35,4.7),ylim=(-.65,2))
    graph.set_title("(b)  Tasks considered for replanning after the F4 speed restriction",loc="left",fontweight="bold")
    def node(x,y,label,state,dy=.15):
        shape,col = {"update":("o","#236db0"),"reuse":("o","#438b37"),"fixed":("s","#73828c")}[state]
        graph.plot(x,y,marker=shape,markeredgecolor=col,mfc="white" if state=="reuse" else col,ms=7,zorder=5)
        graph.text(x,y+dy,label,ha="center",va="bottom" if dy>0 else "top",fontsize=9)
    def edge(a,b,shared=False):
        graph.annotate("",xy=b,xytext=a,arrowprops={"arrowstyle":"-" if shared else "-|>","color":"#71828c","linestyle":"--" if shared else "-","shrinkA":5,"shrinkB":5})
    for i in range(4): edge((i,1.3),(i+1,1.3))
    limit=next(s for s in new["stands"] if s["id"]=="F4")["exitLimit"]
    titles=[f"F4 capacity limit\n{limit} m/s",f"Exit speed setpoint\n{base['speed']} → {new['speed']} m/s",
            f"Last strip leaves F7\n{clock(base['tail'])} → {clock(new['tail'])}",
            f"Last strip coiled\n{clock(base['coilEnd'])} → {clock(new['coilEnd'])}",
            f"Line released\n{clock(base['release'])} → {clock(new['release'])}"]
    for i,s in enumerate(titles): node(i,1.3,s,"update")
    node(0,.47,"F6 capacity retained","reuse",-.12); edge((0,.47),(1,1.3))
    node(1,.47,"Continue rolling","reuse"); edge((1,1.3),(1,.47))
    node(1,-.25,f"Cooling window\n{config['coolingRange'][0]}–{config['coolingRange'][1]} m/s","fixed",-.12);edge((1,-.25),(1,.47))
    node(2.55,.47,f"Retain {new['coiler']}","reuse");edge((3,1.3),(2.55,.47))
    node(2.55,-.25,"Coiler calendar","fixed",-.12);edge((2.55,-.25),(2.55,.47))
    node(4,.47,"Shared crew  "+"–".join(map(clock,config["crewBlock"])),"fixed")
    graph.text(3.52,1.40,f"{config['isolationMin']} min isolation",fontsize=8,ha="center")
    legend = [Line2D([],[],marker="o",lw=0,color="#236db0",label="Recompute or reschedule"),
              Line2D([],[],marker="o",lw=0,mfc="white",mec="#438b37",label="Reuse result"),
              Line2D([],[],marker="s",lw=0,color="#73828c",label="Fixed condition"),
              Line2D([],[],color="#71828c",lw=1,label="Data dependency"),
              Line2D([],[],color="#71828c",lw=1,ls="--",label="Shared resource")]
    graph.legend(handles=legend,ncols=5,frameon=False,loc="lower center",
                 bbox_to_anchor=(.5,-.13),fontsize=8)
    for i,(loc,job) in enumerate([(3.56,"F4"),(4.47,"F6")]):
        old=next(j["start"] for j in base["bookings"] if j["id"]==job)
        changed=next(j["start"] for j in new["bookings"] if j["id"]==job)
        edge((4,1.3),(loc,-.25));edge((4,.47),(loc,-.25),True)
        node(loc,-.25,f"{job} maintenance\n{clock(old)} → {clock(changed)}","update",-.12)
    ax=fig.add_subplot(gs[1,0]); dot=fig.add_subplot(gs[1,1])
    cmap=LinearSegmentedColormap.from_list("overlap",[(0,"white"),(.66,"#fde8d1"),(1,"#e7a45f")])
    ax.set_xlim(-.5,len(cols)-.5)
    ax.set_ylim(len(rows)-.5,-.5)
    peak=max(max(row) for row in grid) or 1
    for i,row in enumerate(grid):
        for j,v in enumerate(row):
            ax.add_patch(Rectangle((j-.5,i-.5),1,1,fc=cmap(v/peak),ec="#d8d8d8",lw=.7))
            ax.text(j,i,str(v),ha="center",va="center")
    i,j,_=min(restarts,key=lambda t:t[2]);ax.add_patch(Rectangle((j-.48,i-.48),.96,.96,fill=False,ec="#236db0",lw=2))
    original=next(job["start"] for job in base["bookings"] if job["id"]=="F6")
    ax.set_xticks(range(len(cols)),[("Original slot\n" if t==original else "")+clock(t) for t in cols]);ax.xaxis.tick_top()
    ax.set_yticks(range(len(rows)),list(map(clock,rows)))
    ax.set_xlabel("F6 start time");ax.set_ylabel("F4 start time")
    ax.set_title("(c)  Shared-crew overlap (min)",loc="left",fontweight="bold",pad=10)
    for i,j,t in restarts:
        dot.plot(t,i,"o",ms=8,mec="#236db0",mfc="#236db0" if t==new["restart"] else "white")
    dot.set_ylim(len(rows)-.5,-.5);dot.set_yticks(range(len(rows)),[]);dot.grid(axis="y",alpha=.35)
    ts=sorted({v for _,_,v in restarts});dot.set_xticks(ts,list(map(clock,ts)))
    dot.axvline(config["deadline"],ls="--",color="#717b80")
    dot.set_xlabel("Production restart time");dot.set_title("Conflict-free schedules",fontweight="bold")
    figure("figure_07",fig)


def run():
    node=shutil.which("node")
    if not node: raise RuntimeError("Node.js is required for the full-line scheduler")
    result=json.loads(subprocess.check_output([node, str(ROOT/"line_solver.js")],cwd=ROOT, encoding="utf-8"))
    config,base,new=[result[k] for k in ("config","base","revised")]
    if not (base["feasible"] and new["feasible"]): raise ValueError("Full-line verification failed")
    a,b,grid,restarts=choices(config,new)
    gantt(config,base,new)
    feedback(config,base,new,a,b,grid,restarts)
    def summary(s):
        return {k:s[k] for k in ("speed","coiler","release","tail","coilEnd","bookings","restart","feasible","feasibleCount")}
    return {"baseline":summary(base),"revised":summary(new),"fixed_F6_feasible":result["restricted"]["feasible"],
            "f4_start":a,"f6_start":b,"crew_overlap_min":grid,"conflict_free_restart":[v for _,_,v in restarts]}

