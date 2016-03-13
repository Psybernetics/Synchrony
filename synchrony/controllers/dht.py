# _*_ coding: utf-8 _*_
#
# Psybernetics 2015
# Original code from Kademlia Copyright (c) 2014 Brian Muller
# MIT License
#
"""
 See the corresponding file at synchrony/resources/peers.py for
 the process messages go through before being received by
 their counterpart methods in the protocol class.

 This namespace and synchrony/resources/peers.py implement an overlay network
 heavily based on Kademlia. If you're coming to this without having read the
 original paper you may want to take a couple of days to really grok it,
 hopefully it won't take that long because you have this software.

 These modules make it as easy as possible to participate in multiple networks.
 Telling peers you have data and obtaining data from peers looks like this:

    routes[url] = revision
    revision = routes[url]

 In the application itself, among multiple routing tables:

    app.routes._default[url] = revision
    revision = app.routes._default[url]


TODO/NOTES:
 Make revision selection strategies plug-and-play.

 protocol.copy_routing_table
 connection throttling

 Invite-only private networks based on FOAF public keys.
 Tag documents as edits or originals in rpc_append.
 Let users select whether they will accept edits. Default deny.

 A public revision is a public revision.

 CORS.
 Same-Origin policy.
 JavaScript.

 b64encoded/signed messages need a corresponding recv function.
 Possibly add self to peer tables by pinging peers received on bootstrap.
 Tell nodes if their clock is out of sync.


 Tit-for-tat: Forget peers who don't want to share well.
 A list of trusted peers (s/kademlia / trust managers for individual peers)

 React to a None return value in protocol.fetch_revision?

 Every message must contain the addresses of peers.

 An instance of Synchrony itself has a public/private keypair. This enables 
 messages to be signed regardless of whichever user accounts come and go,
 which is a form of identity. As far as the network is concerned, an
 APPEND_VALUE for some content comes from the instance of Synchrony rather than a
 specific user account.

 Want a resource? Hash the URL and use it as a node ID to ask if it or any neighbours
 have been informed of peers who have the data.

 /v1/peers/revisions/<string:hash> (direct download of public resources incl. binaries)
 use Content-Disposition: inline; filename="" to give a file its known name.

 Permit retrieval of files to start at an offset given (fsize / online_sufferers)
 > user visits example.com/picture.png and transmits the hash_1 made of the
   content
 > divides the pieces, hashes those and stores them as an association to hash-1
 > user transmits they have hash-1 based on example.com/picture.png
 > user may omit the domain from the url field, where peers with knowledge of 
   users' pubkey can pick up the broadcast, enabling user to multicast her own
   files to friends.

 Getting online video with a little help from our peers:
 > perform FIND for the content hash of a hypermedia object such as video or
   geometry.
 > initiate a request to the highest ranking peer of the resulting set R to
   obtain the size of the object.
 > divide file size between the cardinality of R.
 > initiate requests to the remaining members of R indicating you would like
   the specified number of bytes beginning at the specified byte.

 Transmit and remember hash(content + pubkey + prev_hash) for a raft-like log:
 > user performs an edit on "http://google.com/"
 > broadcasts they have content for hash(content + pubkey + prev_hash) based on
   "http://google.com/"
 > nodes remember this and relay it
 < "friend made public edit based on http://google.com/"

 TODO: Weighting of most recent-to-most-replicated.

 Can also present the user with a list of "addr | hash | count" of
 revisions we become privy to when querying for a URL, allowing the user
 to select precisely what's obtained for the request.

 data = {
   'time': 1441227835.867711,
   'peers': [(long_id,addr,port),...],
   'peers6': [],
   'sufferers': [], # other peers who've got this content
   'rpc_append': {
       'url_hash':'content_hash'
   },
 }
 This message would then be serialised as JSON, base64 encoded and signed:
 payload = b64encode(json.dumps(data)) 
 {
   'data':      payload,
   'pubkey':    app.key.publickey().exportKey(),
   'signature': app.key.sign(SHA256.new(payload).digest(), '')[0],
 }

 put various stages of find_value into the
 corresponding socket.io connection to update the view when loading resources.

"""
import gzip
import json
import math
import time
import heapq
import socket
import random
import pprint
import gevent
import base64
import operator
import urlparse
import requests
from io import BytesIO
from hashlib import sha1
from copy import deepcopy
from sqlalchemy import and_
from gevent import Greenlet
from synchrony import app, db
from gevent.coros import RLock
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from synchrony import log as _log
from gevent.greenlet import Greenlet
from gevent.event import AsyncResult
from synchrony.controllers import utils
from binascii import hexlify, unhexlify
from itertools import takewhile, imap, izip
from collections import OrderedDict, Counter
from synchrony.models import Revision, User, Friend, Network, Peer
from synchrony.streams.utils import change_channel, check_availability, broadcast

try:
    import numpy
except ImportError:
    numpy = None

class RoutingTable(object):
    """
    Routing is based on representative members of lists ("buckets") and an XOR
    metric.

    The ID space is a unidirectional number line of 160-bit binary values.
    This gives us 2^160 possible IDs and the ability to change direction on
    the line by XORing an ID against an arbitrary value.

    Lists of nodes are kept to size K and divided once K is reached.
    K is typically a number of nodes that're unlikely to go down in an hour of
    eachother, like 20.

    The most recently contacted or "best" node is kept at the head of the list,
    enabling messages to be routed in logarithmic distance proportionate to K.

    Contacting a node at the beginning of the number line from the middle only
    requires contacting the "best" nodes of the buckets responsible for that part
    of the space.

    Every hour we check for dead nodes and republish keys.
    """
    def __init__(self, addr, port, pubkey, httpd, ksize=20, alpha=3, id=None, nodes=[], network=None):
        """
        The first three options can be set to None.
        This is useful for testing from a live interpreter session.

        options are the command-line flags which lets us determine what port
        to tell peers to connect to. httpd contains an event loop that we attach
        to in order to periodically ping peers and tell them which URLs we're
        storing data for. upnp is a UPnP client for querying the gateway about
        what IP address we should tell peers to connect to.

        ksize is the bucket size, alpha is the amount of parallel requests to deal in,
        id is the previously used node ID for this instance as a peer.

        id may come from the database if we've previously been in the network before.
        nodes is a list of (address, port) tuples to bootstrap into the network with.
        """
        if not network:
            network = "Test Network"
        self.network = network
        self.httpd   = httpd
        self.ksize   = ksize
        self.alpha   = alpha
        self.private = None  # Private networks are ones in which
                             # we only accept peers who can also sign
                             # data using the same public key as ours.

        seed      = "%s:%i:%s" % (addr, port, pubkey)
        self.node = Node(id or utils.generate_node_id(seed),
                         addr,
                         port,
                         pubkey,
                         self)

        # An unbounded group of pre-trusted peers
        self.tbucket  = TBucket(self)
        # Our sublists of known peers
        self.buckets  = [KBucket(0, 2 ** 160, self.ksize)]
        # An instance of a protocol class implementing our RPCs
        self.protocol = SynchronyProtocol(self, Storage(), ksize)

        # This makes it easy for test suites select which method to use.
        # Note that if you are using a different store method then it's up to
        # you to set self.protocol up with any corresponding storage class(es).
        self.storage_method = self.protocol.rpc_append

        # Introduce previously known nodes.
        nodes = self.load(nodes)

        # Contact these peers and discover their peers
        self.bootstrap(nodes)

        if self.httpd:
            self.httpd.loop.run_callback(self.loop)
            log("Peers can bootstrap to %s:%i." % (addr, port))
            log("You're on network \"%s\"." % self.network)

    def loop(self):
        """
        Executes on program startup.
        Check for unresponsive nodes and republish keys every 24 hours.

        Please note that exceptions raised in any of the functions called here 
        can cause this method to cease recursing if not handled.
        """
        try:
            self.protocol.republish_keys()
        except Exception, e:
            log("Error republishing keys: %s." % e.message, "error")

        try:
            for peer in self:
                self.protocol.rpc_ping(peer)
        except Exception, e:
            log("Error pinging peers: %s" % e.message, "error")

        self.tbucket.calculate_trust()

        peers  = len(self)
        # 24 hours:
        timing = 86400
        # 1 hour:
        if peers <= 200:
            timing = timing / 8
            timing = timing / 3
        # 2 hours:
        elif peers <= 500:
            timing = timing / 4
            timing = timing / 3
        # 6 hours:
        elif peers <= 1500:
            timing = timing / 2
     
        hours = (timing / 60) / 60
        log("Pinging peers and republishing keys in %i hour%s." % \
                (hours,'s' if hours > 1 else ''))
        self.timer = self.httpd.loop.timer(timing)
        self.timer.start(self.loop)

    def bootstrap(self, addrs):
        """
        Bootstrap the server by connecting to other known nodes in the network.
        addrs is a list of (addr, port) tuples.
        """
        for addr in addrs:
            log("Pinging %s:%i" % addr)
            self.protocol.rpc_ping(addr)
        self.find_own_id()

    def find_own_id(self):
        """
        Perform FIND_NODE for our own ID per the paper.
        """
        nodes = [n for n in self]
        if nodes:
            spider  = NodeSpider(self.protocol, self.node, nodes, self.ksize, self.alpha)
            results = spider.find()
            unique  = True
            for node in results:
                if node.id == self.node.id and node.threeple != self.node.threeple:
                    log("A peer is already using this node ID.")
                    log("It's probably a stale reference to this instance so don't worry.")
        log("Using node ID " + str(self.node.long_id))

    def load(self, nodes):
        """
        Create a unique list of bootstrap nodes given an initial list.
        """
        network = Network.query.filter(Network.name == self.network).first()
        if network:
            for peer in network.peers:
                if peer.ip == self.node.ip and peer.port == self.node.port:
                    continue
                nodes.append((peer.ip, peer.port))
            nodes = list(set(nodes))
        return nodes

    def save(self):
        """
        Create or update a Network model representing this instance.
        """
        network = Network.query.filter(Network.name == self.network).first()
        if network == None:
            network = Network(name=self.network)

        # Persist our peers
        for node in self:
            peer = Peer.query.filter(
                        and_(Peer.network == network,
                             Peer.ip      == node.ip,
                             Peer.port    == node.port)
                    ).first()
            if not peer:
                peer = Peer()
            peer.load_node(node)
            network.peers.append(peer)
            db.session.add(peer)
        
        db.session.add(network)
        db.session.commit()

    def leave_network(self):
        """
        Create a spider to tell close peers we won't be available to respond
        to requests.
        """
        self.save()
        threads = []
        for node in self:
            threads.append(gevent.spawn(self.protocol.rpc_leaving, node))
        if threads:
            log("%s: Telling peers we're leaving the network." % self.network)
        gevent.joinall(threads)

    def split(self, index):
        one, two = self.buckets[index].split()
        self.buckets[index] = one
        self.buckets.insert(index+1, two)

    def get_lonely_buckets(self):
        return [b for b in self.buckets if b.last_updated < (time.time() - 3600)]

    def remove_node(self, node):
        log("Removing %s from contacts." % node)
        self.protocol.storage.remove_node(node)
        index = self.get_bucket_for(node)
        self.buckets[index].remove_node(node)

    def is_new_node(self, node):
        index = self.get_bucket_for(node)
        return self.buckets[index].is_new_node(node)

    def add_contact(self, node):
        if not self.is_new_node(node):
            return
        if node.id == self.node.id:
            return
