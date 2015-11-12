from synchrony import app, log
from flask.ext import restful
from flask import request, session

from synchrony.controllers import fetch
from synchrony.controllers import parser
from synchrony.controllers.auth import auth

class RequestResource(restful.Resource):

	def get(self, url):

		user = auth(session, required=not app.config['OPEN_PROXY'])

		revision = fetch.get("http://"+url, request.user_agent, user)

		if revision.bcontent and not revision.content:
			return {"response":"A wild binary."}, 200
		data = parser.parse(revision.content, 'http://' + url)
		return {"response":data}, revision.status

