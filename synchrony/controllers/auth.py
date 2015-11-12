from synchrony.models import Session
from flask.ext.restful import abort

def auth(session, required=False):
	if 'session' in session:
		s = Session.query.filter(Session.session_id == session['session']).first()
		if s and s.user and s.user.active: return s.user
	if required: abort(403)
	return None