#        if node.id == self.node.id or node.id in [n.id  for n in self]:
#            return
        # Validate node ID
        seed = "%s:%i:%s" % (node.ip, node.port, node.pubkey)
        if node.long_id != long(utils.generate_node_id(seed).encode('hex'), 16):
            # If you're seeing this on your internal network you might want to try
            # the --address option.
            log("Invalid node ID for %s." % node, "warning")
            return
        log("Adding %s to contacts." % node)
        index  = self.get_bucket_for(node)
        bucket = self.buckets[index]
        if bucket.add_node(node):
            return

        # Per section 4.2 of the paper, split if the bucket has the node in its range
        # or if the depth is not congruent to 0 mod 5
        if bucket.has_in_range(self.node) or bucket.depth() % 5 != 0:
            self.split(index)
            self.add_contact(node)
        else:
            # Ping the first node in the bucket
            self.protocol.rpc_ping(bucket.head())

    def get_existing_node(self, node):
        """
        Return a reference to a node if we already have it as a contact.
        """
        if isinstance(node, (list, tuple)):
            node = Node(*node)
        if not self.is_new_node(node):
            # Try finding the node by its id
            index = self.get_bucket_for(node)
            n = self.buckets[index].get_node(node)
            if n: return n

    def get_bucket_for(self, node):
        for index, bucket in enumerate(self.buckets):
            if node.long_id < bucket.range[1]:
                return index

    def find_neighbours(self, node, k=None, exclude=None):
        k = k or self.ksize
        nodes = []
        for neighbour in TableTraverser(self, node):
            if neighbour.id != node.id and (exclude is None or not neighbour.same_home(exclude)):
                heapq.heappush(nodes, (node.distance_to(neighbour), neighbour))
            if len(nodes) == k:
                break
        return map(operator.itemgetter(1), heapq.nsmallest(k, nodes))

    def __getitem__(self, key):
        """
        Get a revision if the network has it.

        The default strategy is most-replicated, for general safety (flooding?)
        with the capacity to opt for most-recent so that resources may age out
        of the DHT. Peers can be asked to list their public revisions for a URL.
        """        
        if isinstance(key, Revision): # This permits rev = app.routes[content_hash]
            if key.url:
                key = key.url
            else:
                key = key.hash

        # url here is passed to ValueSpider so it can be a parameter to
        # SynchronyProtocol.fetch_revision, which then sets
        # SynchronyProtocol.downloads correctly.
        # This is because tracking resource requests for <link>, <script> and
        # <img> elements via headers when the page is in an iframe isn't
        # supposed to be possible.
        # Instead, we memorise all DHT downloads and let admins provide feedback.
        url  = key
        node = Node(digest(key))
        nearest = self.find_neighbours(node)
        if len(nearest) == 0:
            log("There are no known neighbours to get %s" % key)
            return None
        
        # Long list of arguments but it helps us map {url: peer_who_served}
        spider = ValueSpider(
                self.protocol,
                node,
                nearest,
                self.ksize,
                self.alpha,
                url
                )
       
        # If spider.find() returns a revision object then it's only this method
        # you're reading that can associate it with the correct Resource and Domain.
        return spider.find()

    def __setitem__(self, url, content_hash):
        """
        Make peers aware that we have data for the hash of a URL.

        Unlike a traditional DHT we don't directly store data on peer nodes to replicate it,
        we instead make them aware that we have a copy of it and what the hash of it is.

        This allows for multiple strategies for obtaining revisions, such as most recent
        versus most-replicated.

        Peer nodes may also opt to replicate data for observed advertisements.
        """
        if isinstance(url, Revision):
            if url.url:                
                url = url.url          
            else:                # This permits the following:
                url = url.hash   # app.routes[rev] = rev
                                 # Even when the Revision has no .resource attribute.
        if isinstance(content_hash, Revision):
            content_hash = content_hash.hash

        hashed_url = digest(url)

        log("Adding local reference.")
        self.protocol.storage[hexlify(hashed_url)] = (content_hash, self.node)

        def store(nodes):
            """
            A closure for a dictionary of responses from alpha nodes containing
            peer information for neighbours close to a target key.

            These responses don't contain their own 'peers' field at the moment.
            """
            log("Telling %s we have %s." % (nodes, url))
            threads = [gevent.spawn(self.storage_method, node, hexlify(hashed_url),\
                    content_hash) for node in nodes]
            gevent.joinall(threads)
            threads = [thread.value for thread in threads]
            log("%s: %s" % (self.storage_method.func_name, threads))

        log("Telling peers we're storing %s [%s]." % (url, content_hash))
        node = Node(hashed_url)
        nearest = self.find_neighbours(node)
        if len(nearest) == 0:
            log("There are no neighbours to inform that we have data for %s" % url)
            return False
        spider = NodeSpider(self.protocol, node, nearest, self.ksize, self.alpha)
        return store(spider.find())

    def jsonify(self):
        res = {}
        res['name']    = self.network
        res['peers']   = len(self)
        res['private'] = self.private
        if hasattr(self, "node"):
            res['node_id'] = str(self.node.long_id)
        return res

    def __iter__(self):
        nodes = []
        for bucket in self.buckets:
            nodes.extend(bucket.nodes.values())
        return iter(nodes)

    def __len__(self):
        return len([n for n in self])

    def __repr__(self):
        return "<RoutingTable for \"%s\" with %i peers>" %  (self.network, len(self))

class SynchronyProtocol(object):
    def __init__(self, router, storage, ksize):
        """
        Methods beginning with rpc_ define our outward calls and their
        handle_ counterparts define how we deal with their receipt.
        Also requires a storage object.
        Check RoutingTable.__init__ to see how that works.
        
        As well as node ID generation we also use cryptographic keys here to
        encrypt methods such as RPC_CHAT and RPC_EDIT.
        There is a possible Man-in-the-Middle attack whereby a  malicious
        eavesdropping party intercepts the introduction of two peers to one
        another and replaces their keys with a new pair of public keys,
        deciphering communications in-transit and re-encrypting with the peers'
         real public keys on rebroadcast.

        This is best evaded by sharing your public key separately ahead of time.
        
        {"rpc_append":     {"url_hash":"content_hash"}}
        {"rpc_edit":       {"channel": [], "edit": subtree}}
        {"rpc_chat":       {'to': 'uid', 'from': ['uid', 'username'],
                            'type': "message" or "init" or "close" or "rtc",
                            'body': {'m':'content'}}}
        {"rpc_find_node":  "node_id"}
        {"rpc_find_value": "url_hash"}
        {"rpc_friend":
            [
                {"add": {"from": "uid", "to": "addr"}},
                {"remove": {"from": "uid", "to": "addr"}},
                {"status": {"from": "uid", "to": "addr", "type": "AO"}},
            ]
         "network": "alpha"
         "peers":   [...]
        }
        """
        self.ksize         = ksize
        self.router        = router
        self.epsilon       = 0.0001  # Don't use a different trust increment publicly.
        self.storage       = storage
        self.source_node   = router.node
        self.downloads     = ForgetfulStorage()         # content_hash -> (n.ip, n.port)
        self.received_keys = ForgetfulStorage(bound=2)  # node -> [republish_messages,..]

    def get_refresh_ids(self):
        """
        Get ids to search for to keep old buckets up to date.
        """
        ids = []
        for bucket in self.router.get_lonely_buckets():
            ids.append(random.randint(*bucket.range))
        return ids

    def rpc_ping(self, addr):
        # "addr" may be an (addr, port) tuple
        data = transmit(self.router, addr, {"rpc_ping": True})
        # Remove peer
        if not data:
            if isinstance(addr, Node):
                self.router.remove_node(addr)
            return
        node = Node(*data['node'], pubkey=data['pubkey'], router=self.router)
        self.router.add_contact(node)
        # FIXME: Ping nodes in the 'peers' part of the response.
        #        Don't let malicious nodes fill the routing table with
        #        information for peers who won't respond.
        if 'peers' in data:
            for peer in data['peers']:
                if peer['node'][0] == self.source_node.long_id:
                    continue
                peer = Node(*peer['node'],
                            pubkey=peer['pubkey'],
                            router=self.router)
                self.router.add_contact(peer)
