from synchrony import app
from socketio import socketio_manage
from flask import session, request, Response
from synchrony.streams.events import EventStream
from synchrony.streams.documents import DocumentStream

@app.route("/stream/<path:remaining>", methods=['GET', 'POST'])
def stream(remaining):
	try:
		# We pass an immutable session dictionary as the request to socketio_manage
		# This allows us to use our normal authentication function to turn a session into a user
#		socketio_manage(request.environ, {'': GlobalStream, '/chat': ChatStream}, dict(session))
		socketio_manage(
			request.environ,
			{
				'/events':    EventStream,
				'/documents': DocumentStream,
			},
			dict(session)
		)
	except Exception, e:
		print e.message
	return Response()
