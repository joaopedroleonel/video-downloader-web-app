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
from concurrent.futures import ThreadPoolExecutor
from threading import Thread
from flask_socketio import SocketIO, emit, disconnect
import threading

app = Flask(__name__, static_url_path='',  static_folder='web/static', template_folder='web/')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
socketio = SocketIO(app, cors_allowed_origins="*")

redis_host = os.environ.get("REDIS_HOST")
redis_port = int(os.environ.get("REDIS_PORT"))
r = redis.Redis(host=redis_host, port=redis_port, db=0)

authorization = Auth()

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
                    return redirect(url_for('auth'))

            try:
                data = authorization.decodeToken(cookieToken, app)
            except Exception:
                if api:
                    return Response(status=401)
                else:
                    return redirect(url_for('auth'))

            if not data.get('session'):
                if api:
                    return Response(status=401)
                else:
                    return redirect(url_for('auth'))

            return func(*args, **kwargs)
        return wrapper
    return decorador

def processDownloads(taskData):
    jobId = taskData["uuid"]
    try:
        Yt(r).download(
            taskData["playlist"],
            taskData["type"],
            taskData["url"],
            jobId
        )
    except Exception as e:
        r.hset(jobId, mapping={'status': 'O download do vídeo não pôde ser realizado.'})
        

@app.route('/', methods=['GET'])
@requireAuth(api=False)
def home():
    return render_template('index.html', year=datetime.now().year)

@app.route('/auth', methods=['GET', 'POST'])
def auth():
    if request.method == 'GET':
        return render_template('auth.html')
    else:
        try:
            password = request.get_json()['password']
            if authorization.checkPassword(password):
                res = make_response(Response(status=200))
                res.set_cookie('token', authorization.encodeToken(app), httponly=True) 
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
        jobId = str(uuid.uuid4())

        task = {
            "uuid": jobId,
            "playlist": data.get("playlist"),
            "type": data.get("type"),
            "url": data.get("url")
        }

        r.hset(jobId, mapping={"status": "Aguardando para ser processado."})
        r.lpush("download_queue", json.dumps(task))

        return jsonify({"uuid": jobId}), 200
    except Exception as e:
        print(e)
        return Response(status=400)

@socketio.on('checkStatus')
def checkStatus(data):
    cookieToken = request.cookies.get('token')
    authorizated = authorization.decodeToken(cookieToken, app)
    if not authorizated:
        disconnect()
        
    jobId = data.get('jobId')
    if not jobId:
        emit('statusUpdate', {"error": "No jobId provided"})
        return
    
    previous_status = None

    while True:
        status = r.hget(jobId, "status")
        if not status:
            emit('statusUpdate', {"error": "Job not found"})
            break

        status = status.decode() if isinstance(status, bytes) else status  

        if status != previous_status:
            emit('statusUpdate', {"uuid": jobId, "status": status})
            previous_status = status

        if status in ["O download do arquivo será iniciado em instantes.","O download do vídeo não pôde ser realizado."]:
            break

        socketio.sleep(0.3)
        
    disconnect()
    
@app.route("/download/<jobId>")
def downloadVideo(jobId):
    folder = f"./files/{jobId}"
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
    print("[worker] workerLoop started, waiting on BRPOP")
    while True:
        try:
            _, taskJson = r.brpop("download_queue")
        except Exception as e:
            eventlet.sleep(1)
            continue

        if not taskJson:
            continue
        try:
            taskData = json.loads(taskJson)
        except Exception as e:
            print(f"[worker] invalid json: {e}")
            continue

        eventlet.spawn_n(processWrapper, taskData)

socketio.start_background_task(workerLoop)
    
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)