#                self.rpc_ping(node)
        return node

    def rpc_report_trust(self, node_to_rate, node_to_tell):
        """
        The equivalent is a GET request to /v1/peers/node_id

        """
        pass

    def rpc_friend(self, message_body):
        """
        {"rpc_friend":
            [
                {"add": {"from": "uid", "to": "addr"}},
                {"remove": {"from": "uid", "to": "addr"}},
                {"status": {"from": "uid", "to": "addr", "type": "AO"}},
            ]
         "network": "alpha"
         "peers":   [...]
        }

        addr is of the form "network_name/node_id/remote_user_id".
        RPC_FRIEND messages can be batched together.
        
        TODO: The type field for status messages should support
            
            AFK - Away
            A   - Available
            O   - (Appear) Offline
            GET - Request status of remote friend

        """
        if not isinstance(message_body, list):
            message_body = [message_body]

        node    = None
        payload = []

        for message in message_body:
            message_type = message.keys()[0]
            addr = message[message_type]["to"]

            if addr.count("/") != 2:
                log("Invalid address %s" % addr)
                return False, None
            network, node_id, remote_uid = addr.split("/")
            
            if network != self.router.network:
                return False, None

            node = Node(long(node_id))
            nearest = self.router.find_neighbours(node)
            if len(nearest) == 0:
                log("There are no neighbours to help us add users on %s as friends." % \
                    node_id)
                return False, None
            spider  = NodeSpider(self, node, nearest, self.ksize, self.router.alpha)
            nodes   = spider.find()
            node    = None

            if len(nodes) > 1:
                for _ in nodes:
                    if str(_.long_id) == node_id:
                        node = _

            # Sometimes spidering doesn't get us all the way there.
            # Check who we already know:
            if node == None:
                nodes = [n for n in self.router if str(n.long_id) == node_id]
                if len(nodes) != 1:
                    log("Node %s not found via spidering." % node_id, "warning")
                    return False, None
                node = nodes[0]

            log(node_id, "debug")
            log(node.long_id, "debug")

            log("Found remote instance %s." % node)

        if not node:
            log("No peer node found for RPC_FRIEND %s" % message_type.upper())
            return False, None

        response = transmit(self.router, node, {"rpc_friend": message_body})
    
        if not isinstance(response, dict) or not "response" in response:
            return False, None

        return response['response'], node

    def rpc_chat(self, nodeple, data):
        """
        Implements CHAT where we encrypt a message destined for the user with
        UID on the receiving node.

        Message data should be of the form
        { 
           'to': 'uid',
           'from': ['uid', 'username'],
           'type': "message" or "init" or "close" or "rtc"
           'body': {'m':'content'}
        }
        """
        # Worth retaining this ping call for the routing information we get.
        node     = self.rpc_ping(nodeple)
        
        if node == None:
            return

        data     = base64.b64encode(json.dumps(data))
        key      = RSA.importKey(node.pubkey)
        data     = key.encrypt(data, 32)
        data     = base64.b64encode(data[0])
        response = transmit(self.router, node, {'rpc_chat': data})
        log(response, "debug")
        return response

    def rpc_edit(self, data):
        """
        Inter-instance EDIT.

        Message data should be of the form
        { 
           'to':      "network/node_id/user_id"
           'from':    ['uid', 'username'],
           'type':    "edit", or "invite"
           'body':    '<span>DOM nodes to match and replace</span>'
        }   
        """
        if not "to" in data: return
        
        network, node_id, user_id = data["to"].split("/")
        node_id = long(node_id)

        node = self.router.get_existing_node(Node(node_id))
        if node == None:
            return

        data = base64.b64encode(json.dumps(data))
        key  = RSA.importKey(node.pubkey)
        data = key.encrypt(data, 32)
        transmit(self.router, node, {'rpc_edit': data})

    def rpc_leaving(self, node):
        addr = self.get_address(node)
        return transmit(self.router, addr, {"rpc_leaving":True})

    def rpc_append(self, node, url_hash, content_hash):
        """
        Allows senders to tell peers they have the data for the hash of a path.
        Hash here is the hash made from the content the peer has stored.
        They're letting you know they have data that corresponds to the hash.
        {
         peers:       [],
         pubkey:      "",
         signature:   "",
         time:        1440064069.0,
         rpc_append:  {url_hash: content_hash},
        }
        """
        # Append this peer to the list of nodes storing data for this path
        # urls[data['url']].append(sender)
        addr = self.get_address(node)
        data = {"rpc_append": {url_hash: content_hash}}
#        if addr.threeple == self.source_node.threeple:
#            self.storage[url_hash] = (content_hash, addr)
        return transmit(self.router, addr, data)

    def rpc_find_node(self, node_to_ask, node_to_find):
        address = (node_to_ask.ip, node_to_ask.port)
        message = {'key': node_to_find.id}
        message = envelope(self.router, message)
        return self.handle_find_node(message)

    def rpc_find_value(self, node_to_ask, node_to_find):
        address = (node_to_ask.ip, node_to_ask.port)
        message = {'rpc_find_value': hexlify(node_to_find.id)}
        return transmit(self.router, address, message)

    def rpc_transfer_routing_table(self, sender, nodeid):
        pass 

    def rpc_republish(self, node, data):
        """
        Please refer to SynchronyProtocol.republish_keys to see what's really going
        on here.
        
        The data argument here is a list that looks like this:
        [{'node': [[nodeple], 'pubkey'],'keys': {signature: key_data}}, ...]
        Where "key_data" is a b64encoded JSON dump of the return value for
        self.storage.get_entries_for(self.source_node).

        Peers save this message, as we remember when they send rpc_republish
        messages to us. We forward previous rpc_republish messages for peers
        we still have as a contact.
        """
        addr = self.get_address(node)
        data = {'rpc_republish': data}
        return transmit(self.router, addr, data)

    def rpc_transfer_storage_table(self, node):
        """
        Given a new node, send it all the keys/values it should be storing.
        node here is a new node that's just joined or that we've just found
        out about.

        For each key in storage, get k closest nodes. If newnode is closer
        than the furthest in that list, and the node for this server
        is closer than the closest in that list, then store the key/value
        on the new node (per section 2.5 of the paper)
        """
        ds = []
        for key, value in self.storage.iteritems():
            keynode = Node(sha1(key).digest())
            neighbours = self.router.find_neighbours(keynode)
            if len(neighbours) > 0:
                new_node_close = node.distance_to(keynode) < neighbours[-1].distance_to(keynode)
                this_node_closest = self.source_node.distance_to(keynode) < neighbours[0].distance_to(keynode)
            if len(neighbours) == 0 or (new_node_close and this_node_closest):
                ds.append(self.call_store(node, key, value))
        return ds

    # handle_* methods (generally) indicate a request initiated by a peer node.

    def handle_ping(self, data):
        node = self.read_envelope(data)
        log("Received rpc_ping from %s." % node)
        return envelope(self.router, {'ping':"pong"})

    def handle_friend(self, data):
        """
        {"rpc_friend":
            [
                {"add": {"from": "uid", "to": "addr"}},
                {"remove": {"from": "uid", "to": "addr"}},
                {"status": {"from": "uid", "to": "addr", "type": "AO"}},
            ]
         "network": "alpha"
         "peers":   [...]
        }
        
        Match to UID and return a new Friend instance representing our side.
        """
        node = self.read_envelope(data)
       
        if len(data['rpc_friend']) > 10:
            log("Received too many batched RPC_FRIEND messages.", "warning")
            return

        for message in data['rpc_friend']:
            
            message_type = message.keys()[0]
            payload      = message.values()[0]
            
            if isinstance(payload, (list, dict)) and len(payload) > 5:
                log("Abnormal RPC_FRIEND payload: %s" % str(payload), "warning")
                continue

            if not "from" in payload or not "to" in payload:
                continue
           
            network, node_id, local_uid = payload['to'].split('/', 2)
            user      = User.query.filter(User.uid == local_uid).first()

            if network != self.router.network:
                log("Mismatched network: Message for %s on %s." % \
                   (network, self.router.network), "error")
                return False

            elif long(node_id) != self.router.node.long_id:
                log("Message for %s delivered to %s." % \
                    (node_id, str(self.router.node.long_id)), "error")
                return False

            elif not user:
                log("No user %s." % local_uid, "error")
                return False
            
            # Currently only one FRIEND RPC is recognised.
            # TODO(ljb): Remove friend, update status.
            if message_type == "add":
                
                from_addr = "/".join([self.router.network, str(node.long_id), payload['from']])
                friend    =  Friend.query.filter(
                                    and_(Friend.address == from_addr, Friend.user == user)
                                ).first()
                if friend:
                    # This permits the remote side to see if they're added or blocked.
                    return envelope(self.router, {"response": friend.jsonify()})
                
                node = Node(*data['node'])

                network = Network.query.filter(Network.name == self.router.network).first()
                
                if network == None:
                    network = Network(name = self.router.network)

                peer = Peer.query.filter(
                            and_(Peer.network == network,
                                 Peer.ip      == node.ip,
                                 Peer.port    == node.port)
                        ).first()

                if peer == None:
                    peer = Peer()
                    peer.ip      = node.ip
                    peer.port    = node.port
                    peer.pubkey  = node.pubkey
                    peer.network = network

                friend          = Friend(address=from_addr)
                friend.state    = 1
                friend.received = True
                friend.ip       = node.ip
                friend.port     = node.port
                
                user.friends.append(friend)
                peer.friends.append(friend)

                db.session.add(user)
                db.session.add(peer)
                db.session.add(friend)
                db.session.add(network)
                db.session.commit()
                
                return envelope(self.router, {"response": friend.jsonify()})
            
            if message_type == "status":
                if not "type" in payload:
                    return None

                if payload["type"].lower() == "get":
                    friend = [f for f in user.friends if f.uid == payload['from']]
                    if not any(friend):
                        return None

                    response = {"response": user.jsonify(address=self.router)}
                    return envelope(self.router, response)

    def handle_chat(self, data):
        """
        Move a message from a remote node up to the UI if the recipient
        UID has an active connection to the chat stream.
        """
        # TODO(ljb): Ensure this conforms to the channel system and rethink
        #            this in terms of group chats where users are subscribed
        #            to a shared name with a minimum of 3 delivery retries.

        node            = self.read_envelope(data)
        # With the ciphertext being a binary string we also b64encode it
        message_content = base64.b64decode(data['rpc_chat'])
        message_content = app.key.decrypt((message_content,))
        data            = json.loads(base64.b64decode(message_content))
        log(message_content, "debug")
        log(data, "debug")

        user = User.query.filter(User.uid == data['to']).first()
        if user == None:
            return {"error": "No such user."}

        friend = Friend.query.filter(and_(Friend.user    == user,
                                          Friend.network == self.router.network,
                                          Friend.node_id == str(node.long_id),
                                          Friend.uid     == data['from'][0])
                                    ).first()
        if friend:

            available = check_availability(self.router.httpd, "chat", user)
            if not available:
                return {"error": "The intended recipient isn't connected to chat."}

            if data['type'] == "init":
                # Enable the recipient to reply by forcing them into the channel
                log("Changing chat channel of %s to %s." % \
                    (user.username, friend.address), "debug")

                # change_channel and broadcast are from streams.utils.
                change_channel(self.router.httpd,
                               "chat",
                               user,
                               friend.address)
                broadcast(self.router.httpd,
                          "chat",
                          "rpc_chat_init",
                          data['from'],
                          user=user)
            
            if data['type'] == "message":
                broadcast(self.router.httpd,
                          "chat",
                          "rpc_chat",
                          data,
                          user=user)

        return {"state": "delivered"}

    def handle_edit(self, data):
        """
        Messages have two types: invite and edit.

        This method is used to send session initiation requests up
        to the user if they're connected to the stream defined in
        streams.events, or, given an existing session, to send
        synchronisation data given an existing session.
        """
        log(data, "debug")
        return
        if not "type" in data: return
        if data['type'] == "invite":
            pass
            return
        if data['type'] == "edit":
            self.read_envelope(data)
            data = app.key.decrypt(data['rpc_edit'])
            pass

    def handle_leaving(self, data):
        conscientous_objector = self.read_envelope(data)
        self.router.remove_node(conscientous_objector)

    def handle_find_node(self, data):
        """
        Used for finding existing nodes near to a target ID.
        """
        source = self.read_envelope(data)
        if not 'key' in data:
            return "No target key specified.", 400
        node = Node(data['key'])
        log("Finding neighbours of %s." % node.long_id)
        nodes = {'nodes': [p.jsonify() for p in \
                self.router.find_neighbours(node, exclude=source)]}
        return envelope(self.router, nodes)

    def handle_find_value(self, data):
        source = self.read_envelope(data)
        if not source: return
        if not 'rpc_find_value' in data: return
        # usually comes in as unicode
        if not isinstance(data['rpc_find_value'], (unicode, str)):
            return
        key = data['rpc_find_value']
        log("Finding value for %s" % key)
        value = self.storage.get(key, None)
        if key is None:
            log("No value found for %s" % key)
            return self.rpc_find_node(sender, nodeid, key)
        log("Found %s" % value)
        return envelope(self.router,{'value':value})

    def handle_append(self, data):
        """
        Handle messages of the form {'rpc_append': {'url_hash': 'content_hash'}}
        We do this by inserting the data into a structure that looks like
        { 'url_hash': {'content_hash': [(timestamp, nodeple)]}}
        """
        node = self.read_envelope(data)
        if max(node.trust, 0) == 0:
            log("%s with negative trust rating tried to append." % node, "warning")
            return False
        url_hash, content_hash = data['rpc_append'].items()[0]
        log("Received rpc_append request from %s." % node)
        log("Adjusting known peers for %s." % url_hash)
        self.storage[url_hash] = (content_hash, node)
