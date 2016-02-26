import flask_restful as restful
from sqlalchemy import and_, desc
from flask import request, session
from synchrony import app, db, log
from synchrony.controllers.auth import auth
from synchrony.controllers.utils import make_response
from synchrony.models import User, UserGroup, Acl, Priv

class UserGroupCollection(restful.Resource):
    def get(self):
        """
        Implements /v1/groups
        """
        parser = restful.reqparse.RequestParser()
        parser.add_argument("page",     type=int, required=False, default=1)
        parser.add_argument("per_page", type=int, required=False, default=10)
        args = parser.parse_args()

        user = auth(session, required=True)

        if not user.can("see_all"):
            return {}, 403

        query = UserGroup.query.order_by(desc(UserGroup.created)).paginate(args.page, args.per_page)
        
        return make_response(request.url, query)

    def put(self):
        """
        Create a new usergroup by name.
        """
        parser = restful.reqparse.RequestParser()
        parser.add_argument("name", type=str, required=True)
        args = parser.parse_args()

        user = auth(session, required=True)

        if not user.can("modify_usergroup"):
            return {}, 403

        group = UserGroup(name=args.name)

        db.session.add(group)
        db.session.commit()

        return group.jsonify()

    def delete(self):
        """
        Remove a usergroup by name.
        """
        parser = restful.reqparse.RequestParser()
        parser.add_argument("name", type=str, required=True)
        args = parser.parse_args()
    
        user = auth(session, required=True)
        group = UserGroup.query.filter(UserGroup.name == args.name).first()

        db.session.delete(group)
        db.session.commit()
        return {}, 204

class UserGroupResource(restful.Resource):
    """
    Implements /v1/groups/:groupname
    """
    def get(self, name):
        user = auth(session, required=True)

        group = UserGroup.query.filter(UserGroup.name == name).first()
        if not group:
            return {}, 404

        return group.jsonify(with_users=True, with_privs=True)
       
    def post(self, name):
        parser = restful.reqparse.RequestParser()
        parser.add_argument("allow",  type=str, default=None)
        parser.add_argument("deny",   type=str, default=None)
        parser.add_argument("add",    type=str, default=None)
        parser.add_argument("remove", type=str, default=None)
        args = parser.parse_args()

        user = auth(session, required=True)

        if not user.can("modify_usergroup"):
            return {}, 403

        group = UserGroup.query.filter(UserGroup.name == name).first()
        if not group:
            return {}, 404

        if args.allow:
            if ',' in args.allow:
                privs = args.allow.split(',')
            else:
                privs = [args.allow]
            for priv_name in privs:
                priv = Priv.query.filter(Priv.name == priv_name).first()
                if not priv: continue
                acl = Acl.query.filter(and_(Acl.priv == priv, Acl.group == group)).first()
                if acl: 
                    acl.allowed = True
                    db.session.add(acl)
                    continue
                acl = Acl()
                acl.priv  = priv
                acl.group = group
                acl.allowed = True
                db.session.add(acl)

        if args.deny:
            if ',' in args.deny:
                privs = args.deny.split(',')
            else:
                privs = [args.deny]
            for priv_name in privs:
                priv = Priv.query.filter(Priv.name == priv_name).first()
                if not priv: continue
                acl = Acl.query.filter(and_(Acl.priv == priv, Acl.group == group)).first()
                if acl: 
                    acl.allowed = False
                    db.session.add(acl)
                    continue
                acl = Acl()
                acl.priv  = priv
                acl.group = group
                acl.allowed = False
                db.session.add(acl)

            if args.add:
                if ',' in args.add:
                    users = args.add.split(',')
                else:
                    users = [args.add]
                for username in users:
                    user = User.query.filter(User.username == username).first()
                    if not user: continue
                    if user in group.users: continue
                    group.users.append(user)

            if args.remove:
                if ',' in args.remove:
                    users = args.remove.split(',')
                else:
                    users = [args.remove]
                for username in users:
                    user = User.query.filter(User.username == username).first()
                    if not user: continue
                    if user not in group.users: continue
                    group.users.remove(user)


        db.session.add(group)
        db.session.commit()

        return group.jsonify(with_users=True, with_privs=True)

