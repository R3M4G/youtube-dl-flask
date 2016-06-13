#!/usr/bin/python3
from flask import Flask, request, send_from_directory, jsonify
from flask_socketio import SocketIO, emit
from youtube_dl import YoutubeDL
from sys import stderr
import json

app = Flask(__name__)
socketio = SocketIO(app)
clients = {}


@app.route('/', methods=['GET'])
def index():
	return send_from_directory('static', 'index.html')

@app.route('/static/<path:path>')
def send_js(path):
	return send_from_directory('static', path)


@socketio.on('connect')
def create_user():
	print("User {} connected".format(request.sid))
	def send_progress(msg):
		emit('progress', msg)
		print(msg)
	clients[request.sid] = {'info': None, 'ydl': YoutubeDL({
		'outtmpl': '%(uploader)s - %(title)s',
		'progress_hooks': [send_progress]})}

@socketio.on('disconnect')
def destroy_user():
	print("User {} disconnected".format(request.sid))
	del clients[request.sid]

@socketio.on('parse')
def parse_dl(url):
	try:
		video_info = clients[request.sid]['ydl'].extract_info(url, download=False)
		if 'entries' in video_info:
			if len(video_info['entries']) > 1:
				return emit('message', "playlists unsupported at this time")
			video_info = video_info['entries'][0]
		exposed_info = limited_dict(video_info, [
			'title', 'uploader', 'duration', 'width', 'height', 'fps'])
		formats = [limited_dict(format, [
			'format_id', 'width', 'height', 'fps', 'abr', 'acodec', 'vcodec', 'filesize'
			]) for format in video_info['formats']]
		for key in ('audio', 'video', 'other'):
			exposed_info[key+"_formats"] = []
		for format in formats:
			if format['acodec'] and format['acodec'] != "none":
				if format['vcodec'] and format['vcodec'] != "none":
					exposed_info['other_formats'].append(format)
				else:
					exposed_info['audio_formats'].append(format)
			elif format['vcodec']:
				exposed_info['video_formats'].append(format)

		emit('video_info', json.dumps(exposed_info))
		clients[request.sid]['info'] = video_info
	except Error as e:
		print(e, file=stderr)
		emit('message', '500: Server error')

@socketio.on('start_dl')
def start_dl(format):	
	print(format)
	ydl = clients[request.sid]['ydl']
	format = '+'.join([i for i in format.split('+') if i != '0'])
	ydl.params['format'] = format
	ydl.process_video_result(clients[request.sid]['info'], download=True)
	

def limited_dict(original, keys):
	return {k: original.get(k, None) for k in original.keys() & keys}
if __name__ == "__main__":
	socketio.run(app, '0.0.0.0', 8001)