#        if self.router.options and self.router.options.autoreplicate:
#            if not Revision.query.filter(Revision.hash == content_hash).first():
#                revision = self.fetch_revision(content_hash, [source])
#                if revision:
#                    db.session.add(revision)
#                    db.session.commit()
        return True

    def handle_republish(self, data):
        """
        Retain signed messages here so they can be relayed.
        """
        node = self.read_envelope(data)
        
        if max(node.trust, 0) == 0:
            log("%s with negative trust rating tried to republish." % node, "warning")
            return False

        log("Received rpc_republish from %s." % node)
        republished_keys = data['rpc_republish']
        for message in republished_keys:
            
            if max(node.trust, 0) == 0:
                return False

            signature = (long(message['keys'].keys()[0]),)
            data      = message['keys'].values()[0]
            hash      = SHA256.new(data).digest()
            key       = RSA.importKey(message['node'][1])
            if not key.verify(hash, signature):
                log("Invalid signatures for keys provided by %s." % node, "warning")
                node.trust -= self.epsilon
                continue

            try:
                keys = json.loads(base64.b64decode(data))
            except Exception, e:
                log("Error unserialising republished keys: %s" % e.message, "error")
                continue

            referee = Node(*message['node'][0], pubkey=message['node'][1])
            if self.router.is_new_node(referee):
                self.rpc_ping(referee)
            
            # Get the trust rating of this referee
            referee = self.router.get_existing_node(referee)
            if not referee or referee.trust < 0:
                log("%s is currently republishing for %s." % (node, referee), "warning")
                continue

            self.storage.merge(keys)
            self.received_keys[referee.id] = message

        return True

    def fetch_revision(self, url, content_hash, nodeples):
        """
        Return a revision object for a content hash given a list of peers.

        Called from ValueSpider._handle_found_values.
        nodeples is a list of node triples [long_id, ip, port].
        """
        urls  = []
        nodes = []
        for n in nodeples:
            if n[1] == self.source_node.ip and n[2] == self.source_node.port:
#                continue # Attempt to retrieve from DHT even if we have a copy
                log("Serving locally held copy of this revision.")
                revision = Revision.query.filter(Revision.hash == content_hash)\
                    .first()
                if revision:
                    return revision
            node = self.router.get_existing_node(n)
            if node:
                nodes.append(node)
                continue
            node = self.rpc_ping(n)
            if node == None:
                continue
            nodes.append(node)

        nodes = sort_nodes_by_trust(nodes)

        for node in nodes:
            urls.append("http://%s:%i/v1/peers/revisions/%s" % \
                (node.ip, node.port, content_hash))
#        urls = ["http://%s:%i/v1/peers/revisions/%s" % \
#            (n[1],n[2],content_hash) for n in nodes]
        # TODO: Handle unresponsive peers
        headers = {'User-Agent': 'Synchrony %s' % app.version}
        threads = [gevent.spawn(requests.get, url, headers=headers) for url in urls]
        gevent.joinall(threads)
        threads = [t.value for t in threads]
        for response in threads:
            # Every type of scenario here is useful
            # If a peer was unresponsive then it tells us we have a peer to remove,
            # if a peer serves content that doesn't match the hash we went for then
            # there's a trust rating to adjust
            # and if we hit upon the content we're after the sooner the better.
            if response and response.status_code != 200:
                continue
            revision = Revision()
            revision.add(response)
            if revision.hash != content_hash:
                node.trust -= self.epsilon
                log("Hash doesn't match content for %s" % content_hash, "warning")
                log("Decremented trust rating for %s." % node, "warning")
            else:
                # Adjust mimetype, set the network and increment bytes_rcvd
                log("Incrementing trust rating for %s." % node)
                node.trust += self.epsilon
                if 'content-type' in response.headers:
                    revision.mimetype = response.headers['content-type']
                if 'Content-Type' in response.headers:
                    revision.mimetype = response.headers['Content-Type']
                # Set the network instance on this revision object
                # the user instance is defined when Revision.save is called in
                # controllers.fetch
                network = Network.query.filter(
                            Network.name == self.router.network
                          ).first()
                if not network:
                    network = Network(name=self.router.network)
                revision.network = network
                app.bytes_received += revision.size

                # Remember this download in case we have feedback on it
                # Ideal data structure: {url: {hash: nodeple}}
                host = urlparse.urlparse(response.url)
                if ':' in host.netloc:
                    addr    = host.netloc.split(':')
                    addr[1] = int(addr[1])
                    self.downloads[url] = {revision.hash: tuple(addr)}
                else:
                    if not host.port:
                        port = 80
                    else:
                        port = host.port
                    self.downloads[url] = {revision.hash: (host.netloc, port)}
                return revision

    def republish_keys(self):
        """
        This means retransmitting url and content hashes we're serving for and
        signing the message.
        
        Signing permits peers to relay the message and permits us to republish
        for our peers.
        """
        data       = self.storage.get_entries_for(self.source_node)
        messages   = []
        threads    = []

        # Organise our keys for republishing
        if data:
            data = base64.b64encode(json.dumps(data))
            hash = SHA256.new(data).digest()
            signature = app.key.sign(hash, '')[0] 
            messages.append(
                    {'node': [self.source_node.threeple, self.source_node.pubkey],
                    'keys': {signature: data}}
            )
        # Grab keys we've seen our peers republish
        for key in self.received_keys:
            messages.append(self.received_keys[key][-1])

        # Tell everyone
        if messages:
            log("Republishing keys.")
            for node in self.router:
                threads.append(gevent.spawn(self.rpc_republish, node, messages))
            gevent.joinall(threads)

    def read_envelope(self, data):
        """
        Take an incoming message and either update the last_seen time for the
        sender or add the sender as a new contact.

        peers.py should also call this method once it's determined the network
        a message is for. That way we can inspect the 'peers' attribute and
        use read_envelope to also learn of new peers.
        """
        # Validate the senders' node ID
        seed = "%s:%i:%s" % (data['node'][1],data['node'][2],data['pubkey'])
        if data['node'][0] != long(utils.generate_node_id(seed).encode('hex'), 16):
            log("\"%s\" is using an incorrect node ID." % data['node'][1], "warning")
            return

        # Learn of peers
        #  TODO: Spawn coroutines to ping these nodes.
        if 'peers' in data:
            for peer in data['peers']:
                node = Node(*peer['node'], pubkey=peer['pubkey'], router=self.router)
                if node != self.source_node and self.router.is_new_node(node):
                    self.router.add_contact(node)

        # Update last_seen times for contacts or add if new
        node          = Node(*data['node'], pubkey=data['pubkey'], router=self.router)
        existing_node = self.router.get_existing_node(node)
        if existing_node:
            existing_node.last_seen = time.time()
            return existing_node
        elif node != self.source_node:
            self.router.add_contact(node)
            return node

    def decrement_trust(self, addr):
        """
        Implements the feedback mechanism for our trust metric.
        
        "addr" is an (ip, port) tuple to match to a known peer.

        Loosely based on EigenTrust++.

        A dedicated testing framework can be cloned from here:
        https://github.com/Psybernetics/Trust-Toolkit

        http://nlp.stanford.edu/pubs/eigentrust.pdf
        http://www.cc.gatech.edu/~lingliu/papers/2012/XinxinFan-EigenTrust++.pdf
        http://dimacs.rutgers.edu/Workshops/InformationSecurity/slides/gamesandreputation.pdf
        """
        for node in self.router:
            if node.ip == addr[0] and node.port == addr[1]:
                if "NO_PRISONERS" in app.config and app.config["NO_PRISONERS"]:
                    log("Setting trust rating for %s to 0." % node, "warning")
                    node.trust = 0
                else:
                    log("Decrementing trust rating for %s by %f." % (node, self.epsilon), "warning")
                    node.trust -= 2 * self.epsilon
#               peer = Peer.query.filter(
#                       and_(Peer.network == self.network,
#                            Peer.ip      == addr[0],
#                            Peer.port    == addr[1])
#                   ).first()
#               if peer:
#                   peer.trust -= amount
#                   db.session.add(peer)
#                   db.session.commit()
                return True

        return False

    def get_address(self, node):
        if node.ip == self.source_node.ip:
            address = ('127.0.0.1', node.port)
        else:
            address = (node.ip, node.port)
        return address
 
