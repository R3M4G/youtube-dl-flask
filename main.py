#!/usr/bin/python3
from flask import Flask, request, send_from_directory, jsonify
from flask_socketio import SocketIO, emit
from youtube_dl import YoutubeDL
from sys import stderr
import json, traceback

app = Flask(__name__)
socketio = SocketIO(app)
clients = {}


def limited_dict(original, keys, missing=None):
        #return a copy of the original dict with only specified keys
        return {k: original.setdefault(k, []) for k in keys}

@app.route('/', methods=['GET'])
def index():
        return send_from_directory('static', 'index.html')

@app.route('/static/<path:path>')
def send_js(path):
        return send_from_directory('static', path)


@socketio.on('connect')
def create_user():
        clients[request.sid] = {
                'video_info': None,
                'ydl': YoutubeDL({
                        'outtmpl': '%(uploader)s - %(title)s',
                        'progress_hooks': [lambda msg: emit('progress', json.dumps(msg))]
                })
        }

@socketio.on('disconnect')
def destroy_user():
        # this will happen on any disconnect, graceful or not
        print("User {} disconnected".format(request.sid))
        del clients[request.sid]

@socketio.on('parse')
def parse_dl(url):
        try:
                emit('status', '200: Working...')
                ydl = clients[request.sid]['ydl']
                # make the call to the YoutubeDL library
                video_info = ydl.extract_info(url, download=False)

                # send the relevant information to the user
                exposed_info = limited_dict(
                        video_info, 
                        ['title', 'uploader', 'duration', 'width', 'height', 'fps', 'video_formats', 'audio_formats', 'other_formats'],
                        missing=[]
                )
                for format in video_info['formats']: 
                        # format can have 'acodec' be None, 'none', or a useful value
                        acodec = format.get('acodec', "none") 
                        vcodec = format.get('vcodec', "none") 

                        if acodec != "none":
                                if vcodec != "none":
                                        format_type = "other"
                                else:
                                        format_type = "audio"
                        elif vcodec != "none":
                                format_type = "video"
                        else:
                                continue

                        exposed_info[format_type+"_formats"].append(limited_dict(
                                format,
                                ['format_id', 'width', 'height', 'fps', 'abr', 'acodec', 'vcodec', 'ext', 'filesize']
                        ))

                emit('video_info', json.dumps(exposed_info))
                clients[request.sid]['video_info'] = video_info
        except Exception as e:
                traceback.print_exc()
                emit('status', '500: Server error')

@socketio.on('start_dl')
def start_dl(format):
        ydl = clients[request.sid]['ydl']
        video_info = clients[request.sid]['video_info']
        format = '+'.join([i for i in format.split('+') if i != '0'])

        print(video_info)
        video_info['requested_formats'] = list(ydl.build_format_selector(format)(video_info.get('formats')))
        ydl.params.update({'format': format})
        ydl.process_video_result(video_info, download=True)

if __name__ == "__main__":
        socketio.run(app, '0.0.0.0', 8001)
