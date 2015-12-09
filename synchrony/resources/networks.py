"""
Defines network-related endpoints used in the settings and network settings
views.
"""
from synchrony import app
import flask_restful as restful
from flask import session, request
from synchrony.controllers.auth  import auth
from synchrony.controllers.dht   import RoutingTable, log
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

    def put(self):
        user = auth(session, required=True)
        parser = restful.reqparse.RequestParser()
        parser.add_argument("name", type=str, required=True)
        args = parser.parse_args()

        if not user.can("manage_networks"):
            return {}, 403

        if app.routes.get(args.name, None):
            return {}, 409

        log('%s is creating a network named "%s".' % (user.username, args.name))

        # Derive settings from the default routing table
        settings = app.routes._default
        pubkey   = app.key.publickey().exportKey()
        ip       = settings.node.ip
        port     = settings.node.port
        router   = RoutingTable(ip, port, pubkey, settings.httpd, network=args.name)

        app.routes.append(router)
        return router.jsonify()

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

    def delete(self, network):
        """
        Remove a network.
        """
        user   = auth(session, required=True)
        routes = app.routes.get(network, None)
        if routes == None:
            return {}, 404

        if not user.can("manage_networks"):
            return {}, 403

        log("%s is removing network \"%s\"." % (user.username, network))
        app.routes.leave(network)

class NetworkPeerCollection(restful.Resource):
    """
    Retrieve the peer nodes we know of for a specific network.

    Node IDs are changed to strings to represent them without change on the
    frontend.
    """
    def get(self, network):
        auth(session, required=True)
        parser = restful.reqparse.RequestParser()
        parser.add_argument("page",     type=int, default=1)
        parser.add_argument("per_page", type=int, default=10)
        args = parser.parse_args()

        routes = app.routes.get(network, None)
        if not routes:
            return {}, 404
 
        peers       = [peer for peer in routes]
        pages       = Pagination(peers, args.page, args.per_page)
        pages.items = [p.jsonify(string_id=True) for p in pages.items]

        # Would like to make the following more elegant.
#        for i, j in enumerate(pages.items):
#            pages.items[i]['node'] = (str(j['node'][0]), j['node'][1], j['node'][2])

        return make_response(request.url, pages, jsonify=False)

    def post(self, network):
        """
        Hosts here is a comma-seperated list of ip:port pairs.
        """
        user   = auth(session, required=True)
        parser = restful.reqparse.RequestParser()
        parser.add_argument("hosts", type=str)
        args   = parser.parse_args()

        routes = app.routes.get(network, None)
        if routes == None:
            return {}, 404

        if not user.can("manage_networks"):
            return {}, 403

        # Get hosts as a list of "ip:port" strings
        hosts = args.hosts.replace(" ", "").split(',')
        def tuplify(host):
            if not ':' in host:
                return
            host = host.split(':')
            return tuple([host[0], int(host[1])])
        hosts = [tuplify(h) for h in hosts]

        # Emulate RoutingTable.bootstrap
        nodes = []
        for host in hosts:
            if host == None: continue
            log("Pinging %s:%i" % host)
            nodes.append(routes.protocol.rpc_ping(host))
        
        response = []
        for node in nodes:
            if node:
               response.append(node.jsonify(string_id=True))

        return response

    def delete(self, network):
        """
        Remove a peer.
        """
        user   = auth(session, required=True)
        parser = restful.reqparse.RequestParser()
        parser.add_argument("hosts", type=str)
        args   = parser.parse_args()

        routes = app.routes.get(network, None)
        if routes == None:
            return {}, 404

        if not user.can("manage_networks"):
            return {}, 403