class KBucket(object):
    def __init__(self, lower, upper, ksize):
        self.range = (lower, upper)
        self.ksize = ksize
        self.nodes = OrderedDict()
        self.replacement_nodes = utils.OrderedSet()
        self.touch_last_updated()

    def touch_last_updated(self):
        self.last_updated = time.time()

    def get_nodes(self):
        return self.nodes.values()

    def is_new_node(self, node):
        return node.id not in self.nodes

    def split(self):
        midpoint = self.range[1] - ((self.range[1] - self.range[0]) / 2)
        one = KBucket(self.range[0], midpoint, self.ksize)
        two = KBucket(midpoint + 1, self.range[1], self.ksize)
        for node in self.nodes.values():
            bucket = one if node.long_id <= midpoint else two
            bucket.nodes[node.id] = node
        return (one, two)

    def has_in_range(self, node):
        return self.range[0] <= node.long_id <= self.range[1]

    def add_node(self, node):
        """
        If the bucket is full, keep track of the node in
        a replacement list, per section 4.1 of the paper.
        """
        if node.id in self.nodes:
            del self.nodes[node.id]
            self.nodes[node.id] = node
        elif len(self) < self.ksize:
            self.nodes[node.id] = node
        else:
            self.replacement_nodes.push(node)
            return False
        return True

    def get_node(self, node):
        for existing_node in self.nodes.values():
            if existing_node.id == node.id:
                return existing_node

    def remove_node(self, node):
        if node.id not in self.nodes:
            return

        # NOTE: We don't remove peers if they've earned themselves a negative
        #       trust rating. That would enable peers to leave and rejoin to
        #       reset their rating.
        if self.nodes[node.id].trust < 0:
            return

        # delete the node, and see if we can add a replacement
        del self.nodes[node.id]
        if len(self.replacement_nodes) > 0:
            newnode = self.replacement_nodes.pop()
            self.nodes[newnode.id] = newnode

    def depth(self):
        sp = shared_prefix([n.id for n in self.nodes.values()])
        return len(sp)

    def head(self):
        return self.nodes.values()[0]

    def __getitem__(self, id):
        return self.nodes.get(id, None)

    def __len__(self):
        return len(self.nodes)

class TBucket(dict):
    """
    A two-tiered bucket of pre-trusted peers.

    The extended set cannot contain members of the real set and the real set
    mustn't contain members of the extended set. The members of the set of
    pre-trusted peers, referred to as P, are queried about every peer we know
    of except for themselves providing the cardinality of P is greater than a
    pre set percentage of the size of the network, with a frequency that's also
    tied to the size of the network as we see it. The larger the network the
    less often you should perform calculate_trust().
    
    The responses about peers are first checked for trust rating inflation,
    deflation and whether they're just impossible in relation to their reported
    transaction count.

    For each peer we then calculate the median altruism rating of all obtained
    responses, which is the number of transactions divided by the trust rating
    once normalised to its defaults (IE. trust - 0.5 / transactions * epsilon).

    For peers who have a median altruism rating below 1.00 minus our cutoff
    point, say 5%, we say that a consensus has been acheived via set P that
    the peer in question is malicious. This enables use to identify nodes
    we should distrust without having to transact with them at all.

    Members of the extended set, referred to as EP, are being monitored for
    retaining an altruism score of 1.00 (100% ratio of trust to transactions)
    and can be graduated into set P once they have rendered reliable service
    to at least either half of our set of pre-trusted peers or if none are
    available, directly to ourselves.

    See https://github.com/Psybernetics/Trust-Toolkit if you would like to
    craft your own threat models against this class.
    """
    def __init__(self, router, *args, **kwargs):
        # Peers trusted by pre-trusted peers. These are peers we're observing
        # for possible inclusion into the set of pre-trusted peers.
        self.extent  = {}
        
        # We require alpha satisfactory transactions and altruism(peer) = 1
        # before we graduate a remote peer from the extended set into this set.
        self.alpha   = 500
        
        # The minimum satisfactory transactions required with at least half of
        # the members of this set, or if there are no members of this set, with
        # ourselves before graduating remote peers into the extended set.
        self.beta    = 250
        
        # Percentage of purportedly malicious downloads before a far peer can be
        # pre-emptively dismissed for service. 0.5% by default. This means that
        # we'll tolerate one unsatisfactory download out of every 200 per
        # threat model F.
        self.delta   = 0.005
        
        # Percentage of network peers we need to trust before we start
        # letting them cut us off from peers they report to be malicious.
        self.gamma = 0.04
        
        # Access to the routing table.
        self.router  = router
        
        # Whether we're logging stats.
        self.verbose = None
        
        dict.__init__(self, *args, **kwargs)

    @property
    def all(self):
        copy = self.copy()
        copy.update(self.extent)
        return iter(copy.values())

    def append(self, nodes):
        if not isinstance(nodes, list):
            nodes = [nodes]

        for node in nodes:
            if not hasattr(node, "long_id"):
                continue
            self[node.long_id] = node

    def get(self, node, about_node):
        """
        Ask a remote peer about a peer.
        """
        if not node:
            return
        
        url = '/'.join([self.router.network, str(about_node.long_id)])
        response = get(node, url)
        
        if not response: return {}
        return response

    def mean(self, ls):
        if not isinstance(ls, (list, tuple)):
            return
        if numpy:
            [ls.remove(_) for _ in ls if _ == None or _ is numpy.nan]
        else:
            [ls.remove(_) for _ in ls if _ == None]
        if not ls: return 0.00
        mean = sum(ls) / float(len(ls))
        if self.verbose:
            log("mean:   %s %f" % (ls, mean))
        return mean

    def med(self, ls):
        if not numpy:
            med = utils.median(ls)
        else:
            med =  numpy.median(numpy.array(ls))
        if self.verbose:
            log("med:    %s %f" % (ls, med))
        return med

    def median(self, l):
        if numpy:
            [l.remove(_) for _ in l if _ > 1 or _ < 0 \
             or not isinstance(_, (int, float)) or _ is numpy.nan]
        else:
            [l.remove(_) for _ in l if _ > 1 or _ < 0 \
             or not isinstance(_, (int, float))]
        if not len(l): return 0.00
        a = self.mean(l)
        m = self.med(l)
        me = self.mean([a, m])
        if self.verbose:
            log("me:     [%f, %f] %f" % (a, m, me))
        median = min(max(me, 0), 1)
        if self.verbose:
            log("median: %s %f" % (l, median))
        return median

    def altruism(self, i):
        # print i, 
        if isinstance(i, Node):
            i = {"trust": i.trust, "transactions": i.transactions}
        divisor = (i['transactions'] * self.router.protocol.epsilon)
        # print i, divisor
        a = i['trust'] - self.router.node.trust
        if not divisor and not a: return 1.00
        if not divisor: return 0.00
        # print a
        return a / divisor

    def calculate_trust(self):
        # Any superficially simple behaviors here can be enhanced with
        # decision trees.
        all_responses = {} 

        for peer in self.router:
            responses             = []
            ep_responses          = []
            altruism              = []
            local_altruism        = 0.00

            # Multiplier is the amount of transactions more than ourselves we're
            # checking a trusted peer is reporting they've satisfactorily had
            # with an untrustworthy peer. For small networks we would find it
            # interesting if a peer we depend on for consensus claims to have
            # had more than twice as many satisfactory transactions than
            # ourselves with a peer who we've only have had (100% - delta)
            # satisfactory transactions with.
            multiplier = 2.1 if len(self.router) < 40 else 1.1
            
            # Ask memebers of EP about the peer in question.
            for extent_peer in self.extent.values():
                if extent_peer == peer: continue
                response = self.get(extent_peer, peer)
                if responses:
                    ep_responses.append(respond)

            # Ask members of set P about the peer.
            for trusted_peer in self.values():
                if trusted_peer == peer: continue
                response = self.get(trusted_peer, peer)
                if response and response['transactions']:
                    responses.append((trusted_peer, response))

                    if not trusted_peer in all_responses:
                        all_responses[trusted_peer] = [(peer, response)]
                    else:
                        all_responses[trusted_peer].append((peer, response))

            for response in ep_responses:
                if response and response['transactions']:
                
                    # Check for peers in EP reporting trust ratings greater or lower
                    # than what they could be in relation to reported transaction counts.
                    if (response['trust'] > 0.5 + (response['transactions'] * self.router.protocol.epsilon)) \
                    or (response['trust'] < 0.5 - (response['transactions'] * self.router.protocol.epsilon)) \
                    and response['trust'] and extent_peer.long_id in self.extent:
                        extent_peer.trust = 0
                        [setattr(_, "trust", 0) for _ in self.router if _ == extent_peer]
                        log("Removing %s from EP for impossible trust ratings." % extent_peer)
                        del self.extent[extent_peer.long_id]
                        continue

                    # Check for members of set EP reporting 100% unsatisfactory
                    # transactions with the peer in question but not reporting the
                    # peer as having trust == 0 when reporting altruism < 0.8.
                    if self.altruism(response) <= 0.8 and response['trust'] > 0:
                        if self.verbose:
                            log((extent_peer, peer, response))
                        if extent_peer.long_id in self:
                            log("Removing %s from EP for deflating trust ratings." % \
                                extent_peer)
                            del self.extent[extent_peer.long_id]
                            continue

                    # Check for peers in EP reporting high transaction count and
                    # high trust with peers we don't trust, indicating inflated scores.
                    if not peer.trust and peer.transactions > 5 * multiplier \
                        and response['transactions'] >= peer.transactions * multiplier \
                        and float("%.1f" % self.altruism(response)) >= 1.0:
                        # Check for at least two  members of set P to cross-reference with
                        if len(responses) < 3: break
                        c = 0
                        for _, resp in responses:
                            if len.altruism(resp) > 0.95: c += 1
                        # Vet the next response from the next member of EP if
                        # less than 90% of P find the current peer untrustworthy.
                        if c < 0.9 * (len(responses) - 1):
                            continue
                        if self.verbose:
                            log((peer, extent_peer, response))
                        if extent_peer.long_id in self.extent:
                            extent_peer.trust = 0
                            [setattr(_, "trust", 0) for _ in self.router if _ == extent_peer]
                            log("Removing %s from EP for inflating trust ratings." % extent_peer)
                            del self.extent[extent_peer.long_id]


            # Ask members of set P about everyone in our routing table.
            for trusted_peer in self.values():
                if trusted_peer == peer: continue
                response = self.get(trusted_peer, peer)
                if response and response['transactions']:
                    responses.append((trusted_peer, response))
                    
                    if not trusted_peer in all_responses:
                        all_responses[trusted_peer] = [(peer, response)]
                    else:
                        all_responses[trusted_peer].append((peer, response))

            # Check for peers in P reporting trust ratings greater or lower
            # than what they could be in relation to reported transaction counts.
            for trusted_peer, response in responses:
                if (response['trust'] > 0.5 + (response['transactions'] * self.router.protocol.epsilon)) \
                or (response['trust'] < 0.5 - (response['transactions'] * self.router.protocol.epsilon)) \
                and response['trust'] and trusted_peer.long_id in self:
                    trusted_peer.trust = 0
                    [setattr(_, "trust", 0) for _ in self.router if _ == trusted_peer]
                    log("Removing %s from P for impossible trust ratings." % trusted_peer)
                    del self[trusted_peer.long_id]
                    del all_responses[trusted_peer]
                    responses.remove((trusted_peer, response))
                    continue

                # Check for members of set P reporting 100% unsatisfactory
                # transactions with the peer in question but not reporting the
                # peer as having trust == 0 when reporting altruism < 0.5.
                if response['trust'] > 0 and self.altruism(response) <= 0.5 \
                    and response['transactions'] >= 5 * multiplier:
                    if self.verbose:
                        log((trusted_peer, peer, response))
                        log(self.altruism(response))
                    if trusted_peer.long_id in self:
                        log("Removing %s from P for deflating trust ratings." % \
                            trusted_peer)
                        del self[trusted_peer.long_id]

                # Check for peers in P reporting high transaction count and
                # altruism > 1 - delta with peers we don't trust, which indicates
                # trusted peers giving inflated trust ratings.
                if not peer.trust and peer.transactions > 5 * multiplier \
                    and response['transactions'] >= peer.transactions * multiplier \
                    and float("%.1f" % self.altruism(response)) >= 1.0:
                    # Check for at least two members of set P to cross-reference
                    # with, ensuring at least a minimum of two pre-trusted peers.
                    if len(responses) < 3: break
                    c = 0
                    for _, resp in responses:
                        if self.altruism(resp) > 0.95: c += 1
                    # Vet the next response from the next member of EP if
                    # less than 90% of P find the current peer untrustworthy.
                    if c < 0.9 * (len(responses) - 1):
                        continue
                    if self.verbose:
                        log((peer, trusted_peer, response))
                    if trusted_peer.long_id in self:
                        trusted_peer.trust = 0
                        [setattr(_, "trust", 0) for _ in self.router if _ == trusted_peer]
                        log("Removing %s from P for inflating trust ratings." % \
                            trusted_peer)
                        del self[trusted_peer.long_id]
                        del all_responses[trusted_peer]
                        responses.remove((trusted_peer, response))
                        continue
            
            if not peer.trust: continue

            local_altruism = float("%.1f" % self.altruism(peer))
            
            if (local_altruism + self.delta) <= 1.0:
                log("Local experience shows %s is malicious." % peer)
                peer.trust = 0
                continue

            median_reported_altruism = 0.00
            # Let our pre-trusted peers have some say about this if they
            # A) Represent at least gamma percent of who we know in the network.
            # B) Report having more experience than us with the peer in question.
            if float(len(self)) / len(self.router) >= self.gamma:
                
                # Filter responses to those from peers who report having more
                # experience than us with the peer in question if we're ascribing
                # a 100% altruism rating to this peer.
                filtered_responses = filter(lambda r:
                                        r[1]['transactions'] >= peer.transactions and \
                                        (float(r[1]['transactions'] - peer.transactions) / r[1]['transactions']) \
                                        >= 0.01,
                                        responses
                                  )

                # If we have good faith in the peer regardless of having had no
                # transactions with them we'll require the votes to come from
                # pre-trusted peers who've rendered excellent service to
                # mitigate the effect of maximally deflationary pre-trusted peers.
                if local_altruism >= 0.99:
                    filtered_responses = filter(lambda r: r[0].transactions > self.alpha,
                                                filtered_responses)


                for response in filtered_responses:
                    altruism.append(self.altruism(response[1]))

                # continue if we've had good service from the peer in question
                # and only received one vote, or if we've had perfect service
                # from the peer so far. Listen to trusted peers if we have no
                # prior transactions with the peer in question as this is really
                # what the system's about: Pre-emptively identifying
                # untrustworthy peers without having to transact with them.
                if not len(altruism) or (local_altruism == 1.0 and len(altruism) == 1) or \
                        (peer.transactions and local_altruism == 1.0):
                    continue
                
                if numpy:
                    [altruism.remove(_) for _ in altruism if _ == None or _ is numpy.nan]
                else:
                    [altruism.remove(_) for _ in altruism if _ == None]
                
                if self.verbose:
                    log(filtered_responses)
                    log("%s local_altruism %f" % (peer, local_altruism))

                log("%s %s" % (peer, altruism))
                
                median_reported_altruism = self.median(altruism)
                log("Median reported altruism: %f" % median_reported_altruism)
                # Check if global altruism is below our accepted threshold (delta) and
                # if it's reportedly less than our experience minus the accepted threshold
                # gamma, which is made to be a function of routing table size. 
                if (median_reported_altruism + self.delta) < 1.0:
                    log("Consensus from our trusted peers is that %s is malicious." % peer)
                    peer.trust = 0
                    continue
            
            # Don't adjust a peers' trust rating to more closely reflect the consensus
            # as this gives an innacurate reflection of their trust / transaction ratio
            # from our perspective.

            # Check who we can invite into the extended set.
            if (len(self) and float("%.1f" % median_reported_altruism) != 1.0) \
            or peer in self.all:
                continue
            
            # If we haven't continued from this peer we'll see if they can be
            # graduated into the extended set of pre-trusted peers using the
            # responses obtained earlier.
            #
            # We do this based on the peer having median_reported_altruism == 1
            # and either at least half of our trusted peers having at least
            # the minimum required transaction count (beta) with this peer or
            # if we're in need of some pre-trusted peers, this instance having
            # the necessary transaction count.
            votes = sum([1 for r in responses if r[1]['transactions'] >= self.beta])
            if len(self) and not votes: continue
            
            if (not len(self) and peer.transactions >= self.beta) \
            or (len(self) and votes >= (len(self) / 2)):
                if len(self):
                    log("votes: %s %i" % (peer, votes))
                log("Graduating %s into EP." % peer)
                self.extent[peer.long_id] = peer

        for peer in self.extent.copy().values():
            if float("%.1f" % self.altruism(peer)) != 1.0:
                log("Removing %s from the extended set of pre-trusted peers." % peer)
                del self.extent[peer.long_id]
                continue
            # Check if they're trustworthy enough to be a pre-trusted peer
            if peer.transactions >= self.alpha:
                log("Graduating %s from EP to P." % peer)
                del self.extent[peer.long_id]
                self[peer.long_id] = peer

        for peer in self.copy().values():
            if float("%.1f" % self.altruism(peer)) != 1.0:
                log("Removing %s from the set of pre-trusted peers." % peer)
                del self[peer.long_id]
        
        # Check the percentage of high transaction/altruism peers being
        # reported as untrustworthy by this peer.
        for trusted_peer, responses in all_responses.items():
            if not trusted_peer.long_id in self: continue
            x = 0
            for peer, response in responses:
                if not trusted_peer.long_id in self: break
                if response['transactions'] < peer.transactions \
                or peer.transactions < 20: continue
                if self.altruism(peer) > 0.95 and self.altruism(response) <= 0:
                    x += 1
                for cmp_peer, cmp_responses in all_responses.items():
                    if not cmp_peer in self.values() or cmp_peer == trusted_peer:
                        continue
                    for _peer, cmp_response in cmp_responses:
                        if _peer == peer and self.altruism(cmp_response) > 0.95:
                            x += 1
            if self.verbose:
                log("%s x: %i" % (trusted_peer, x))
            if x > len(self.router) * 0.7:
                log("Removing %s from P for deflating trust ratings." % trusted_peer)
                del self[trusted_peer.long_id]

        log("P:  %s" % str(self.values()))
        log("EP: %s" % str(self.extent.values()))

        for _ in sort_nodes_by_trust([p for p in self.router]):
            log(_)

        del all_responses

    def __repr__(self):
        return "<TBucket with EP:%i P:%i>" % (len(self.extent), len(self))

