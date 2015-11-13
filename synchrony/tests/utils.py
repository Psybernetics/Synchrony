"""
Implements a base class for all Synchrony test suites to quickly create peer nodes.
"""
import pprint
import random
import unittest
from synchrony import app
from synchrony.models import Revision
from synchrony.controllers import dht
from synchrony.controllers.utils import exclude

class BaseSuite(unittest.TestCase):

    peer_amount    = 10
    storage_method = "rpc_append"

    def setUp(self):
        """
        This method will probably form the basis of other tests.
        """
        print
        print "Creating %i peers configured to use %s." % \
            (self.peer_amount, self.storage_method)

        self.peers = create_peers(self.peer_amount, self.storage_method)

        # We add these RoutingTable objects as an attribute of mock_transmit
        # so it may find other nodes and work on their protocol instances.
        # We also monkey patch dht.fetch revision to avert network calls.
        mock_transmit.peers = self.peers
        dht.transmit        = mock_transmit
        for key in self.peers:
            self.peers[key].protocol.fetch_revision = mock_fetch_revision

def create_peers(peer_amount, storage_method):
    peers = {}
    for x in range(peer_amount):
        peers[x] = dht.RoutingTable(
                "127.0.0.1",
                random.randint(0,99999),
                app.key.publickey().exportKey(),
                None,
        )
        peers[x].buckets = [dht.KBucket(0,2**160,20)]
        rpcmethod = getattr(peers[x].protocol, storage_method, None)
        if not rpcmethod:
            raise Exception("Unknown storage method: %s" % storage_method)
        peers[x].storage_method = rpcmethod
    log = dht.log

    # We check for unique port numbers because addr is usually an (ip, port)
    # tuple when calling dht.transmit.
    ports = []
    for p in peers.values():
        ports.append(p.node.port)
    unique_ports = len(set(ports)) == len(peers.keys())
    log("Unique port numbers: %s" % str("Yes." if unique_ports else "No. Recreating."))
    if not unique_ports:
        return create_peers(peer_amount, storage_method)
        
    log("Introducing peers to one another.")
    dht.log = lambda x: x
    for peer in peers.values():
        [peer.add_contact(router.node) for router in peers.values()]
    dht.log = log
    print pprint.pformat(peers)
    return peers


def mock_transmit(routes, addr, data):
    """
    Put dht.RoutingTable instances through to one another without calling out
    to the network.
    """
    if not hasattr(mock_transmit, "peers"):
        dht.log("Can't find test peers.")
        dht.log("synchrony.test.utils.mock_transmit is missing a peers object.")
        return

    peer_routes = filter(
        lambda r: r if r.node.port == addr[1] else 0,
        [r for r in mock_transmit.peers.values()]
    )

    if not peer_routes:
        dht.log("Unknown peer %s:%i" % addr)
        return

    peer_routes = peer_routes[0]
    data = dht.envelope(routes, data)

    for field in data.keys():
        if field.startswith('rpc_'):
            rpc_name = 'handle_%s' % field.replace('rpc_', '')
            rpc_method = getattr(peer_routes.protocol, rpc_name, None)
            if not rpc_method:
                log("%s tried to call unknown procedure %s." % \
                    (routes.node, rpc_name), "warning")
                return
            return rpc_method(data)

def mock_fetch_revision(content_hash, nodes):
    return  Revision.query.filter(Revision.hash == content_hash).first()
