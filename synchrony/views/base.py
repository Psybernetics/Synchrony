from flask import session

from flask.ext.classy import FlaskView
from synchrony.controllers.utils import generate_csrf_token
from synchrony.controllers.auth import auth

class BaseView(FlaskView):

	PER_PAGE = 20

	def before_request(self, name, *args, **kwargs):
		# Make certain objects available to locally rendered views.
		self.ctx = {'user': auth(session),
					'csrf_token':generate_csrf_token(),
					'config': self.app.config}


