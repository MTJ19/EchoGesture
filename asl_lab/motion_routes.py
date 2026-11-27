import json,re,uuid
from pathlib import Path
import joblib,numpy as np
from flask import Blueprint,abort,current_app,request,jsonify
from .motion import motion_features,MOTION_VERSION,MOTION_LABELS
from .motion_path import path_evidence


def motion_routes(root):
    routes=Blueprint('motion',__name__)
    @routes.post('/api/motion')
    def sequence():
        payload=request.get_json(silent=True)
        if not isinstance(payload,dict):raise ValueError('Send a motion sequence')
        if payload.get('action') == 'collect' and not current_app.config.get('DEVELOPMENT_TOOLS', True):
            abort(404)
        frames=payload.get('frames');features=motion_features(frames)
        if payload.get('action')=='collect':
            label,group,split=(payload.get(k,'') for k in ('label','group','split'))
            if label not in MOTION_LABELS or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',group) or split not in ('train','validation','test'):raise ValueError('Choose a motion label, valid group and partition')
            directory=root/'data/processed/motion';directory.mkdir(parents=True,exist_ok=True)
            for path in directory.glob('*.json'):
                old=json.loads(path.read_text())
                if old['group']==group and old['split']!=split:raise ValueError('Keep this group in one partition')
            (directory/(uuid.uuid4().hex+'.json')).write_text(json.dumps({'label':label,'group':group,'split':split,'frames':frames,'version':MOTION_VERSION}))
            return jsonify(status='saved',frames=len(frames))
        if payload.get('action')!='predict':raise ValueError('Unknown motion action')
        path=root/'models/motion.joblib'
        if not path.exists():return jsonify(status='untrained',label=None)
        bundle=joblib.load(path)
        if bundle['version']!=MOTION_VERSION:raise ValueError('Re-extract/retrain motion features')
        scores=bundle['model'].predict_proba(features.reshape(1,-1))[0];i=int(np.argmax(scores));label=str(bundle['model'].classes_[i]);score=float(scores[i])
        evidence = path_evidence(frames)
        if evidence['label']:
            return jsonify(status='ok',label=evidence['label'],candidate=evidence['label'],
                           confidence=None,method='trajectory',evidence=evidence,
                           template_candidate=label,template_score=score)
        eligible = label in evidence.get('eligible', [])
        accepted=score>=bundle['threshold'] and eligible
        if label in ('J','Z') and not eligible:
            label='NONE'
        return jsonify(status='ok' if accepted else 'uncertain',label=label if accepted else None,confidence=score,candidate=label,threshold=bundle['threshold'])
    return routes
