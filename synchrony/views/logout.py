from synchrony import log, db
from flask import redirect
from flask.ext.classy import route
from synchrony.views.base import BaseView
from synchrony.controllers.auth import auth
from flask import session, make_response
from flask.ext.mako import render_template

class LogoutView(BaseView):
	route_base = '/logout'

	@route("/")
	def index(self):
		user = auth(session, required=True)
		current_session = session['session']
		[db.session.delete(s) for s in user.sessions if s.session_id == current_session]
		session['session'] = ''
		log("%s logged out." % user.username)
		return redirect('/')
