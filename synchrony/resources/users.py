# This file defines the API endpoints for users and sessions
from synchrony import db, log
from sqlalchemy import desc
from flask.ext import restful
from flask import request, session
from flask.ext.restful import reqparse
from synchrony.controllers.auth import auth
from synchrony.controllers.utils import make_response
from synchrony.models import User, Session, UserGroup

class UserCollection(restful.Resource):
    """
    Implements /v1/user
    """
    def get(self):
        """
        Paginated access to users
        """
        user = auth(session, required=True)
        
        per_page = 10

        parser = reqparse.RequestParser()
        parser.add_argument("me", type=bool, default=None)
        parser.add_argument("page",type=int, help="", required=False, default=1)
        parser.add_argument("content",type=bool, help="", required=False, default=None)
        args = parser.parse_args()

        if args.me:
            return user.jsonify()

        if not user.can("see_all"):
            return {}, 403

        query = User.query.order_by(desc(User.created)).paginate(args.page, per_page)
        return make_response(request.url, query)

    def put(self):
        """
        Create a user
        """
        parser = reqparse.RequestParser()
        parser.add_argument("username", type=str, help="Username.", required=True)
        parser.add_argument("password", type=str, help="Password.", required=True)
        args = parser.parse_args()

        if User.query.filter(User.username == args.username).first():
            return {'message':"Username already in use."}, 304
        
        user = User(args.username, args.password)

        # First user is an admin
        if not User.query.first():
            group = UserGroup.query.filter(UserGroup.name == "Administrators").first()
        else:
            group = UserGroup.query.filter(UserGroup.name == "Users").first()

        group.users.append(user)

        s = Session()
        s.from_request(request)
        user.sessions.append(s)

        db.session.add(user)
        db.session.add(group)
        db.session.add(s)
        db.session.commit()

        session['session'] = s.session_id
        return s.jsonify()

class UserResource(restful.Resource):
    """
    Implements /v1/user/:username
    """
    def get(self, username):
        """
        View user, or, if you're an admin, other users.
        """
        user = auth(session, required=True)

        if user.username != username and not user.can("see_all"):
            return {}, 403

        user = User.query.filter(User.username == username).first()

        if not user:
            return {}, 404

        return user.jsonify(groups=True, sessions=True)

    def post(self, username):
        """
        Account modification
        """
        parser = reqparse.RequestParser()
        parser.add_argument("password",  type=str)
        parser.add_argument("email",     type=str)
        parser.add_argument("public",    type=bool, default=None)
        parser.add_argument("active",    type=bool, default=None)
        parser.add_argument("can_store", type=bool, default=None)
        args = parser.parse_args()

        calling_user = auth(session, required=True)

        if calling_user.username != username and not calling_user.admin:
            return {}, 403

        user = User.query.filter(User.username == username).first()

        if not user:
            return {}, 404

        should_commit = False

        if args.password:
            user.change_password(args.password)
            should_commit = True

        if args.email:
            user.email = args.email
            should_commit = True

        if args.public:
            user.public = args.public != None
            should_commit = True

        if calling_user.can("deactivate") and args.active != None:
            user.active = args.active
            if args.active == True:
                log("%s reactivated %s's user account." % \
                    (calling_user.username, user.username))
            else:
                log("%s deactivated %s's user account." % \
                    (calling_user.username, user.username))
                for s in user.sessions:
                    db.session.delete(s)
            should_commit = True

        if calling_user.admin and args.can_store != none:
            user.can_store = args.can_store
            should_commit = True

        if should_commit:
            db.session.add(user)
            db.session.commit()

        return user.jsonify()

    def delete(self, username):
        """
        Account deletion
        """
        user = auth(session, required=True)

        if user.username != username and not user.admin:
            return {}, 403

        user = User.query.filter(User.username == username).first()

        if not user:
            return {}, 404

        db.session.delete(user)
        db.session.commit()
        return {}, 204


class UserSessionsResource(restful.Resource):
    """
    Implements /v1/user/:username/sessions
    """
    def get(self, username):
        "Permit administrators to view other users"

        requesting_user = auth(session, required=True)
        user = User.query.filter(User.username == username).first()
        if not user:
            return {}, 404

        if requesting_user != user and not requesting_user.admin:
            return {}, 403

        return user.jsonify(sessions=True)

    def put(self, username):
        "Add a session for a user and return the session cookie"
        parser = reqparse.RequestParser()
        parser.add_argument("password", type=str, help="password.", required=True)
        args = parser.parse_args()

        user = User.query.filter(User.username == username).first()
        if not user:
            return{}, 404

        if not user.verify_password(args.password):
            return {}, 401

        if not user.active:
            return {}, 304

        s = Session()
        s.from_request(request)
        user.sessions.append(s)
        db.session.add(user)
        db.session.add(s)
        db.session.commit()
        session['session'] = s.session_id

        log("%s logged in." % user.username)

        response            = user.jsonify()
        response['session'] = s.jsonify()
        return response

    def delete(self, username):
        "Delete a session for a user"
        user = auth(session, required=True)

        parser = reqparse.RequestParser()
        parser.add_argument("timestamp", type=int, help="session timestamp", required=True)
        args = parser.parse_args()

        for s in user.sessions:
            if time.mktime(s.created.timetuple()) == args.timestamp:
                db.session.delete(s)
                db.session.commit()
        log("%s logged out." % user.username)

        return {}, 204
