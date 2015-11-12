# Revision.get(hash)
# Revision.delete(hash)
# /v1/revisions/<hash>
# /v1/revisions/<hash>/content
from synchrony import app, db
from flask.ext import restful
from synchrony.models import Revision
from flask import request, session
from sqlalchemy import and_, or_, desc
from synchrony.controllers.auth import auth
from synchrony.controllers.utils import make_response

class RevisionCollection(restful.Resource):
    def get(self):
        user = auth(session, required=True)

        per_page = 10

        parser = restful.reqparse.RequestParser()
        parser.add_argument("page",type=int, help="", required=False, default=1)
        parser.add_argument("content",type=bool, help="", required=False, default=None)
        args = parser.parse_args()  

        if user.can("see_all"):
            query = Revision.query.order_by(desc(Revision.created)).paginate(args.page, per_page)
        else:
            query = Revision.query.filter(or_(Revision.public == True, Revision.user == user))\
                .order_by(desc(Revision.created)).paginate(args.page, per_page)

        return make_response(request.url, query)


class RevisionResource(restful.Resource):
    def get(self, hash):
        user = auth(session)
        rev  = Revision.query.filter(and_(Revision.hash == hash, Revision.user == user)).first()
        if rev:
            return rev.jsonify()
        return {}, 404

    def post(self, hash):
        user = auth(session)

        parser = restful.reqparse.RequestParser()
        parser.add_argument("public",type=bool, help="", required=False, default=None)
        args = parser.parse_args()  

        rev  = Revision.query.filter(and_(Revision.hash == hash, Revision.user == user)).first()
        if rev:
            if args.public != None:
                rev.public = args.public

            db.session.add(rev)
            db.session.commit()
            return rev.jsonify()

        return {}, 404

class RevisionContentResource(restful.Resource):
    def get(self, hash):
        user = auth(session)
        rev  = Revision.query.filter(and_(Revision.hash == hash, Revision.user == user)).first()
        if rev:
            return rev.as_response
        return {}, 404

class RevisionFeedbackResource(restful.Resource):
    """
    Facilitates feedback into the system for bogus DHT revisions.
    """

    def post(self, network, hash):
        user = auth(session)

        parser = restful.reqparse.RequestParser()
        parser.add_argument("reason",type=int, help="", required=True)
        args = parser.parse_args()

        routes = app.routes.get(network, None)
        if not routes:
            return {}, 404

        return routes.protocol.decrement_trust(hash, args.reason)

class RevisionDownloadsResource(restful.Resource):
    """
    Provides an overview of revisions fetched via overlay network.

    Would be part of RevisionFeedbackResource except this has no need
    for a "hash" param.
    """

    def get(self, network=None):
        user = auth(session)
        if not network:
            routes = app.routes._default
        else:
            routes = app.routes.get(network, None)
            if not routes:
                return {}, 404

        return [f for f in routes.protocol.downloads]