class Node(object):
    def __init__(self, id, ip=None, port=None, pubkey=None, router=None):
        if isinstance(id, long):
            id = unhexlify('%x' % id)
        self.id        = id
        self.ip        = ip
        self.port      = port
        self.trust     = 0.50
        self.pubkey    = pubkey
        self.router    = router
        self.last_seen = time.time()
        self.long_id   = long(id.encode('hex'), 16) 
        self.name      = str(self.long_id)

    def same_home(self, node):
        return self.ip == node.ip and self.port == node.port

    def distance_to(self, node):
        return self.long_id ^ node.long_id

    @property
    def transactions(self):
        if self.router == None:
            return 0
        return len(
                    self.router.protocol
                    .downloads.get_entries_for((self.ip, self.port))
                  )

    @property
    def printable_id(self):
        return bin(self.long_id)[2:]

    @property
    def threeple(self):
        return (self.long_id, self.ip, self.port)

    def __iter__(self):
        return iter([self.id, self.ip, self.port])

    def __repr__(self):
        return "<Node %s:%s %.4fT/%i>" % \
            (self.ip, str(self.port), self.trust, self.transactions)

    def __eq__(self, other):
        if other is None: return False
        return self.ip == other.ip and self.port == other.port 

    def jsonify(self, string_id=False):
        res = {}
        res['node']         = self.threeple
        res['trust']        = self.trust
        res['pubkey']       = self.pubkey
        res['last_seen']    = self.last_seen
        res['transactions'] = self.transactions
        if string_id:
            res['node']    = list(res['node'])
            res['node'][0] = str(res['node'][0])
            res['node']    = tuple(res['node'])
        return res

class NodeHeap(object):
    def __init__(self, node, maxsize):
        self.node = node
        self.heap = []
        self.contacted = set()
        self.maxsize = maxsize

    def purify(self):
        """
        Clear the heap of nodes with negative trust ratings.
        """
        [self.heap.remove(node) for node in self.heap if node[1].trust < 0]

    def remove(self, peer_ids):
        per_ids = set(peer_ids)
        if len(peer_ids) == 0:
            return
        nheap = []
        for distance, node in self.heap:
            if node.id not in peer_ids:
                heapq.heappush(nheap, (distance, node))
        self.heap = nheap

    def get_node_by_id(self, id):
        for _, node in self.heap:
            if node.id == id:
                return node
        return Node

    def all_been_contacted(self):
#        return [n.id for n in self]
        return any([n for n in self])

    def get_ids(self):
        return [n.id for n in self]

    def mark_contacted(self, node):
        self.contacted.add(node.id)

    def popleft(self):
        if len(self) > 0:
            return heapq.heappop(self.heap)[1]
        return None

    def push(self, nodes):
        """
        nodes can be singular or a list.
        """
        if not isinstance(nodes, list):
            nodes = [nodes]

        for node in nodes:
            # Ensure node uniqueness before appending:
            if [node.ip, node.port] in [[n[1].ip, n[1].port] for n in self.heap]:
                continue
            distance = self.node.distance_to(node)
            heapq.heappush(self.heap, (distance, node))

    def __len__(self):
        return min(len(self.heap), self.maxsize)

    def __iter__(self):
        nodes = heapq.nsmallest(self.maxsize, self.heap)
        return iter(map(operator.itemgetter(1), nodes))

    def get_uncontacted(self):
        return [n for n in self if n.id not in self.contacted]

    def __repr__(self):
        return "<NodeHeap %s" % str(self.heap)

