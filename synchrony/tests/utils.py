# _*_ coding: utf-8 _*_
"""
Implements a base class for all Synchrony test suites to quickly create peer nodes.
"""
import pprint
import random
import unittest
from copy import deepcopy
from synchrony import app
from synchrony.models import Revision
from synchrony.controllers import dht
from synchrony.controllers.utils import exclude

class BaseSuite(unittest.TestCase):

    dfp            = 0.0          # 0% of peers are malicious by default
    alpha          = 0.0
    beta           = 0.85         # Normalisation factor
    iterations     = 100          # calculate_trust iterates 100 times by default
    peer_amount    = 25
    storage_method = "rpc_append"

    def setUp(self):
        print "\nCreating %i peers configured to use %s." % \
            (self.peer_amount, self.storage_method)

        self.peers = create_peers(self.peer_amount, self.storage_method)

        count = int(len(self.peers) * self.dfp)
#        dht.log("%i peers will be malicious for this test." % count)
#        for i in range(count):
#            self.peers[i] ...

        # All remaining peers considered honest are automatically
        # added to one anothers' bucket of pre-trusted peers.
        #
        # Your test suite(s) will want to adjust this manually after the fact.
        
        self.honest_peers = {}
        honest_count = len(self.peers) - count
        dht.log("Introducing %i pre-trusted peers to one another." % honest_count)
        for j in range(honest_count):
            self.honest_peers[self.peers[count+j].node.long_id] = self.peers[count+j]

        for router in self.honest_peers.values():
            router.tbucket.update(self.honest_peers)

        # We add these RoutingTable objects as an attribute of mock_transmit
        # so it may find other nodes and work on their protocol instances.
        # We also monkey patch dht.fetch revision to avert network calls.
        mock_transmit.peers       = self.peers
        dht.transmit              = mock_transmit
        mock_get.peers            = self.peers
        dht.get                   = mock_get
        mock_fetch_revision.peers = self.peers
        for key in self.peers:
            self.peers[key].protocol.fetch_revision = mock_fetch_revision

def create_peers(peer_amount, storage_method):
    peers = {}
    for i in range(peer_amount):
        peers[i] = dht.RoutingTable(
                "127.0.0.1",
                random.randint(0, 999999),
                app.key.publickey().exportKey(),
                None,
        )
        peers[i].buckets = [dht.KBucket(0, 2**160, 20)]
        rpcmethod = getattr(peers[i].protocol, storage_method, None)
        if not rpcmethod:
            raise Exception("Unknown storage method: %s" % storage_method)
        peers[i].storage_method = rpcmethod
        # Attempted pings in add_contact would cause some previously
        # added peers to be promptly removed. We manually swap the method
        # for a mockup and reintroduce the original once we have our set of peers.
        peers[i].protocol.original_ping = peers[i].protocol.rpc_ping
        peers[i].protocol.rpc_ping = mock_ping

    log = dht.log
    # We check for unique port numbers because addr is /usually/ an (ip, port)
    # tuple when calling dht.transmit.
    ports = [p.node.port for p in peers.values()]
    unique_ports = len(set(ports)) == len(peers.keys())
    log("Unique port numbers: %s" % str("Yes." if unique_ports else "No. Recreating."))
    if not unique_ports:
        return create_peers(peer_amount, storage_method)
 
    log("Introducing peers to one another.")
    dht.log = lambda x, y=None: x
    for peer in peers.values():
        [peer.add_contact(router.node) for router in peers.values()]
    dht.log = log
    print pprint.pformat(peers)
    
    # Please god, forgive this fourth loop?
    for p in peers.values():
        peer.protocol.rpc_ping = peer.protocol.original_ping
    return peers

def mock_ping(addr):
    return

def mock_transmit(routes, addr, data):
    """
    Put dht.RoutingTable instances through to one another without calling out
    to the network.
    """
    # Test case setup method should set a peers attr on this function beforehand
    if not hasattr(mock_transmit, "peers"):
        dht.log("Can't find test peers.")
        dht.log("synchrony.test.utils.mock_transmit is missing a peers dictionary.")
        return

    if isinstance(addr, dht.Node):
        addr = (addr.ip, addr.port)

    # Filter for everyone who isn't the intended recipient
    peer_routes = filter(
        lambda r: r if r.node.port == addr[1] else None,
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

def mock_get(addr, path, field="data", all=True):

    if isinstance(addr, dht.Node):
        f = lambda f: f.node.threeple == addr.threeple
        addr = filter(f, mock_get.peers.values())
        if addr:
            return [p.jsonify() for p in addr[0]]
   
    return []

def mock_fetch_revision(url, content_hash, nodes):
    #
    return  Revision.query.filter(Revision.hash == content_hash).first()
