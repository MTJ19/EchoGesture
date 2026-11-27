"""Isolated prototype routes: short video inference and training examples."""
import json
from pathlib import Path
import tempfile
import threading
import joblib
from flask import Blueprint,jsonify,render_template,request,send_file
from .word_features import WORD_FEATURE_VERSION
from .word_inference import predict


def word_routes(root):
    import os
    variant = os.environ.get("ECHOGESTURE_WORD_MODEL")
    if variant is None and (Path(root) / "models/word81-grammar-candidate.joblib").is_file():
        variant = "showcase50"
    if variant is None:
        variant = "word80-svm" if (Path(root)/"models/word80-priority-wlasl-citizen-svm.joblib").exists() else "prototype"
    svm_models = {
        'word20-svm': 'word20-citizen-svm',
        'word24-svm': 'word24-wlasl-citizen-svm',
        'word60-svm': 'word60-priority-wlasl-citizen-svm',
        'word80-svm': 'word80-priority-wlasl-citizen-svm',
        'showcase50': 'word81-grammar-candidate',
        'word81-svm': 'word81-grammar-candidate',
        'word85-svm': 'word85-four-additions-candidate',
        'word98-svm': 'word-cached-expansion-candidate',
        'word100-svm': 'word100-weak-extension-candidate',
        'word105-svm': 'word105-weak-extension-candidate',
        'word105-repairs-svm': 'word105-weak-extension-repairs-candidate',
    }
    candidate = variant == 'word20' or variant in svm_models
    root=Path(root);bp=Blueprint('words',__name__);lock=threading.Lock()
    def load():
        path=root/'models'/('words20-candidate.joblib' if candidate else 'words-prototype.joblib')
        if not path.is_file():return None
        bundle=joblib.load(path)
        if bundle.get('feature_version')!=WORD_FEATURE_VERSION:raise ValueError('Incompatible word model')
        if variant in svm_models:
            from sklearn.preprocessing import FunctionTransformer
            from sklearn.pipeline import make_pipeline
            from .word_svm_features import summarize_batch
            name = svm_models[variant]
            estimator = joblib.load(root/'models'/(name+'.joblib'))
            bundle.update(name=name, labels=list(estimator.classes_), model=make_pipeline(FunctionTransformer(summarize_batch), estimator))
        if variant == "showcase50":
            words = json.loads((root / "config/showcase50.json").read_text())
            if len(set(words)) != 50 or not set(words).issubset(bundle["labels"]):
                raise ValueError("Invalid showcase vocabulary")
            bundle.update(labels=words, allowed_words=set(words), name="showcase50")
        return bundle

    @bp.get('/words')
    def page():
        bundle=load()
        words = bundle['labels'] if bundle else []
        examples = sorted(word for word in words if (root/'static/word-examples'/word/(word+'.mp4')).is_file())
        return render_template('words.html',candidate=candidate, svm=variant=='word20-svm', words=words, example_words=examples)

    @bp.get('/api/words/status')
    def status():
        bundle=load()
        return jsonify(trained=bundle is not None,words=bundle['labels'] if bundle else [],
                       model=bundle['name'] if bundle else None)

    @bp.get('/api/words/example/<word>')
    def example(word):
        bundle=load()
        if bundle is None or word not in bundle['labels']:return jsonify(error='Unknown supported word'),404
        selected = root/'static/word-examples'/word/(word+'.mp4')
        if selected.is_file():
            return send_file(selected,mimetype='video/mp4',conditional=True)
        path=root/'datasets/preprocessed/words/quality-manifest.json'
        if not path.exists():return jsonify(error='Local examples unavailable'),404
        rows=json.loads(path.read_text())
        # Training examples only, with deterministic selection; never reveal test examples here.
        matches=sorted((r for r in rows if r['label']==word and r['split']=='train'),key=lambda r:r['video_id'])
        if not matches:return jsonify(error='Example unavailable'),404
        video_id=str(matches[0]['video_id'])
        if not video_id.isdigit():return jsonify(error='Invalid example ID'),404
        video=root/'datasets/raw/wlasl/videos'/(video_id+'.mp4')
        if not video.is_file():return jsonify(error='Example unavailable'),404
        return send_file(video,mimetype='video/mp4',conditional=True)

    @bp.post('/api/words/predict')
    def prediction():
        if 'video' not in request.files:raise ValueError('Upload a short video')
        if not lock.acquire(blocking=False):return jsonify(error='A word clip is already processing. Try again shortly.'),409
        try:
            bundle=load()
            if bundle is None:return jsonify(error='Word model has not been trained'),503
            extension=Path(request.files['video'].filename or '').suffix.lower()
            if extension not in {'.webm','.mp4','.mov','.m4v','.ogv'}:raise ValueError('Use WebM, MP4 or MOV video')
            # Temporary uploads are removed after success or failure. No training/capture route.
            with tempfile.TemporaryDirectory(prefix='echogesture-word-') as directory:
                path=Path(directory)/('clip'+extension);request.files['video'].save(path)
                return jsonify(predict(path,bundle=bundle))
        finally:lock.release()
    return bp