class Storage(object):
    """
    {
        'src.psybernetics.org/': {
            'content_hash': [(ts,nodeple), (ts,nodeple)],
            'content_hash': [(ts,nodeple), (ts,nodeple)],
        }
    }

    Must have a ceiling on the amount of urls and content hashes.
    Must not allow nodes to appear multiple times in the same list.
    """
    def __init__(self, ttl=604800):
        self.ttl       = ttl
        self.data      = {}
        self.lock      = RLock()
        self.sites     = 1000000000
        self.revisions = 10000

    def cull(self):
        self.lock.acquire()
        t = time.time() - self.ttl
        for url in self.data.copy():
            for content in self.data[url]:
                for ref in self.data[url][content]:
                    if ref[0] <= t:
                        log("Culling outdated entry for %s [%s]." % (str(ref[1]), url))
                        self.data[url][content].remove(ref)
        self.lock.release()

    def get(self, key, default=None):
        self.cull()
        if key in self.data:
            return self.data[key]
        return default

    def remove_node(self, node):
        """
        Remove a node from our understanding of who has what resources.
        This prevents us from referring our peers to nodes that have left.
        """
        count = 0
        self.lock.acquire()
        for u_hash in self.data.copy():
            for c_hash in self.data[u_hash].copy():
                for ref in deepcopy(self.data[u_hash][c_hash]):
                    if ref[1] == node.threeple:
                        count += 1
                        self.data[u_hash][c_hash].remove(ref)
                        if not self.data[u_hash][c_hash]:
                            del self.data[u_hash][c_hash]
                        if not self.data[u_hash]:
                            del self.data[u_hash]
        self.lock.release()
        if count:
            log("%s was responsible for %i object%s." % \
                (node, count, 's' if count > 1 else ''))

    def get_entries_for(self, node):
        """
        Return which URL hashes and content hashes a node has said they're
        storing data for, if any.
        """
        response  = {}
        for u_hash in self.data.copy():
            for c_hash in self.data[u_hash].copy():
                operating_copy = deepcopy(self.data[u_hash][c_hash])
                for ref in operating_copy:
                    if ref[1] == node.threeple:
                        response[u_hash] = {c_hash: [ref]}
        return response

    def merge(self, keys):
        """
        Take keys given in protocol.handle_republish and integrate them into
        the storage table.
        
        { url_hash: {c_hash: [ [ts, nodeple],
                               [ts, nodeple] ]
        }            }
        """
        self.cull()
        self.lock.acquire()
        new_data = 0
        assert isinstance(keys, dict)
        for url in keys:
            if not url in self.data:
                new_data += 1
                self.data[url] = keys[url]
            else:
                for c_hash, rpeers in keys[url].items():
                    if not c_hash in self.data[url]:
                        new_data += 1
                        self.data[url][c_hash] = rpeers
                    else:
                        for peer in rpeers:
                            for p in deepcopy(self.data[url][c_hash]):
                                if peer[1] == p[1]:
                                    if peer[0] > p[0]:
                                        new_data += 1
                                        self.data[url][c_hash].remove(p)
                                        self.data[url][c_hash].append(peer)
        self.lock.release()
        log("Merged %s reference%s." % (new_data,'' if new_data == 1 else 's'))

    def __setitem__(self, key, value):
        """
        Data comes in the form of storage[url_hash] = (content_hash, source)
        where source is a Node object.
        """
        self.cull()
        self.lock.acquire()
        assert isinstance(value, tuple)
        if len(self.data.keys()) >= self.sites:
            return False
        c_hash, node = value
        node = node.threeple
        t    = time.time()
        if key in self.data:
            if c_hash in self.data[key]:
                # Just update the timestamp if a node is republishing their keys
                for ref in deepcopy(self.data[key][c_hash]):
                    if ref[1][0] == node[0]:
                        self.data[key][c_hash].remove(ref)
                        self.data[key][c_hash].append((t, node))
                        self.lock.release()
                        return
                # TODO: Bounded lists.
                self.data[key][c_hash].append((t, node))
            else:
                self.data[key][c_hash] = [(t, node)]
        elif (key not in self.data) or key in self.data and len(self.data[key])\
            < self.revisions:
            self.data[key] = {c_hash: [(t, node)]}
        self.lock.release()

    def __getitem__(self, key):
        self.cull()
        if not key in self.data:
            raise KeyError(key)
        return self.data[key]

    def __iter__(self):
        self.cull()
        return iter(self.data.items())

    def __len__(self):
        self.cull()
        return len(self.data)

class ForgetfulStorage(object):
    def __init__(self, ttl=604800, bound=0): # 7 days
        """
        This storage class is used for recording the signatures of key
        republish events so that we can tell peers what data is being stored by
        other nodes in a trustworthy way.
       
        It's also used for holding "content_hash -> node" pairs for revisions
        we've downloaded from peers.

        This means that if we recieve content that the user has determined to
        be inauthentic we have a means of matching it to the peer it came from
        in order to decrement that peers' trust rating.

        "bound" specifies that values are lists and will have their tail value
        popped when their head is appended to once they reach a certain size.
        """
        self.ttl   = ttl
        self.bound = bound
        self.lock  = RLock() 
        self.data  = OrderedDict()

    def forget(self, node):
        pass

    def __setitem__(self, key, value):
        """
        f = ForgetfulStorage(bound=2)
        f['foo'] = ['bar']
        f['foo'] = 'test 1'
        f['foo'] = 'test 2'
        f['foo'] == ['test 1', 'test 2']
        True
        """
        self.lock.acquire()
        if self.bound and key in self.data and isinstance(self.data[key][1], list):
            data = self.data[key][1]
            if value in data:
                self.lock.release()
                return
            if len(data) >= self.bound:
                data.reverse()
                data.pop()
                data.reverse()
            data.append(value)
            self.data[key] = (time.time(), data)
        elif self.bound and not key in self.data:
            self.data[key] = (time.time(), [value])
        else:
            self.data[key] = (time.time(), value)
        self.lock.release()
        self.cull()

    def __getitem__(self, key):
        self.cull()
        return self.data[key][1]

    def __iter__(self):
        self.cull()
        return iter(self.data)

    def __repr__(self):
        self.cull()
        return repr(self.data)

    def get(self, key, default=None):
        self.cull()
        if key in self.data:
            return self[key]
        return default

    def get_entries_for(self, node):
        """
        Get entries for an (addr, port) pair.
        Used in Node.transactions to count total transactions.
        """
        e = []
        for i in self.data.values():
            if len(i) > 1 and isinstance(i[1], dict) and i[1].values()[0] == node:
                e.append(i)
        return e

    def cull(self):
        """
        Note that it may be useful to track what we evict.
        """
        self.lock.acquire()
        for k, v in self.iteritems_older_than(self.ttl):
            self.data.popitem(last=False)
        self.lock.release()

    def iteritems_older_than(self, seconds_old):
        min_birthday = time.time() - seconds_old
        zipped = self._triple_iterable()
        matches = takewhile(lambda r: min_birthday >= r[1], zipped)
        return imap(operator.itemgetter(0, 2), matches)

    def _triple_iterable(self):
        ikeys = self.data.iterkeys()
        ibirthday = imap(operator.itemgetter(0), self.data.itervalues())
        ivalues = imap(operator.itemgetter(1), self.data.itervalues())
        return izip(ikeys, ibirthday, ivalues)

    def iteritems(self):
        self.cull()
        ikeys = self.data.iterkeys()
        ivalues = imap(operator.itemgetter(1), self.data.itervalues())
        return izip(ikeys, ivalues)

class TableTraverser(object):
    def __init__(self, table, start_node):
        index = table.get_bucket_for(start_node)
        table.buckets[index].touch_last_updated()
        self.current_nodes = table.buckets[index].get_nodes()
        self.left_buckets  = table.buckets[:index]
        self.right_buckets = table.buckets[(index+1):]
        self.left = True

    def __iter__(self):
        return self

    def next(self):
        """
        Pop an item from the left subtree, then right, then left, etc.
        """
        if len(self.current_nodes) > 0:
            return self.current_nodes.pop()

        if self.left and len(self.left_buckets) > 0:
            self.current_nodes = self.left_buckets.pop().get_nodes()
            self.left = False
            return self.next()

        if len(self.right_buckets) > 0:
            self.current__nodes = self.right_buckets.pop().get_nodes()
            self.left = True
            return self.next()

        raise StopIteration

# TODO: Prioritise routes based on their global trust rating.
class Routers(dict):
    """
    Ease access to multiple overlay networks by network name.

    new_network         = RoutingTable(options, httpd, None, nodes)
    new_network.network = "private"
    routes              = Routers()
    routes['private']   = new_network

    routes['private']
    routes.get('private', None)
    """
    def __init__(self, routes={}, *args, **kwargs):
        if not routes:
            self._default_name = None
        else:
            self._default_name = routes.values()[0].network
        dict.__init__(self, *args, **kwargs)

    def __getattr__(self, attr):
        if not attr.startswith("_") and attr in self:
            return self[attr]
        raise AttributeError

    def append(self, router):
        assert isinstance(router, RoutingTable)
        self[router.network] = router
        if not self._default_name:
            self._default_name = router.network

    @property
    def _default(self):
        if not self or not self._default_name:
            return None
        return self[self._default_name]

    @property
    def routes_available(self):
        return self != {}

    def leave(self, key):
        router = self.get(key)
        if router == None:
            return
        router.leave_network()
        del self[key]

    def leave_networks(self):
        """
        This is set as sys.exitfunc to tell all networks that we're leaving.
        """
        # TODO: Query for Node objects in the database.
        for router in self.values():
#            for node in router:
#                p = Peer()
#                p.load_node(router.network, node)
#                db.session.add(p)
            router.leave_network()
#        db.session.commit()
        if app.bytes_sent or app.bytes_received:
            log("Replicated {:,} bytes total.".format(app.bytes_sent))
            log("Received {:,} bytes total."\
                .format(app.bytes_received))

class Spider(object):
    """
    Crawl the network and look for given 160-bit keys.
    """
    def __init__(self, protocol, node, peers, ksize, alpha):
        self.protocol = protocol
        self.ksize    = ksize
        self.alpha    = alpha
        self.node     = node
        self.nearest  = NodeHeap(self.node, self.ksize)
        self.last_crawled = [] # IDs
