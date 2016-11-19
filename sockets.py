from flask import request, copy_current_request_context
from flask_socketio import emit
from copy import copy
from threading import Thread
from shutil import move
from traceback import print_exc
from gevent import sleep
import json, os.path
import youtube_dl

EXPOSED_VIDEO_INFO = ['title', 'uploader', 'duration', 'description']
EXPOSED_FORMAT_INFO = ['format_id', 'width', 'height', 'fps', 'abr', 'acodec', 'vcodec', 'ext', 'filesize']
DOWNLOADS_DIR = './downloads/'
clients = {}

def limited_dict(original, keys, missing=None):
    return {k: (original.get(k) or copy(missing)) for k in keys if (original.get(k) or missing) != None}

def create_user():
    clients[request.sid] = {
        'video_info': None,
        'ydl': youtube_dl.YoutubeDL({
            'noprogress': True,
            'outtmpl': '%(uploader)s - %(title)s[%(resolution)s][%(abr)sk].%(ext)s',
            'progress_hooks': [
                lambda msg: emit('progress', json.dumps(limited_dict(
                    msg,
                    ["status", "downloaded_bytes", "total_bytes", "speed"]
                ))),
                lambda _: sleep(0)]
        })
    }

def destroy_user():
    del clients[request.sid]

def parse_url(url):
    try:
        emit('parsing', '_')
        ydl = clients[request.sid]['ydl']
        video_info = ydl.extract_info(url, download=False)
        format_types = ['video_formats', 'audio_formats']

        # filter the video_info object down to what the user needs to know
        exposed_info = limited_dict(video_info, EXPOSED_VIDEO_INFO + format_types, missing=[])

        # seperate the various file formats into either audio or video
        # ones with both are shit; forget them
        for format in video_info['formats']:
            if format.get('acodec', "none") is not "none" and format.get('vcodec', "none") is "none":
                    format_type = "audio_formats"
            elif format.get('vcodec', "none") is not 'none' and format.get('acodec', "none") is "none":
                format_type = "video_formats"
            else:
                continue
            exposed_info[format_type].append(limited_dict(format, EXPOSED_FORMAT_INFO))

        # send the filtered info to the user
        emit('video_info', json.dumps(exposed_info))
        # and store the unfiltered info in the client
        clients[request.sid]['video_info'] = video_info
    except Exception as e:
        print_exc()
        emit('error', 'parsing')

def start_dl(format):
    try:
        # get options from client
        ydl = clients[request.sid]['ydl']
        video_info = clients[request.sid]['video_info']
        format = '+'.join([i for i in format.split('+') if i != '0'])

        # prepare info dict
        video_info['requested_formats'] = None
        format = next(ydl.build_format_selector(format)({'formats': video_info.get('formats')}))

        # if downloading both audio and video, let the client know the total download size
        if len(format.get('requested_formats', [])) > 1:
            emit('total_bytes', sum(x['filesize'] for x in format['requested_formats']))
        video_info.update(format)
        for key in EXPOSED_FORMAT_INFO:
            if key not in format and key in video_info:
                del video_info[key]

        # start download in a new thread
        @copy_current_request_context
        def download(info):
            # let the client know where to find the file in case connection is lost
            filename = youtube_dl.utils.encodeFilename(ydl.prepare_filename(info))
            emit('filename', '/downloads/'+filename)

            # download the file if it doesn't already exist
            if not os.path.exists(DOWNLOADS_DIR+filename):
                ydl.process_info(info)
                filename = youtube_dl.utils.encodeFilename(ydl.prepare_filename(info))
                # then move it to the downloads_dir
                move(filename, DOWNLOADS_DIR+filename)

            # then inform the client where to find it
            emit('finished', '/downloads/'+filename)
        Thread(target=download, args=(video_info,)).start()
    except Exception:
        print_exc()
        emit('error', 'parsing')
