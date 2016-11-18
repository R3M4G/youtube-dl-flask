#!/usr/bin/python3
from flask import Flask, request, send_from_directory, jsonify, copy_current_request_context
from flask_socketio import SocketIO, emit
from youtube_dl import YoutubeDL, utils
from sys import stderr
from copy import copy
from threading import Thread
from shutil import move
import json, traceback, gevent, gevent.monkey, os.path

app = Flask(__name__)
socketio = SocketIO(app, async_mode='gevent', ping_timeout=30)
clients = {}


def limited_dict(original, keys, missing=None):
    return {k: (original.get(k) or copy(missing)) for k in keys if (original.get(k) or missing) != None}


@app.route('/')
def index():
    return send_static('index.html')

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

@app.route('/downloads/<path:path>')
def send_downloaded(path):
    return send_from_directory('/srv/ftp/youtube', path)

@socketio.on('connect')
def create_user():
    clients[request.sid] = {
        'video_info': None,
        'ydl': YoutubeDL({
            'ratelimit': 500000,
            'noprogress': True,
            'outtmpl': '%(uploader)s - %(title)s[%(resolution)s][%(asr)s].%(ext)s',
            'progress_hooks': [
                lambda msg: emit('progress', json.dumps(limited_dict(
                    msg, 
                    ["status", "downloaded_bytes", "total_bytes", "speed"]
                ))),
                lambda _: gevent.sleep(0)]
        })
    }

@socketio.on('disconnect')
def destroy_user():
    del clients[request.sid]

@socketio.on('parse')
def parse_dl(url):
    try:
        emit('parsing', '_')
        ydl = clients[request.sid]['ydl']
        # make the call to the YoutubeDL library
        video_info = ydl.extract_info(url, download=False)

        # filter the video_info object down to what the user needs to know
        exposed_info = limited_dict(
            video_info, 
            ['title', 'uploader', 'duration', 'width', 'height', 'fps', 'video_formats', 'audio_formats', 'other_formats'],
            missing=[]
        )
        for format in video_info['formats']: 
            if format.get('acodec', "none") != "none": # format can have 'acodec' missing, 'none', or a useful value
                if format.get('vcodec', "none") != "none":
                    format_type = "other"
                else:
                    format_type = "audio"
            elif format.get('vcodec', "none") != 'none':
                format_type = "video"

            exposed_info[format_type+"_formats"].append(limited_dict(
                format,
                ['format_id', 'width', 'height', 'fps', 'abr', 'acodec', 'vcodec', 'ext', 'filesize']
            ))

        # send the info to the user
        emit('video_info', json.dumps(exposed_info))
        clients[request.sid]['video_info'] = video_info
    except Exception as e:
        traceback.print_exc()
        emit('error', 'parsing')

@socketio.on('start_dl')
def start_dl(format):
    # get options from client
    ydl = clients[request.sid]['ydl']
    video_info = clients[request.sid]['video_info']
    format = '+'.join([i for i in format.split('+') if i != '0'])

    # prepare info dict
    video_info['requested_formats'] = None
    format = next(ydl.build_format_selector(format)({'formats': video_info.get('formats')}))
    if len(format.get('requested_formats', [])) > 1:
        emit('total_bytes', sum(x['filesize'] for x in format['requested_formats']))
    video_info.update(format)

    # start download in a new thread
    @copy_current_request_context
    def download(info):
        filename = utils.encodeFilename(ydl.prepare_filename(info))
        emit('filename', '/downloads/'+filename)

        if not os.path.exists('/srv/ftp/youtube/'+filename):
            ydl.process_info(info)
            filename = utils.encodeFilename(ydl.prepare_filename(info))
            move(filename, '/srv/ftp/youtube/'+filename)
        # then inform the client where to find it
        emit('finished', '/downloads/'+filename)
    Thread(target=download, args=(video_info,)).start()

if __name__ == "__main__":
    gevent.monkey.patch_all()
    socketio.run(app, '127.0.0.1', 8001)
