import csv
import io
import os
import re
import threading
import uuid
import time
from pathlib import Path
import joblib
import numpy as np
from flask import Flask, abort, jsonify, render_template, request
from PIL import Image, ImageOps, UnidentifiedImageError
from asl_lab.features import FEATURE_VERSION, HandExtractor, LETTERS
from asl_lab.predict import classify
from asl_lab.motion_routes import motion_routes
from asl_lab.word_routes import word_routes

ROOT = Path(__file__).resolve().parent


def create_app():
    app = Flask(__name__)
    app.register_blueprint(motion_routes(ROOT))
    app.register_blueprint(word_routes(ROOT))
    app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['DEVELOPMENT_TOOLS'] = os.getenv('ECHOGESTURE_DEVELOPMENT_TOOLS', '1') == '1'
    lock = threading.Lock()
    state = {'extractor': None, 'bundle': None, 'mtime': None}

    def get_extractor():
        if state['extractor'] is None:
            state['extractor'] = HandExtractor()
        return state['extractor']

    def bundle():
        path = ROOT / 'models/classifier.joblib'
        if not path.exists():
            return None
        mtime = path.stat().st_mtime_ns
        if state['mtime'] != mtime:
            loaded = joblib.load(path)  # Only load locally trained, trusted artifacts.
            if loaded['feature_version'] != FEATURE_VERSION:
                raise ValueError('Retrain model: incompatible feature version')
            state.update(bundle=loaded, mtime=mtime)
        return state['bundle']

    def read_image():
        if 'image' not in request.files:
            raise ValueError('Send an image file')
        raw = request.files['image'].read()
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > 16_000_000:
                raise ValueError('Image exceeds 16 megapixels')
            image = ImageOps.exif_transpose(image).convert('RGB')
            image.thumbnail((1280, 1280))
            return image.copy()

    @app.get('/')
    def index():
        show_tools = app.config['DEVELOPMENT_TOOLS'] and request.args.get('tools') == '1'
        return render_template('index.html' if show_tools else 'landing.html', letters=LETTERS)

    @app.get('/sign')
    def signing():
        return render_template('index.html', letters=LETTERS)

    @app.get('/api/status')
    def status():
        with lock:
            model = bundle()
            return jsonify(trained=model is not None, labels=model['labels'] if model else [],
                           model=model['name'] if model else None)

    @app.get('/healthz')
    def health():
        return jsonify(status='ok')

    @app.post('/api/predict')
    def predict():
        started = time.perf_counter()
        image = read_image()
        with lock:
            extractor = get_extractor()
            features, status = extractor.extract(np.array(image))
            if features is None:
                return jsonify(status=status, label=None, confidence=None)
            model = bundle()
            if model is None:
                return jsonify(status='untrained', label=None, confidence=None)
            cutoff = request.form.get('cutoff')
            threshold = float(cutoff) / 100 if cutoff is not None else model['threshold']
            if not np.isfinite(threshold) or not .10 <= threshold <= .95:
                raise ValueError('Recognition cutoff must be between 10 and 95 percent')
            prediction = classify({**model, 'threshold': threshold}, features)
            prediction['landmarks'] = extractor.points
            prediction['processing_ms'] = round((time.perf_counter() - started) * 1000, 1)
            return jsonify(prediction)

    @app.post('/api/collect')
    def collect():
        if not app.config['DEVELOPMENT_TOOLS']:
            abort(404)
        label, group, split = (request.form.get(k, '') for k in ('label', 'group', 'split'))
        if label not in LETTERS or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', group):
            raise ValueError('Choose a static letter and a signer ID (letters, numbers, dash, underscore)')
        if split not in ('train', 'validation', 'test'):
            raise ValueError('Choose a partition')
        image = read_image()
        with lock:
            manifest = ROOT / 'data/manifest.csv'
            rows = list(csv.DictReader(manifest.open())) if manifest.exists() else []
            if any(r['group'] == group and r['split'] != split for r in rows):
                raise ValueError('This signer already belongs to a different partition')
            if state['extractor'] is None:
                state['extractor'] = HandExtractor()
            features, status = state['extractor'].extract(np.array(image))
            if features is None:
                raise ValueError('Capture requires exactly one detected hand: ' + status)
            relative = f'raw/collected/{group}/{label}/{uuid.uuid4().hex}.jpg'
            path = ROOT / 'data' / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            image.save(path, quality=95)
            with manifest.open('a', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=['path', 'label', 'group', 'split'])
                if not rows:
                    writer.writeheader()
                writer.writerow(dict(path=relative, label=label, group=group, split=split))
        return jsonify(saved=True, samples=len(rows) + 1)

    @app.errorhandler(ValueError)
    @app.errorhandler(UnidentifiedImageError)
    @app.errorhandler(Image.DecompressionBombError)
    def invalid(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(413)
    def too_large(exc):
        return jsonify(error='Frame exceeds 8 MB'), 413

    return app


if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=8080, threaded=True)
