/* Segment a complete gesture, classify once, and keep its honest outcome. */
class AutoMotion {
  constructor(send,notify=()=>{}) { this.send=send;this.notify=notify;this.epoch=0;this.reset(); }
  reset() {
    this.epoch++;this.frames=[];this.segment=[];this.phase='idle';this.busy=false;
    this.detected=null;this.anchor=null;this.lastPrediction=null;this.steady=null;this.kind=null;this.lostShapeAt=null;this.lastActive=-Infinity;this.finishedAt=-Infinity;
  }
  shape(frame) {
    const p=frame.points.map(v=>[v[0]-frame.points[0][0],(v[1]-frame.points[0][1])/frame.aspect]);
    const scale=Math.max(...p.map(v=>Math.hypot(...v)),1e-6);
    return p.map(v=>v.map(c=>c/scale));
  }
  shapeDifference(a,b) {return Math.sqrt(a.reduce((sum,p,i)=>sum+(p[0]-b[i][0])**2+(p[1]-b[i][1])**2,0)/21);}
  movement(frames=this.frames) {
    if(frames.length<2)return 0;
    const first=frames[0],p=first.points;
    const scale=Math.max(...p.map(v=>Math.hypot(v[0]-p[0][0],(v[1]-p[0][1])/first.aspect)));
    if(scale<1e-6)return 0;
    return Math.max(...[0,8,20].map(index=>{
      const xs=frames.map(f=>f.points[index][0]),ys=frames.map(f=>f.points[index][1]/f.aspect);
      return Math.hypot(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys))/scale;
    }));
  }
  handKind(frame,expected=null) {
    const p=frame.points;
    const distance=i=>Math.hypot(p[i][0]-p[0][0],(p[i][1]-p[0][1])/frame.aspect,p[i][2]-p[0][2]);
    const ratios=[8,12,16,20].map((tip,i)=>distance(tip)/Math.max(distance([6,10,14,18][i]),1e-6));
    if(expected==='little')return ratios[3]>.95&&Math.max(...ratios.slice(0,3))<1.2?'little':null;
    if(expected==='index')return ratios[0]>.9&&Math.max(...ratios.slice(1))<1.2&&ratios[0]-Math.max(...ratios.slice(1))>.1?'index':null;
    if(ratios[3]>1.15&&Math.max(...ratios.slice(0,3))<1.05)return 'little';
    if(ratios[0]>.9&&Math.max(...ratios.slice(1))<1.05&&ratios[0]-Math.max(...ratios.slice(1))>.12)return 'index';
    return null;
  }
  staticQ(result,aspect) {
    if(result.status!=='ok'||result.label!=='Q'||result.confidence<.6)return false;
    const p=result.landmarks;
    const distance=i=>Math.hypot(p[i][0]-p[0][0],(p[i][1]-p[0][1])/aspect);
    const scale=Math.max(...p.map((_,i)=>distance(i)),1e-6);
    return (p[8][1]-p[0][1])/aspect>.1*scale&&distance(20)<1.05*distance(18);
  }
  current() {return ['recognized','uncertain'].includes(this.phase)?this.detected:null;}
  reading() {return this.phase!=='idle'&&this.phase!=='recognized';}
  recoverStatic(result,frame,now) {
    const shape=this.shape(frame);
    const steady=this.steady;
    if(result.status!=='ok'||!result.label) { this.steady=null;return false; }
    if(!steady||steady.label!==result.label||this.shapeDifference(shape,steady.shape)>.08||
       this.movement([steady.frame,frame])>.12) {
      this.steady={label:result.label,shape,frame,since:now};return false;
    }
    const unresolved=['uncertain','incomplete','error','untrained'].includes(this.phase);
    const zEnding=this.phase==='recognized'&&this.detected?.label==='Z'&&this.kind==='index'&&result.label==='G'&&this.anchor;
    const shapeChange=this.anchor?this.shapeDifference(shape,this.anchor):0;
    // Preserve a confirmed Z ending hold, but let a deliberate G pose recover.
    if(zEnding&&shapeChange<.10)return false;
    const changed=this.phase==='recognized'&&this.anchor&&shapeChange>.08;
    if((unresolved||changed)&&now-steady.since>=900) {
      this.reset();this.frames=[frame];this.finishedAt=now;return true;
    }
    return false;
  }
  feedback() {
    if(this.phase==='recording')return 'Reading motion — complete the gesture, then briefly hold still';
    if(this.phase==='classifying')return 'Checking the completed gesture…';
    if(this.phase==='incomplete')return 'Motion incomplete — hold a letter steady or retry the gesture';
    if(this.phase==='error')return 'Motion request failed — hold a letter steady to continue';
    if(this.phase==='untrained')return 'Motion classifier is not trained';
    const p=this.lastPrediction;
    return p&&Number.isFinite(p.score)?`Motion uncertain · Closest ${p.candidate||'background'} · ${(p.score*100).toFixed(1)}% / 70% required. Hold a letter steady or retry the gesture.`:'Motion uncertain — hold a letter steady or retry the gesture';
  }
  incomplete(frame,now) {
    this.phase='incomplete';this.anchor=this.shape(frame);this.finishedAt=now;
    this.segment=[];this.notify(this.feedback());
  }
  async finish(frame,now) {
    const clip=this.segment.slice(),job=this.epoch;
    this.segment=[];this.phase='classifying';this.anchor=this.shape(frame);this.finishedAt=now;this.busy=true;
    this.notify(this.feedback());
    try {
      const p=await this.send(clip);if(job!==this.epoch)return;
      this.lastPrediction={candidate:p.candidate||p.label,score:p.confidence,at:now};
      this.detected=null;
      if(p.status==='untrained')this.phase='untrained';
      else if(p.status==='ok'&&['J','Z'].includes(p.label)&&(p.method==='trajectory'||p.confidence>=.7)) {
        this.phase='recognized';this.detected={label:p.label,score:p.confidence,accepted:true,method:p.method};
      }else {
        this.phase='uncertain';
        if(['J','Z'].includes(p.candidate))this.detected={label:p.candidate,score:p.confidence,accepted:false};
      }
      this.notify(this.phase==='recognized'?`Completed motion: ${p.label}`:this.feedback());
    }catch(error){if(job===this.epoch){this.phase='error';this.notify(this.feedback());}}
    finally{if(job===this.epoch)this.busy=false;}
  }
  async observe(result,aspect,enabled,now=performance.now()) {
    if(!enabled){this.reset();return;}
    if(!result.landmarks){
      const last=this.frames.at(-1);
      if(last&&['recording','classifying'].includes(this.phase)&&now-last.time<=500)return;
      this.reset();return;
    }
    // A transient static Q guess must not erase an already-started Z trace.
    if(this.phase==='idle'&&this.staticQ(result,aspect)){this.reset();return;}
    const previous=this.frames.at(-1);
    const frame={points:result.landmarks,time:now,aspect};
    frame.kind=this.handKind(frame)||(result.status==='ok'&&result.label==='I'?'little':null);
    if(previous&&now-previous.time>750) {
      if(this.phase==='recording'){this.incomplete(frame,now);this.frames=[frame];return;}
      this.reset();
    }
    this.frames.push(frame);this.frames=this.frames.filter(f=>now-f.time<=1000).slice(-120);
    if(this.phase==='classifying')return;
    if(this.recoverStatic(result,frame,now))return;
    if(this.phase!=='idle'&&this.phase!=='recording'&&this.anchor&&this.shapeDifference(this.shape(frame),this.anchor)>.25) {
      this.phase='idle';this.detected=null;this.anchor=null;this.lastPrediction=null;
      this.finishedAt=now;this.frames=[frame];return;
    }
    if(this.phase==='recording') {
      if(this.kind&&this.handKind(frame,this.kind)!==this.kind&&!(this.kind==='little'&&result.status==='ok'&&result.label==='I')){
        if(this.lostShapeAt===null)this.lostShapeAt=now;
        if(now-this.lostShapeAt>=350){
          const last=this.segment.at(-1);
          if(this.segment.length>=6&&last.time-this.segment[0].time>=350)await this.finish(last,now);
          else this.incomplete(frame,now);
        }
        return;
      }
      this.lostShapeAt=null;
      this.segment.push(frame);
      if(previous&&this.movement([previous,frame])>.08)this.lastActive=now;
      const span=now-this.segment[0].time;
      // Wait for a real ending hold; never classify an ongoing timeout as complete.
      if(now-this.lastActive>=450&&this.segment.length>=6&&span>=350)await this.finish(frame,now);
      else if(span>4500||this.segment.length>=120)this.incomplete(frame,now);
      return;
    }
    const kind=frame.kind;
    const recent=this.frames.filter(f=>f.time>this.finishedAt&&(!kind||f.kind===kind));
    if(kind&&recent.length>=3&&this.movement(recent)>.3) {
      this.phase='recording';this.detected=null;this.lastPrediction=null;this.anchor=null;this.kind=kind;this.lostShapeAt=null;
      this.segment=recent.slice();this.lastActive=now;this.notify(this.feedback());
    }
  }
}
if(typeof window!=='undefined')window.AutoMotion=AutoMotion;
if(typeof module!=='undefined')module.exports=AutoMotion;
