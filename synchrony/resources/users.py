# This file defines the API endpoints for users and sessions
import time
import gevent
import flask_restful as restful
from sqlalchemy import and_, desc
from flask_restful import reqparse
from flask import request, session, redirect

from synchrony import app, db, log
from synchrony.controllers.auth import auth
from synchrony.controllers.utils import make_response
from synchrony.models import User, Friend, Peer, Network
from synchrony.models import Session, UserGroup, Revision

class UserCollection(restful.Resource):
    """
    Implements /v1/users
    """
    def get(self):
        """
        Paginated access to users
        """
        parser = reqparse.RequestParser()
        parser.add_argument("me",       type=bool, default=None)
        parser.add_argument("signups",  type=bool, default=None)
        parser.add_argument("page",     type=int, required=False, default=1)
        parser.add_argument("per_page", type=int, required=False, default=10)
        args = parser.parse_args()

        # Let unauthenticated users see if they can register an account
        if args.signups:
            if "PERMIT_NEW_ACCOUNTS" in app.config:
                return app.config["PERMIT_NEW_ACCOUNTS"]
            return None
        
        user = auth(session, required=True)

        if args.me:
            s = Session.query.filter(Session.session_id == session['session']).first()
            response            = user.jsonify()
            response['session'] = s.jsonify()
            return response

        if not user.can("see_all"):
            return {}, 403

        query = User.query.order_by(desc(User.created)).paginate(args.page, args.per_page)
        return make_response(request.url, query, revisions=True)

    def put(self):
        """
        Create a user given a username and password.
        """
        parser = reqparse.RequestParser()
        parser.add_argument("username", type=unicode, help="Username.", required=True)
        parser.add_argument("password", type=unicode, help="Password.", required=True)
        args = parser.parse_args()

        if "PERMIT_NEW_ACCOUNTS" in app.config and \
            not app.config["PERMIT_NEW_ACCOUNTS"]:
            return {"message":"This server isn't allowing new accounts at this time."}, 304

        if User.query.filter(User.username == args.username).first():
            return {'message':"Username already in use."}, 304
        
        user = User(args.username, args.password)

        # Add the first-created  user account to the Administrators group
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
        View user. Those with see_all may access more attributes.
        """
        user = auth(session, required=True)

        parser = reqparse.RequestParser()
        parser.add_argument("can", type=str)
        args = parser.parse_args()

        target = User.query.filter(User.username == username).first()

        if not target:
            return {}, 404

        if not user.can("see_all") and username != user.username:
            return target.jsonify(address=app.routes._default)
        
        if args.can:
            return target.can(args.can)
    
        return target.jsonify(revisions=True,
                            groups=True,
                            sessions=True,
                            address=app.routes._default)
        
    def post(self, username):
        """
        Account modification
        """
        parser = reqparse.RequestParser()
        parser.add_argument("email",           type=str)
        parser.add_argument("password",        type=str)
        parser.add_argument("verify_password", type=str)
        parser.add_argument("public",          type=bool, default=None)
        parser.add_argument("active",          type=bool, default=None)
        args = parser.parse_args()

        calling_user = auth(session, required=True)

        if calling_user.username != username and not calling_user.can("reset_user_pw"):
            return {}, 403

        user = User.query.filter(User.username == username).first()

        if not user:
            return {}, 404

        if args.verify_password: # It's here to spare from getting in the logs.
            return user.verify_password(args.verify_password)

        if args.password:
            # must be at least six characters though
            if len(args.password) < 6:
                return "Must be at least six characters.", 304
            user.change_password(args.password)
            db.session.add(user)
            db.session.commit()
            return True

        if args.email:
            user.email = args.email

        if args.public:
            user.public = args.public != None

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

        db.session.add(user)
        db.session.commit()
        return user.jsonify()

    def delete(self, username):
        """
        Account deletion
        """
        user = auth(session, required=True)

        if user.username != username and not user.can("delete_at_will"):
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
        user = auth(session, required=True)

        parser = reqparse.RequestParser()
        parser.add_argument("page",     type=int, default=1)
        parser.add_argument("per_page", type=int, default=10)
        args = parser.parse_args()

        if user.username != username and not user.can("see_all"):
            return {}, 403

        if user.username != username:
            user = User.query.filter(User.username == username).first()
            if not user:
                return {}, 404

        query = Session.query.filter(Session.user == user)\
            .order_by(desc(Session.created)).paginate(args.page, args.per_page)
        return make_response(request.url, query)

    def put(self, username):
        "Add a session for a user and return the session cookie"
        parser = restful.reqparse.RequestParser()
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
        parser.add_argument("timestamp", type=str, help="session timestamp", required=True)
        args = parser.parse_args()

        if user.username != username and not user.can("delete_at_will"):
            return {}, 304

        target = User.query.filter(User.username == username).first()
        if not target:
            return {}, 404

        timestamp = float(args.timestamp + '.0')

        for s in user.sessions:
            if time.mktime(s.created.timetuple()) == timestamp:
                db.session.delete(s)
                db.session.commit()
        log("%s deleted a session for %s." % (user.username, target.username))
        return {}, 204

class UserRevisionCollection(restful.Resource):
    def get(self, username):
        user = auth(session, required=True)

        if user.username != username and not user.can("see_all"):
            return {}, 403

        parser = reqparse.RequestParser()
        parser.add_argument("page",     type=int, default=1)
        parser.add_argument("per_page", type=int, default=20)
        args = parser.parse_args()  

        user = User.query.filter(User.username == username).first()
        if user == None:
            return 404

        query = Revision.query.filter(Revision.user == user)\
            .order_by(desc(Revision.created)).paginate(args.page, args.per_page)
        return make_response(request.url, query)

    def post(self, username):
        user = auth(session, required=True)
        
        if not 'revision' in request.files:
            return {}, 400

        upload = request.files['revision']

        # TODO(ljb): Check the KL divergence with existing files and
        #            the frequency with which this method is being called.

        revision = Revision()
        revision.add(upload)
        
        if user.public:
            revision.public = True

        existing = Revision.query.filter(
                        Revision.hash == revision.hash
                   ).first()

        if existing: # We already have this file
            if not existing in user.revisions:
                user.revisions.append(existing)
            db.session.add(existing)
        else:
            user.revisions.append(revision)
            db.session.add(revision)

        db.session.add(user)
        db.session.commit()
       
        if revision.public:
            threads = []
            for router in app.routes.values():
                threads.append(gevent.spawn(router.__setitem__, revision, revision))
            gevent.joinall(threads)

        return redirect("/")

class UserRevisionCountResource(restful.Resource):
    def get(self, username):
        user = auth(session, required=True)

        if user.username != username and not user.can("see_all"):
            return {}, 403

        user = User.query.filter(User.username == username).first()
        if user == None:
            return 404

        return Revision.query.filter(Revision.user == user).count()

class UserFriendsCollection(restful.Resource):
    def get(self, username):
        user = auth(session, required=True)

        parser = reqparse.RequestParser()
        parser.add_argument("page",     type=int, default=1)
        parser.add_argument("per_page", type=int, default=10)
        args = parser.parse_args()  

        if user.username != username and not user.can("see_all"):
            return {}, 403

        if user.username != username:
            user = User.query.filter(User.username == username).first()
            if not user:
                return {}, 404

        query = Friend.query.filter(Friend.user == user)\
            .order_by(desc(Friend.created)).paginate(args.page, args.per_page)

        response = make_response(request.url, query)

        # Check the remote side of each request
        for i, friend_request in enumerate(response['data']):
            address = friend_request['address']
            network, node_id, uid = address.split('/')
            router = app.routes.get(network, None)
            if router != None:
                message_body = {"add": {"from": user.uid, "to": address}}
                remote_state = router.protocol.rpc_friend(message_body)
                if remote_state[0]:
                    response['data'][i]['status'] = remote_state[0]['status']

        return response

    def put(self, username):
        """
        Add a friend on a remote instance.
        """
        user = auth(session, required=True)

        parser = reqparse.RequestParser()
        parser.add_argument("name",    type=str, default="")
        parser.add_argument("address", type=str, required=True)
        args = parser.parse_args()

        # Parse the address and contact the node in question.
        # node = NodeSpider(node)
        if args.address.count("/") != 2:
            return False

        network_name, node_id, remote_uid = args.address.split("/")
        router = app.routes.get(network_name, None)
        if router == None:
            return {}, 404

        log("%s is adding a remote friend." % user.username)
        request        = {"add": {"from": user.uid, "to": args.address}}
        response, node = router.protocol.rpc_friend(request)

        if not response:
            return {}, 404

        if Friend.query.filter(and_(Friend.address == args.address,
            Friend.user == user)).first():
            return {}, 304

        # Add a peer instance so the remote sides' public key is
        # accesible for encrypting data we transmit to this friend.
        network = Network.query.filter(Network.name == network_name).first()
        
        if network != None:
            network = Network(name = network_name)

        peer = Peer.query.filter(
                    and_(Peer.network == network,
                         Peer.ip      == node.ip,
                         Peer.port    == node.port)
                ).first()

        if peer == None:
            peer = Peer()
            peer.load_node(node)

        friend       = Friend(address=args.address)
        friend.name  = args.name
        friend.state = 1

        user.friends.append(friend)
        peer.pubkey.friends.append(friend)
        
        db.session.add(peer)
        db.session.add(network)

        db.session.add(user)
        db.session.add(friend)
        db.session.commit()

        return response, 201

    def post(self, username):
        """
        Rename, accept or block a Friend. Refer to models.Friend.states
        to see what the possible integer values accepted by this method
        represent.

        Friends with their "received" attribute set to None cannot have
        their state attribute modified as they represent sent requests.
        """
        user = auth(session, required=True)

        parser = reqparse.RequestParser()
        parser.add_argument("state",   type=int)
        parser.add_argument("name",    type=str)
        parser.add_argument("address", type=str, required=True)
        args = parser.parse_args()

        friend =  Friend.query.filter(and_(Friend.address == args.address,
            Friend.user == user)).first()

        if not friend:
            return {}, 404
        
        if args.name:
            friend.name  = args.name
        if args.state:
            friend.state = args.state
        db.session.add(friend)
        db.session.commit()

        return friend.jsonify()

    def delete(self, username):
        """
        Unfriend an address.
        """
        user = auth(session, required=True)

        parser = reqparse.RequestParser()
        parser.add_argument("address", type=str, required=True)
        args = parser.parse_args()
       
        # Will do for now
        for friend in user.friends:
            if friend.address == args.address:
                db.session.delete(friend)
                db.session.commit()
                return {}, 204

        return {}, 404

class UserAvatarResource(restful.Resource):
    def get(self, username):
        user = User.query.filter(User.username == username).first()
        if not user:
            return {}, 404

        if not user.avatar:
            return {}, 404

        return user.avatar.as_response

    def post(self, username):
        user   = auth(session, required=True)
        
        if not 'avatar' in request.files:
            return {}, 400
        
        upload = request.files['avatar']

        revision = Revision()
        revision.add(upload)
        
        existing = Revision.query.filter(
                        Revision.hash == revision.hash
                   ).first()

        if existing: # We already have this file
            user.avatar = existing
            if not existing in user.revisions:
                user.revisions.append(existing)
            db.session.add(existing)
        else:
            user.avatar = revision
            user.revisions.append(revision)
            db.session.add(revision)

        db.session.add(user)
        db.session.commit()
        
        return redirect("/")
