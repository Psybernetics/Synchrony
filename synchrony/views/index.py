from flask.ext.classy import route
from synchrony.views.base import BaseView
from flask.ext.mako import render_template
from flask import make_response

class IndexView(BaseView):
	route_base = '/'

	@route("/")
	def index(self):
		response = make_response(render_template('index.html', ctx=self.ctx))
		return response
