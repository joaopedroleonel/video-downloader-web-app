import eventlet
eventlet.monkey_patch()

from service import *
from flask import Flask, redirect, request, render_template, url_for, Response, make_response, jsonify, abort, send_file
from functools import wraps
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime
import os
import re
import uuid
import redis
import json
from flask_socketio import SocketIO, emit, disconnect

app = Flask(__name__, static_url_path='',  static_folder='web/static', template_folder='web/')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
socketio = SocketIO(app, async_mode='eventlet')

redis_host = os.environ.get('REDIS_HOST')
redis_port = int(os.environ.get('REDIS_PORT'))
r = redis.Redis(host=redis_host, port=redis_port, db=0, decode_responses=True)
pipe = r.pipeline()

auth = Auth()
clean = Clean()

def start_cleaner():
    eventlet.spawn_n(clean.cleanOldFolders)

socketio.start_background_task(start_cleaner)

sema = eventlet.semaphore.Semaphore(4)

def requireAuth(api=False):
    def decorador(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cookieToken = request.cookies.get('token')
            if not cookieToken:
                if api:
                    return Response(status=401)
                else:
                    return redirect(url_for('authorization'))

            try:
                data = auth.decodeToken(cookieToken, app)
            except Exception:
                if api:
                    return Response(status=401)
                else:
                    return redirect(url_for('authorization'))

            if not data.get('session'):
                if api:
                    return Response(status=401)
                else:
                    return redirect(url_for('auauthorizationth'))

            return func(*args, **kwargs)
        return wrapper
    return decorador

def processDownloads(taskData):
    jobId = taskData['uuid']
    try:
        Yt(r).download(
            taskData['playlist'],
            taskData['type'],
            taskData['url'],
            jobId,
            taskData['session']
        )
    except Exception as e:
        pipe.expire(jobId, int(os.getenv('DATA_REDIS_EXP_SECONDS')))
        pipe.hset(jobId, mapping={'status': 'O download do vídeo não pôde ser realizado.', 'session': taskData['session']})
        pipe.execute()
        

@app.route('/', methods=['GET'])
@requireAuth(api=False)
def home():
    return render_template('index.html', year=datetime.now().year)

@app.route('/auth', methods=['GET', 'POST'])
def authorization():
    if request.method == 'GET':
        return render_template('auth.html')
    else:
        try:
            password = request.get_json()['password']
            if auth.checkPassword(password):
                res = make_response(Response(status=200))
                res.set_cookie('token', auth.encodeToken(app), httponly=True) 
                return res
            else:
                return Response(status=401)
        except:
            return Response(status=400)
        
@app.route('/initDownload', methods=['POST'])
@requireAuth(api=True)
def initDownload():
    try:
        data = request.get_json()
        sessionId = auth.decodeToken(request.cookies.get('token'), app).get('session')
        jobId = str(uuid.uuid4())

        isUrl = re.match(r'^https?://[^\s/$.?#].[^\s]*$', data.get('url'))
        if (data.get('type') not in [1, 2] or not isinstance(data.get('playlist'), bool) or not bool(isUrl)):
            abort(400)

        task = {
            'uuid': jobId,
            'playlist': data.get('playlist'),
            'type': data.get('type'),
            'url': data.get('url'),
            'session': sessionId
        }

        r.hset(jobId, mapping={'status': 'Aguardando para ser processado.', 'session': sessionId})
        r.lpush('download_queue', json.dumps(task))

        return jsonify({'uuid': jobId}), 200
    except Exception as e:
        return Response(status=400)

@socketio.on('checkStatus')
def checkStatus(data):
    cookieToken = request.cookies.get('token')
    authorizated = auth.decodeToken(cookieToken, app)
    if not authorizated:
        disconnect()
        return
        
    jobId = data.get('jobId')
    if not jobId:
        emit('statusUpdate', {'error': 'No jobId provided'})
        return
    
    sessionId = authorizated.get('session')
    if not sessionId:
        emit('statusUpdate', {'error': 'No session provided'})
        return

    pubsub = r.pubsub()
    pubsub.subscribe(jobId)
    previous_status = None

    try:
        for message in pubsub.listen():
            if message['type'] != 'message':
                continue

            status = r.hget(jobId, 'status')
            sessionOwner = r.hget(jobId, 'session')

            if not status:
                emit('statusUpdate', {'error': 'Job not found'})
                break

            if sessionOwner != sessionId:
                disconnect()
                break

            if status != previous_status:
                emit('statusUpdate', {'uuid': jobId, 'status': status})
                previous_status = status

            if status in ['O download do arquivo será iniciado em instantes.','O download do vídeo não pôde ser realizado.']:
                break
    finally:
        pubsub.unsubscribe(jobId)
        pubsub.close()
        disconnect()

@app.route('/download/<jobId>')
def downloadVideo(jobId):
    folder = f'./files/{jobId}'
    if not os.path.isdir(folder):
        return abort(404)

    files = os.listdir(folder)
    if not files:
        return abort(404)

    filename = files[0]
    name, ext = os.path.splitext(filename)
    safeName = re.sub(r'[^\w\s\-.]', '_', name) + ext
    filepath = os.path.join(folder, filename)

    if filename != safeName:
        newpath = os.path.join(folder, safeName)
        os.rename(filepath, newpath)
        filepath = newpath

    return send_file(filepath, as_attachment=True, download_name=safeName)

def processWrapper(taskData):
    with sema:
        processDownloads(taskData)

def workerLoop():
    while True:
        try:
            _, taskJson = r.brpop('download_queue')
        except Exception as e:
            eventlet.sleep(1)
            continue

        if not taskJson:
            continue
        try:
            taskData = json.loads(taskJson)
        except:
            continue

        eventlet.spawn_n(processWrapper, taskData)

socketio.start_background_task(workerLoop)
    
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)