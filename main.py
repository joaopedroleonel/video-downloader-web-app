import eventlet
eventlet.monkey_patch()

from dotenv import load_dotenv
load_dotenv()

from service import *
from flask import Flask, redirect, request, render_template, url_for, Response, make_response, jsonify, abort, send_file
from flask_socketio import SocketIO, emit, disconnect
from functools import wraps
from datetime import datetime
import os
import re
import uuid
import redis
import json
import logging

app = Flask(__name__, static_url_path='',  static_folder='web/static', template_folder='web/')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
socketio = SocketIO(app, async_mode='eventlet')

logging.basicConfig(level=logging.INFO)

redisHost = os.environ.get('REDIS_HOST')
redisPort = int(os.environ.get('REDIS_PORT'))
redisDb = int(os.environ.get('REDIS_DB'))
r = redis.Redis(host=redisHost, port=redisPort, db=redisDb, decode_responses=True)
pipe = r.pipeline()

auth = Auth()
clean = Clean()

socketio.start_background_task(clean.cleanOldFolders)

sema = eventlet.semaphore.Semaphore(int(os.getenv('SEMAPHORE_LIMIT')))

def requireAuth(api):
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
                    return redirect(url_for('authorization'))

            return func(*args, **kwargs)
        return wrapper
    return decorador

@app.before_request
def logRequest():
    xff = request.headers.get('X-Forwarded-For', '')
    clientIp = xff.split(',')[0].strip() if xff else request.remote_addr
    body = None

    if request.method in ['POST', 'PUT', 'PATCH']:
        contentType = request.headers.get('Content-Type', '')
        if 'application/json' in contentType:
            try:
                body = request.get_json(silent=True)
            except Exception as e:
                body = f"Erro ao ler JSON: {e}"

    logEntry = {
        "type": "HTTP",
        "ip": clientIp,
        "method": request.method,
        "path": request.path,
        "user_agent": request.user_agent.string,
        "body": body
    }

    logging.info(json.dumps(logEntry))
        
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

        isValidUrl = re.match(r'^https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^\s]+$', data.get('url'))

        if (data.get('type') not in [1, 2] or not isinstance(data.get('playlist'), bool) or not bool(isValidUrl)):
            abort(400)

        task = {
            'uuid': jobId,
            'playlist': data.get('playlist'),
            'type': data.get('type'),
            'url': data.get('url'),
            'session': sessionId
        }

        pipe.expire(jobId, int(os.getenv('DATA_REDIS_EXP_SECONDS')))
        pipe.hset(jobId, mapping={'status': 'open', 'msg': 'Aguardando para ser processado.', 'session': sessionId})
        pipe.lpush('download_queue', json.dumps(task))
        pipe.publish(jobId, 'updated')
        pipe.execute()

        return jsonify({'uuid': jobId}), 200
    except Exception as e:
        return Response(status=400)

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

@socketio.on('connect')
def handleConnect():
    logEntry = {
        "type": "SOCKET",
        "action": "CONNECT",
        "sid": request.sid,
        "ip": request.remote_addr if request else "N/A",
        "user_agent": request.headers.get('User-Agent', '')
    }
    
    logging.info(json.dumps(logEntry))

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
    previousStatusMsg = None

    try:
        for message in pubsub.listen():
            if message['type'] != 'message':
                continue

            status, msg, sessionOwner = r.hmget(jobId, ['status', 'msg', 'session'])

            if not status:
                emit('statusUpdate', {'error': 'Job not found'})
                break

            if sessionOwner != sessionId:
                disconnect()
                break

            if msg != previousStatusMsg:
                emit('statusUpdate', {'uuid': jobId, 'status': status, 'msg': msg})
                previousStatusMsg = msg

            if status in ['finally','error']:
                break
    finally:
        pubsub.unsubscribe(jobId)
        pubsub.close()
        disconnect()

def processDownloads(taskData, gt):
    with sema:
        jobId = taskData['uuid']
        
        try:
            Yt(r, gt).download(
                taskData['playlist'],
                taskData['type'],
                taskData['url'],
                jobId,
                taskData['session']
            )
        except Exception as e:
            statusMsg = 'Não foi possível realizar o download do vídeo.'

            if str(e) == 'O tamanho máximo da pasta de downloads foi atingido.':
                statusMsg = str(e)

            pipe.expire(jobId, int(os.getenv('DATA_REDIS_EXP_SECONDS')))
            pipe.hset(jobId, mapping={'status': 'error', 'msg': statusMsg, 'session': taskData['session']})
            pipe.execute()

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

        gt = eventlet.spawn(processDownloads, taskData, None)
        gt.args = (taskData, gt)

socketio.start_background_task(workerLoop)
    
if __name__ == '__main__':
    socketio.run(app)