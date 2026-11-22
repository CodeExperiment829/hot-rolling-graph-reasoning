(function () {
  'use strict';
  const fs = require('node:fs');
  const path = require('node:path');
  const inputPath = path.join(__dirname, 'Data', 'full_line.json');
  const {config, stands: finishers, capacityUpdate} = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
  function overlaps(a,b) {return a[0]<b[1]&&b[0]<a[1];}

  function timesAt(speed) {
    const rate=config.widthM*(config.exitGaugeMm/1000)*speed*config.density*60/1000;
    const tonnesPerStrip=config.massT/config.strips;
    const gaps=(config.strips-1)*config.gapSec/60;
    // entryMinute marks the start of strip 1 at F7, the tonnage measurement plane.
    const head=config.entryMinute+(config.massT-tonnesPerStrip)/rate+gaps;
    const tail=config.entryMinute+config.massT/rate+gaps;
    // Reserve the complete last strip at the selected downstream coiler.
    const coilWindow=[Math.floor(head+config.coilTravelMin),Math.ceil(tail+config.coilTravelMin)];
    return {rate,tail:Math.ceil(tail),coilWindow,coilEnd:coilWindow[1],release:coilWindow[1]+config.isolationMin};
  }
  function planMaintenance(release,fixed=[]) {
    // Two jobs share one crew. Among feasible schedules, minimize restart,
    // then pick the earliest F4 start to make equal optima reproducible.
    const latest=config.deadline-config.restartMin;
    const choices=config.jobs.map(job=>{
      const booked=fixed.find(b=>b.id===job.id);
      const starts=booked?[booked.start]:Array.from({length:Math.max(0,latest-release-job.duration+1)},(_,i)=>release+i);
      return starts.map(start=>({id:job.id,start,end:start+job.duration})).filter(b=>
        b.start>=release&&b.end<=latest&&!overlaps([b.start,b.end],config.crewBlock));
    });
    let best=null, feasibleCount=0;
    for(const a of choices[0]) for(const b of choices[1]) {
      if(overlaps([a.start,a.end],[b.start,b.end]))continue;
      const restart=Math.max(a.end,b.end)+config.restartMin;
      feasibleCount++;
      if(!best||restart<best.restart||(restart===best.restart&&a.start<best.f4Start)) {
        best={restart,f4Start:a.start,bookings:[a,b].sort((u,v)=>u.start-v.start)};
      }
    }
    return {feasible:!!best,feasibleCount,bookings:best?best.bookings:[],restart:best?best.restart:null};
  }
  function evaluatePorts(alternatives) {
    const otherLimits = finishers.filter(s => s.id !== capacityUpdate.stand).map(s => s.port.exitLimit);
    return alternatives.map(p=>{
      const test=timesAt(Math.min(p.exitLimit,config.requestedSpeed,config.coolingRange[1],...otherLimits));
      const verdict=p.quality<config.portQualityMin?'quality':p.validUntil<test.tail?'expired':'bound';
      return {...p,verdict};
    });
  }
  function validateBookings(result,release) {
    if(!result.feasible || result.bookings.length!==config.jobs.length)return false;
    const intervals=[];
    for(const job of config.jobs) {
      const booking=result.bookings.find(b=>b.id===job.id);
      if(!booking || booking.start<release || booking.end-booking.start!==job.duration)return false;
      const span=[booking.start,booking.end];
      if(overlaps(span,config.crewBlock)||intervals.some(i=>overlaps(span,i)))return false;
      intervals.push(span);
    }
    return result.restart===Math.max(...intervals.map(i=>i[1]))+config.restartMin &&
      result.restart<=config.deadline;
  }
  function solve(alternatives,prior) {
    const portTrials=evaluatePorts(alternatives);
    const chosen=portTrials.find(p=>p.verdict==='bound');
    const stands=finishers.map((s,i)=>{
      const affected = s.id === capacityUpdate.stand;
      if(prior&&!affected)return prior.stands[i];
      const gaugeMm=s.gaugeMm;
      const port=affected?chosen:s.port;
      const localLimit=port.exitLimit*config.exitGaugeMm/gaugeMm;
      return {id:s.id,gaugeMm,localLimit,exitLimit:Math.round(localLimit*gaugeMm/config.exitGaugeMm*100)/100,
        port:port.id,quality:port.quality,validUntil:port.validUntil};
    });
    const tightest=stands.reduce((a,b)=>a.exitLimit<=b.exitLimit?a:b);
    const speed=Math.min(tightest.exitLimit,config.requestedSpeed,config.coolingRange[1]);
    const timing=timesAt(speed);
    const coiler=config.coilers.find(c=>c.booked.every(reservation=>!overlaps(reservation,timing.coilWindow)));
    // On feedback release the affected F4 job first. Expand to the shared-crew
    // F6 job only when its frozen booking makes the smaller solve infeasible.
    const firstPass=prior?planMaintenance(timing.release,prior.bookings.filter(b=>b.id==='F6')):null;
    const schedule=firstPass?.feasible?firstPass:planMaintenance(timing.release);
    const verified=stands.every(s=>s.quality>=config.portQualityMin&&s.validUntil>=timing.tail&&
      speed*config.exitGaugeMm/s.gaugeMm<=s.localLimit+1e-9)&&
      speed>=config.coolingRange[0]&&speed<=config.coolingRange[1]&&!!coiler&&validateBookings(schedule,timing.release);
    return {stands,portTrials,firstPass,bottleneck:tightest.id,speed,coiler:coiler?.id||null,...timing,...schedule,feasible:verified};
  }
  const base=solve(capacityUpdate.baseline),revised=solve(capacityUpdate.revised,base);
  const restricted=revised.firstPass;
  process.stdout.write(JSON.stringify({config,base,revised,restricted}));
})();