#        log("Creating spider with peers: %s" % peers)
        self.nearest.push(peers)

    def _find(self, rpcmethod):
        """
        Get either a value or a list of nodes.

        The process:
          1. Calls find_* to current alpha nearest not already queried nodes,
             adding results to current nearest list of k nodes.
          2. Current nearest list needs to keep track of who has been queried already.
             Sort by nearest, keep ksize.
          3. If list is same as last time, next call should be to everyone not
             yet queried.
          4. Repeat, unless nearest list has all been queried, then you're done.
        """
        self.nearest.purify()
        log("Crawling with nearest: %s" % self.nearest)
        count = self.alpha
        if self.nearest.get_ids() == self.last_crawled:
            log("last iteration same as current - checking all in list now")
            count = len(self.nearest)
        self.last_crawled = self.nearest.get_ids()

        responses = {}
        def prepare(peer):
            self.nearest.mark_contacted(peer)
            if peer.ip == self.protocol.source_node.ip:
#                and peer.port == self.protocol.source_node.port:
                # FIXME: Internal networks.
                peer.ip = '127.0.0.1'
            responses[peer.id] = gevent.spawn(rpcmethod, peer, self.node)

        [prepare(peer) for peer in self.nearest.get_uncontacted()[:count]]
        gevent.joinall(responses.values())
        for id, thread in responses.copy().items():
            responses[id] = thread.value
        return self._nodes_found(responses)

class NodeSpider(Spider):
    def find(self):
        return self._find(self.protocol.rpc_find_node)

    def _nodes_found(self, responses):
        """
        Handle an iteration of _find.
        """
        to_remove = []
        for peer_id, response, in responses.items():
            response = RPCFindResponse(self, response)
            if not response.happened:
                to_remove.append(peer_id)
            else:
                self.nearest.push(response.get_node_list())
        self.nearest.remove(to_remove)

        if self.nearest.all_been_contacted():
            return list(self.nearest)
        return self.find()

class ValueSpider(Spider):
    """
    Achieve consensus on what to fetch.
    Retrieve it from a peer.
    return a Revision.
    """
    def __init__(self, protocol, node, peers, ksize, alpha, url=None):
        Spider.__init__(self, protocol, node, peers, ksize, alpha)
        
        # Keep track of the URL, which can be a hash, to use as an argument to
        # protocol.downloads.
        self.url = url
        
        # keep track of the single nearest node without the value - per
        # section 2.3 so we can set the key there if found
        self.nearest_without_value = NodeHeap(self.node, 1)

    def find(self):
        """
        Find either the closest nodes or the value requested.
        """
        return self._find(self.protocol.rpc_find_value)

    def _nodes_found(self, responses):
        """
        Remove dead nodes.
        Ensure nodes haven't changed ID or public key.

        """
        toremove = []
        found_values = []
        for peer_id, response in responses.items():
            response = RPCFindResponse(self, response)
            if not response.happened:
                toremove.append(peer_id)
            elif response.has_value:
                found_values.append(response.get_value())
            else:
                peer = self.nearest.get_node_by_id(peer_id)
                self.nearest_without_value.push(peer)
                self.nearest.push(response.get_node_list())
        self.nearest.remove(toremove)

        if len(found_values):
            return self._handle_found_values(found_values)
        if self.nearest.all_been_contacted():
            return None
        return self.find()

    def _handle_found_values(self, values):
        """
        Turn a list of responses to FIND_VALUE into the most likely peers
        to have good content for the hash we were after.

        "values" is a list of responses like this:
        [{'content_hash': [[ts,[node_info]], [ts,[node_info]], ...]},
         {'content_hash': [[ts,[node_info]], [ts,[node_info]], ...]},
         {'content_hash': [[ts,[node_info]], [ts,[node_info]], ...]}]

        What we're doing here is calculating which content hash is the most
        replicated and then sorting the peers replicating for it across the
        responses by their most recently seen time.

        The result is: content_hash, [node_info, node_info, ...] which we
        then feed into protocol.fetch_revision.
        """
        url = self.node.id.encode('hex')
        local_values = self.protocol.storage.get(url, None)
        if local_values:
            values.append(local_values)
        if values == [None]:
            log("No references to revisions of %s." % url)
            return
        else:
            log("Sorting references to revisions of %s." % url)
        keys = []
        for v in values:
            if not v: continue
            keys.extend(v.keys())
        key_counts = Counter(keys)

        # Select the most replicated content hash
        key = key_counts.most_common(1)
        if not key:
            return
        key = key[0][0]

        # Extend the list of peers serving this revision
        revisions = []
        for v in values:
            if not v: continue
            revisions.extend(v[key])

        # Omit nodes that are known to be untrustworthy
        for node_data in deepcopy(revisions):
            nodeple = self.protocol.get_address(Node(*node_data[1]))
            for known_node in self.protocol.router:
               if self.protocol.get_address(known_node) == nodeple \
                    and max(known_node.trust,  0) == 0:
                    revisions.remove(node_data)

        # Reduce the responses to one entry per node and their most recent timestamp.
        # List is an unhashable type so we iterate over a copy.
        peers = {}
        for e in deepcopy(revisions):
            node = '%d:%s:%i' % (e[1][0],e[1][1],e[1][2])
            if not node in peers or (node in peers and peers[node] < e[0]):
                peers[node] = e[0]

       # Create a list of viable peers to fetch from from most viable to least
        nodes = [n[0] for n in sorted(peers.items(), key=operator.itemgetter(1))]
        for i, n in enumerate(deepcopy(nodes)):
            nodes[i]    = n.split(':')
            nodes[i][0] = long(nodes[i][0])
            nodes[i][2] = int(nodes[i][2])

#        log([key, nodes])

#        # Tell the nearest unaware peer we're storing this revision.
#        revision = self.protocol.fetch_revision(key, nodes)
#        if revision:
#            peer_to_save_to = self.nearest_without_value.popleft()
#            if peer_to_save_to is not None:
#            return self.protocol.router.storage_method(peer_to_save_to,
#                self.protocol.source_node.id, unhexlify(self.node.id), key)

        return self.protocol.fetch_revision(self.url, key, nodes)

class RPCFindResponse(object):
    def __init__(self, spider, response):
        """
        response is a dictionary of the form {node_id: {response}}
        """
        self.spider   = spider
        self.response = response
        if not response:
            self.valid_signature = False
        else:
            self.valid_signature = utils.validate_signature(self.response)
            log("Received %s signature from %s." % \
                ("valid" if self.valid_signature else "invalid", self.response['node'][0]))

    @property
    def happened(self):
        return self.response is not None

    @property
    def has_value(self):
        return 'value' in self.response

    def get_value(self):
        if 'value' in self.response:
            return self.response['value']
        return None

    def get_node_list(self):
        nodes = []
        if 'nodes' in self.response and self.valid_signature:
            for data in self.response['nodes']:
#                if not [data['node'][1],data['node'][2]] in [[n.ip, n.port] for n in nodes]:
                nodes.append(Node(*data['node'], pubkey=data['pubkey']))
        return nodes

def shared_prefix(args):
    i = 0
    while i < min(map(len, args)):
        if len(set(map(operator.itemgetter(i), args))) != 1:
            break
        i += 1
    return args[0][:i]

def envelope(routes, data={}):
    """
    We sign the time as attribute never recombine in the same order on the
    receive side when parsed. This method guarantees that hashes match on both
    sides.
    """
    assert isinstance(data, dict)
    data['time']    = time.time()
    data['network'] = routes.network
    data['node']    = routes.node.threeple
    data['pubkey']  = app.key.publickey().exportKey() 
    data['peers']   = [peer.jsonify() for peer in routes.find_neighbours(routes.node)]

    hash = SHA256.new(str(data['time'])).digest()
    data['signature'] = app.key.sign(hash, '')[0] 

    return data

def transmit(routes, addr, data):
    """
    Use the routing table to affix peer information to requests
    to other nodes. Test suites should replace this function
    with something that emulates it without making network calls.
    """
    assert isinstance(data, dict)
    if isinstance(addr, Node):
        addr = (addr.ip, addr.port)

    if isinstance(addr, tuple):
        addr = "http://%s:%i/v1/peers" % addr

    data = json.dumps(envelope(routes, data))

    try:
        r = requests.post(addr, data={'data':data}, timeout=app.config['HTTP_TIMEOUT'])
        if r.status_code != 200:
            log("Error contacting %s: %s" % (addr, r.text))
            return
        return r.json()
    except Exception, e:
        log(e.message, "error")
        return

def get(addr, path, field="data", all=True):
    """
    Helper function for doing things like leafing through
    /v1/peers/<network> on remote peers.
    
    """
    if isinstance(addr, Node):
        addr = (addr.ip, addr.port)

    if isinstance(addr, tuple):
        addr  = "http://%s:%i/v1/peers/" % addr
        addr += path

    def next(addr):
        result = []
        
        try:
            r = requests.get(addr, timeout=app.config['HTTP_TIMEOUT'])
            if r.status_code != 200:
                log("Error contacting %s: %s" % (addr, r.text))
                return result
        except Exception, e:
            log(e.message, "error")
            return []

        json_data = r.json()
        if field in json_data:
            result.append(json_data[field])

        if all and "self" in json_data and "next" in json_data["self"]:
           result.append(next(json_data["self"]["next"]))
        
        return result
    
    return next(addr)

def receive(data):
    """
    b64 unencode, decompress binaries
    """
    buffer = BytesIO(data)
    buffer.seek(0)
    gzip_file = gzip.GzipFile(mode="rb", fileobj=buffer)
    data = gzip_file.read()
    gzip_file.close()
    data = json.loads(data)
    return data

def suppress_unicode_repr(object, context, maxlevels, level):
    typ = pprint._type(object)
    if typ is unicode:
        object = str(object)
    return pprint._safe_repr(object, context, maxlevels, level)

def log(message, loglevel="info"):
    if not message:
        return
    
    if isinstance(message, (list, dict, tuple)):
        printer = pprint.PrettyPrinter()
        printer.format = suppress_unicode_repr
        [log(_) for _ in printer.pformat(message).split("\n")]
        return
    
    _log("DHT: %s" % str(message), loglevel)

def digest(s):
    if not isinstance(s, str):
        s = str(s)
    return sha1(s).digest()

def sort_nodes_by_trust(nodes):
    if nodes == []: 
        return []
    else:
        pivot   = nodes[0]
        lesser  = sort_nodes_by_trust([x for x in nodes[1:] if x.trust < pivot.trust])
        greater = sort_nodes_by_trust([x for x in nodes[1:] if x.trust >= pivot.trust])
        return greater + [pivot] + lesser
