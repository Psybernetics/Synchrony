from synchrony import app
from synchrony.controllers import fetch
from synchrony.controllers import parser
from synchrony.controllers.auth import auth

from flask.ext.classy import route
from synchrony.views.base import BaseView
from flask.ext.mako import render_template
from flask import request, Response, session, send_file

class RequestView(BaseView):
	route_base = '/request'

	@route("/<path:url>")
	def get(self, url):
		user = auth(session, required=not app.config['OPEN_PROXY'])

		revision = fetch.get("http://"+url, request.user_agent, user)
		response = Response(mimetype=revision.mimetype)

		if not "text" in revision.mimetype:
			return send_file(revision.bcontent, mimetype=revision.mimetype)
		else:
			if 'html' in revision.mimetype:
				response.data = parser.parse(revision.content, 'http://' + url)
			else:
				response.data = revision.content
		return response
