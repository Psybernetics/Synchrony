# Revision.get(hash)
# Revision.delete(hash)
# /v1/revisions/<hash>
# /v1/revisions/<hash>/content
from synchrony import app, db
import flask_restful as restful
from flask import request, session
from synchrony.models import Revision
from sqlalchemy import and_, or_, desc
from synchrony.controllers.auth import auth
from synchrony.controllers.utils import Pagination, make_response

class RevisionCollection(restful.Resource):
    def get(self):
        user = auth(session, required=True)

        parser = restful.reqparse.RequestParser()
        parser.add_argument("page",type=int, help="", required=False, default=1)
        parser.add_argument("per_page",type=int, help="", required=False, default=10)
        args = parser.parse_args()  

        if user.can("see_all"):
            query = Revision.query.order_by(desc(Revision.created)).paginate(args.page, args.per_page)
        else:
            query = Revision.query.filter(or_(Revision.public == True, Revision.user == user))\
                .order_by(desc(Revision.created)).paginate(args.page, args.per_page)

        return make_response(request.url, query)


class RevisionResource(restful.Resource):
    def get(self, hash):
        """
        Return a specific revision by hash.
        """
        user = auth(session)
        rev  = Revision.query.filter(and_(Revision.hash == hash, Revision.user == user)).first()
        if rev:
            return rev.jsonify()
        return {}, 404

    def post(self, hash):
        """
        Modify attributes of an existing revision.
        """
        user = auth(session, required=True)

        parser = restful.reqparse.RequestParser()
        parser.add_argument("public", type=bool, help="", required=True, default=None)
        args = parser.parse_args()  

        rev  = Revision.query.filter(and_(Revision.hash == hash, Revision.user == user)).first()
        if rev:
            if args.public != None:
                rev.public = args.public
                # Broadcast to overlay networks when a revision's made public.
                if args.public == True:
                    for router in app.routes:
                        app.routes[router][rev] = rev

            db.session.add(rev)
            db.session.commit()
            return rev.jsonify()

        return {}, 404

    def delete(self, hash):
        """
        Delete a revision object by hash.
        """
        user = auth(session, required=True)

        if user.can("delete_at_will"):
            rev  = Revision.query.filter(Revision.hash == hash).first()
        else:
            rev  = Revision.query.filter(
                    and_(Revision.hash == hash, Revision.user == user)
                   ).first()
        
        if not rev:
            return {}, 404

        db.session.delete(rev)
        db.session.commit()
        return {}, 204

class RevisionContentResource(restful.Resource):
    def get(self, hash):
        user = auth(session)
        rev  = Revision.query.filter(and_(Revision.hash == hash, Revision.user == user)).first()
        if rev:
            return rev.as_response
        return {}, 404

class RevisionDownloadsCollection(restful.Resource):
    def get(self):
        """
        Return all DHT downloads across all networks.
        """
        user = auth(session, required=True)

        parser = restful.reqparse.RequestParser()
        parser.add_argument("page",type=int, help="", required=False, default=1)
        parser.add_argument("per_page",type=int, help="", required=False, default=10)
        args = parser.parse_args()  

        if not user.can("see_all") and not user.can("review_downloads"):
            return {}, 403

        response = []
        for routes in app.routes.values():
            r = {'network': routes.network}
            r['downloads'] = [{f: routes.protocol.downloads[f]} for \
                f in routes.protocol.downloads]
            response.append(r)
        
        pages = Pagination(response, args.page, args.per_page)
        return make_response(request.url, pages, jsonify=False)

class RevisionDownloadsResource(restful.Resource):
    def get(self, network):
        """
        Provides an overview of revisions fetched via overlay network.

        Would be part of RevisionFeedbackResource except this has no need
        for a "hash" param.
        """
        user = auth(session, required=True)

        if not user.can("see_all") and not user.can("review_downloads"):
            return {}, 403

        if not network:
            routes = app.routes._default
        else:
            routes = app.routes.get(network, None)
            if not routes:
                return {}, 404

        return [f for f in routes.protocol.downloads]

    def post(self, network):
        """
        Decrements a peers trust rating and deletes the offending revision.
        """
        user   = auth(session, required=True)
        parser = restful.reqparse.RequestParser()
        parser.add_argument("url",      type=str, required=True)
        parser.add_argument("hash",     type=str, required=True)
        parser.add_argument("severity", type=int, required=True)
        args   = parser.parse_args()

        if not user.can("review_downloads"):
            return {}, 403

        routes = app.routes.get(network, None)
        if not routes:
            return "Network not found.", 404

        hashes = routes.protocol.downloads.get(args.url)
        if not hashes:
            return {}, 404

        addr = hashes.get(args.hash, None)
        if not addr:
            return "Peer not found.", 404

        # Delete the revision in question by hash
        revision = Revision.query.filter(Revision.hash == args.hash).first()
        if not revision:
            return "Revision not found.", 404

        db.session.delete(revision)
        db.session.commit()

        # Too severe, Enhance Your Calm
        if args.severity > 100:
            return {}, 420

        success = routes.protocol.decrement_trust(addr, args.severity)
        # Peer is 410 Gone
        if not success:
            return "Peer had already left.", 410

        return {}, 200


