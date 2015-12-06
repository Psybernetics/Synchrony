import json
import hashlib
import binascii
from synchrony import app, log
import flask_restful as restful
from flask import session, request
from synchrony.controllers.dht import Node
from synchrony.controllers.auth import auth
from synchrony.models import Revision, local_subnets
from synchrony.controllers.utils import Pagination, validate_signature
from synchrony.controllers.utils import generate_node_id, make_response

class PeerCollection(restful.Resource):

    def get(self):
        """
        Currently returns /all/ peers we know of,
        but it should be a paginated resource.
        """
        auth(session, required=True)
        parser = restful.reqparse.RequestParser()
        parser.add_argument("page",type=int, help="", required=False, default=1)
        parser.add_argument("per_page",type=int, help="", required=False, default=10)
        parser.add_argument("network",type=str, help="", required=False, default=None)
        args = parser.parse_args()

        if not args.network:
            routes = app.routes._default
        else:
            routes = app.routes.get(args.network, None)
            if not routes:
                return {}, 404
 
        peers = [peer for peer in routes]
        pages = Pagination(peers, args.page, args.per_page)
        return make_response(request.url, pages)
    
    def post(self):
        """
        Unserialise the data and accept the following calls:
        PING
        CHAT
        EDIT
        APPEND
        LEAVING
        FIND_NODE
        FIND_VALUE

        APPEND signifies the requesting host has data for the given hash.
        """
        parser = restful.reqparse.RequestParser()
        parser.add_argument("data",      type=str, help="The RPC body.", default=None)
#        parser.add_argument("signature", type=str, help="Signature.", default=None)
#        parser.add_argument("pubkey",    type=str, help="Public key.", default=None)
        args = parser.parse_args()
        if not args.data:
            log("Received request from %s with no data." % request.remote_addr, "warning")
            return {}, 400

        response = []
        data = json.loads(args.data)

        if not validate_signature(data):
            log("Received message from %s with an invalid signature." % request.remote_addr, "warning")
            return "Invalid message signature.", 400

        if not 'node' in data:
            log("%s didn't provide useable information about themselves." % request.remote_addr, "warning")
            return {}, 400

        # Validate the node field for internet hosts
        if not any([request.remote_addr.startswith(subnet) for subnet in local_subnets]):
            stated_addr = data['node'][1]
            if stated_addr != request.remote_addr:
                log("Request made from %s stated it originated from %s" % (request.remote_addr, stated_addr), "warning")
                return "sicillian shrug", 418

        # Ensure this peer is using the node ID that corresponds to their ip, port and public key
        seed        = "%s:%i:%s" % (data['node'][1], data['node'][2], data['pubkey'])
        expected_id = long(generate_node_id(seed).encode('hex'), 16)
        if data['node'][0] != expected_id:
            log("%s is using an incorrect node ID." % request.remote_addr, "warning")
            log("Expecting %s but received %s" % (str(expected_id), str(data['node'][0])), "warning")
            return {}, 400

        # Determine which overlay network this request is concerned with
        if not 'network' in data:
            return {}, 400

        router = app.routes.get(data['network'], None)
        if router is None:
            return {}, 404

        # Execute the corresponding RPC handler
        for field in data.keys():
            if field.startswith('rpc_'):
                rpc_name = 'handle_%s' % field.replace('rpc_', '')
#                data[rpc_name] = data[field]
#                del data[field]
                rpc_method = getattr(router.protocol, rpc_name, None)
                if not rpc_method:
                    log("%s tried to call unknown procedure %s." % (request.remote_addr, rpc_name), "warning")
                    return {}, 400
                response = rpc_method(data)
                break

        return response

class PeerNetworkResource(restful.Resource):
    """
    A paginated collection of peers via network name.
    """

    def get(self, network):
        parser = restful.reqparse.RequestParser()
        parser.add_argument("page",     type=int, default=1)
        parser.add_argument("per_page", type=int, default=10)
        args = parser.parse_args()

        routes = app.routes.get(network, None)
        if not routes:
            return {}, 404

        peers    = [peer for peer in routes]
        pages    = Pagination(peers, args.page, args.per_page)
        response = routes.jsonify()

        response.update(make_response(request.url, pages))

        return response

class PeerResource(restful.Resource):
    """
    Defines a resource for returning a specific peer by node ID.
    """

    def get(self, network, node_id):
        routes = app.routes.get(network, None)
        if not routes:
            return {}, 404
        for node in routes:
            if node.long_id == node_id:
                return node.jsonify()
        return {}, 404

class PeerTestSet(restful.Resource):
    """
    Defines a resource that sets a random key to a random value in the DHT.
    Used for testing rpc_store_value.
    """

    def get(self):
        """
        Currently returns all peers we know of,
        but it should be a paginated resource.
        """
#        import random
#        import string
#        import hashlib
#        choices = list(string.ascii_lowercase)
#        key = random.choice(choices) + ".com/"
#        value = hashlib.sha1(random.choice(choices)).hexdigest()
#        app.routes[key] = value

        revision = Revision.query.first()
        app.routes._default[revision] = revision

        return [peer.jsonify() for peer in app.routes._default]

class PeerTestGet(restful.Resource):
    """
    Defines a resource that gets a key from the DHT.
    Used for testing rpc_find_value.
    """

    def get(self, url):
        """
        Grab some data from peers.
        """
        app.routes._default.protocol.republish_keys()
        rev = app.routes._default[url]
        if rev:
            return rev.as_response
        return {}, 404


class PublicRevisionCollection(restful.Resource):
    """
    Defines a paginated view of revisions that are publicly available from this
    instance.
    """
    def get(self):
        return [r.jsonify() for r in Revision.query.filter(Revision.public == True).all()]


class PublicRevisionResource(restful.Resource):
    """
    Permit peers to obtain a specific public revision.
    """
    def get(self, content_hash):
        revision = Revision.query.filter(Revision.hash == content_hash).first()
        if revision:
            app.bytes_sent += revision.size
            return revision.as_response
        return {},404
