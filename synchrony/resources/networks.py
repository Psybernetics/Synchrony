"""
Defines a paginated view of overlay networks the application is configured to
see as legitimate.
"""
from synchrony import app
import flask_restful as restful
from flask import session, request
from synchrony.controllers.auth import auth
from synchrony.controllers.utils import Pagination, make_response

class NetworkCollection(restful.Resource):

    def get(self):
        auth(session, required=True)
        parser = restful.reqparse.RequestParser()
        parser.add_argument("page",     type=int, required=False, default=1)
        parser.add_argument("per_page", type=int, required=False, default=10)
        args = parser.parse_args()

        routes      = app.routes.values()
        pages       = Pagination(routes, args.page, args.per_page)
        response    = make_response(request.url, pages)
        peer_count  = 0

        for router in routes:
            peer_count   += len(router)
        response['peers'] = peer_count

        return response

        # If you're here because you're wondering what the "private" attribute
        # in the responses means: It's for networks composed of nodes who all
        # have the same private/public keypair and will only accept new peers
        # who can decrypt for that key. This is useful for guaranteeing that
        # nodes using --autoreplicate only replicate for your instances.


class NetworkResource(restful.Resource):
    """
    Retrieve a specific network.
    """
    def get(self, network):
        auth(session, required=True)
        network = app.routes.get(network, None)
        if network == None:
            return {}, 404

        return network.jsonify()

class NetworkPeerCollection(restful.Resource):
    """
    Retrieve the peer nodes we know of for a specific network.
    """
    def get(self, network):
        """
        Currently returns /all/ peers we know of,
        but it should be a paginated resource.
        """
        auth(session, required=True)
        parser = restful.reqparse.RequestParser()
        parser.add_argument("page",     type=int, required=False, default=1)
        parser.add_argument("per_page", type=int, required=False, default=10)
        args = parser.parse_args()

        routes = app.routes.get(network, None)
        if not routes:
            return {}, 404
 
        peers = [peer for peer in routes]
        pages = Pagination(peers, args.page, args.per_page)
        return make_response(request.url, pages)


