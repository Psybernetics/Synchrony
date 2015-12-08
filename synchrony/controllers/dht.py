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

 The basic gist of how this file works is that between it and peers.py it
 implements an overlay network heavily based on a system called Kademlia.
 If you're coming to this without having read the original paper take a couple
 of days to really grok it, hopefully it won't take that long because you have
 this software.

 These modules make it as easy as possible to participate in multiple networks.
 Telling peers you have data and obtaining data from peers looks like this:

    app.routes._default[url] = revision
    revision = app.routes._default[url]


TODO/NOTES:
 Persist routing and storage tables to the database.
 trust rating is in Node.jsonify which means network trust is in /v1/peers
 Make revision selection strategies plug-and-play.

 protocol.copy_routing_table
 connection throttling

 Invite-only private networks based on FOAF public keys.
 Tag documents as edits or originals in rpc_append.
 Let users select whether they will accept edits. Default deny.

 Remember properties of the networks we engage in.
 A public revision is a public revision.

 CORS.
 Same-Origin policy.
 JavaScript.

 b64encoded/signed messages need a corresponding recv function.
 Possibly add self to peer tables by pinging peers received on bootstrap.
 Tell nodes if their clock is out of sync.


 Tit-for-tat: Forget peers who don't want to share well.
 Every peer will be rated for altruism.
 A peers' rating of its own peers is based on your own rating of that peer.
 A list of trusted peers

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

 Beware the initial public offering of a resource:
 < User visits site.com and performs APPEND_VALUE for site.com/path = (node_id1,hash_1)
 ! The content at site.com changes.
 < User 2 visits site.com and performs APPEND_VALUE for site.com/path = (node_id2,hash_2)
 < User 3 visits site.com and performs APPEND_VALUE for site.com/path = (node_id3,hash_2)
 ! site.com goes down.
 > Perform FIND_VALUE for site.com/path
 ! User hits the "errant content" button: Privately decrement the altrusim scores of the
   nodes involved.
 > Otherwise, after ten minutes broadcast you have hash_2 content for site.com/path
 > Privately increment the altruism scores accordingly for nodes that routed you
   and slightly more for the nodes that supplied you with content that retained integrity.

 Permit retrieval of files to start at an offset given (fsize / online_sufferers)
 > user visits example.com/picture.png and transmits the hash_1 made of the
   content
 > divides the pieces, hashes those and stores them as an association to hash-1
 > user transmits they have hash-1 based on example.com/picture.png
 > user may omit the domain from the url field, where peers with knowledge of 
   users' pubkey can pick up the broadcast, enabling user to multicast her own
   files to friends.

 Transmit and remember hash(content + pubkey + prev_hash) for a raft-like log:
 > user performs an edit on "http://google.com/"
 > broadcasts they have content for hash(content + pubkey + prev_hash) based on
   "http://google.com/"
 > nodes remember this for about a week and possibly relay it
 < "friend made public edit based on http://google.com/"

 Getting the word out about revisions to a resource will be more about
 telling peers you have a different hash of a resource, or telling known
 peers directly. Problems may arise if popular destinations have many
 competing revisions. Sum the number of hashes and generally go with the
 most-replicated.

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
from synchrony.models import Peer, Revision
from itertools import takewhile, imap, izip
from collections import OrderedDict, Counter

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

        alpha is the amount of concurrent requests at a time to use when spidering
        for values.

        id may come from the database if we've previously been in the network before.
        nodes is a list of (address,port) tuples to bootstrap into the network with.
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

        seed    = "%s:%i:%s" % (addr,port,pubkey)

        self.node = Node(id or utils.generate_node_id(seed),
                         addr,
                         port,
                         pubkey)

#        log(self.node.long_id)
        self.buckets  = [KBucket(0, 2 ** 160, self.ksize)]
        self.protocol = SynchronyProtocol(self, self.node, Storage(), ksize)

        # This makes it easy for test suites select which method to use.
        # Note that if you use a different storage method then it's up to you
        # to set self.protocol up with any corresponding storage class.
        self.storage_method = self.protocol.rpc_append

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
#                    seed              = '%s:%i:%s' % ()
#                    self.node.id      = utils.generate_node_id(seed)
#                    self.node.long_id = long(self.node.id.encode('hex'), 16)
#                    self.protocol     = SynchronyProtocol(self, self.node, Storage(), self.ksize)
#                    unique            = False
#                    break

#            if not unique:
#                self.leave_network()
#                self.bootstrap(app.bootstrap_nodes)
#                self.find_own_id()
#                return
        log("Using node ID " + str(self.node.long_id))

    def leave_network(self):
        """
        Create a spider to tell close peers we won't be available to respond
        to requests.
        """
        threads = []
        for node in self:
            threads.append(gevent.spawn(self.protocol.rpc_leaving, node))
        if threads:
            log("Telling peers we're leaving the network.")
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
        if isinstance(node, list):
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
        if isinstance(key, Revision):  # This permits rev = app.routes[content_hash]
            if key.url:
                key = key.url
            else:
                key = key.hash

        # url here is passed to ValueSpider so it can be a param to
        # SynchronyProtocol.fetch_revision, which can then set
        # SynchronyProtocol.downloads correctly. The reason this is done is 
        # because tracking a pages' <link>, <script> and <img> downloads via
        # headers when that page is in an iframe isn't supposed to be possible.
        # It's a protection for visiting security-sensitive sites, which is a
        # good design. Instead we memorise all DHT downloads and let admins do
        # the trust rating feedback.
        url  = key
        node = Node(digest(key))
        nearest = self.find_neighbours(node)
        if len(nearest) == 0:
            log("There are no known neighbours to get %s" % key)
            return None
        # Unfortunately long list of arguments but it helps us map {url: peer_who_served}
        spider = ValueSpider(
                    self.protocol,
                    node,
                    nearest,
                    self.ksize,
                    self.alpha,
                    url
                 )
        # If spider.find() returns a revision object then it's only this method
        # that can associate it with the correct Resource and Domain.
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

        log("Adjusting local storage table.")
        self.protocol.storage[hexlify(hashed_url)] = (content_hash, self.node)

        def store(nodes):
            """
            A closure for a dictionary of responses from ALPHA nodes containing
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
    def __init__(self, router, source_node, storage, ksize):
        """
        Methods beginning with rpc_ define our outward calls and their
        handle_ counterparts define how we deal with their receipt.
        Also requires a storage object.
        Check RoutingTable.__init__ out to see how that looks.
        """
        self.router        = router
        self.storage       = storage
        self.source_node   = source_node
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
        data = transmit(self.router, addr, {"rpc_ping":True})
        # Remove peer
        if not data:
            if isinstance(addr, Node):
                self.router.remove_node(addr)
            return
        node = Node(*data['node'], pubkey=data['pubkey'])
        self.router.add_contact(node)
        # FIXME: Ping nodes in the 'peers' part of the response.
        #        Don't let malicious nodes fill the routing table with
        #        information for peers who won't respond.
        if 'peers' in data:
            for peer in data['peers']:
                if peer['node'][0] == self.source_node.long_id:
                    continue
                peer = Node(*peer['node'], pubkey=peer['pubkey'])
                self.router.add_contact(peer)
#                self.rpc_ping(node)
        return node

    def rpc_chat(self, node, data):
        """
        Implements CHAT where we encrypt a message destined for the user with
        UID on the receiving node.

        Message data should be of the form
        { 
           'to': 'uid',
           'from': ['uid', 'username'],
           'body': 'message content'
        }   
        """
        data = base64.b64encode(json.dumps(data))
        key  = RSA.importKey(node.pubkey)
        data = key.encrypt(data, 32)
        transmit(self.router, addr, {'rpc_chat': data})

    def rpc_edit(self, node, data):
        """
        Implements inter-instance EDIT.

        Message data should be of the form
        { 
           'stream': 'stream_id',
           'from': ['uid', 'username'],
           'edit': '<span>Some DOM nodes to match and replace</span>'
        }   
        """
        data = base64.b64encode(json.dumps(data))
        key  = RSA.importKey(node.pubkey)
        data = key.encrypt(data, 32)
        transmit(self.router, addr, {'rpc_edit': data})

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

    def handle_chat(self, data):
        self.read_envelope(data)
        data = app.key.decrypt(data['rpc_chat'])
        pass

    def handle_edit(self, data):
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
        if type(data['rpc_find_value']) not in [unicode, str]: return
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
        { 'url_hash': {'content_hash': [(ts,nodeple)]}}
        """
        node = self.read_envelope(data)
        if node.trust < 0:
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
        
        if node.trust < 0:
            log("%s with negative trust rating tried to republish." % node, "warning")
            return False

        log("Received rpc_republish from %s." % node)
        republished_keys = data['rpc_republish']
        for message in republished_keys:
            
            if node.trust < 0:
                return False

            signature = (long(message['keys'].keys()[0]),)
            data      = message['keys'].values()[0]
            hash      = SHA256.new(data).digest()
            key       = RSA.importKey(message['node'][1])
            if not key.verify(hash, signature):
                log("Invalid signatures for keys provided by %s." % node, "warning")
                node.trust -= 0.01
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

    def fetch_revision(self, url, content_hash, nodes):
        """
        Return a revision object for a content hash given a list of peers.
        Called from ValueSpider._handle_found_values.
        """
        urls = []
        for node in nodes:
            if not self.router.get_existing_node(node):
                self.rpc_ping(node)
            node = self.router.get_existing_node(node)
            if node == None: continue
            if node.ip == self.source_node.ip and node.port == self.source_node.port:
                # We don't request revisions from our own HTTPD due to the
                # limitation of coroutines with a blocking call waiting for
                # a blocking call to yeild execution. Instead we just scan
                # the database directly.
                revision = Revision.query.filter(Revision.hash == content_hash)\
                    .first()
                if revision:
                    return revision
            elif node.ip == self.source_node.ip:
                addr = '127.0.0.1'
            else:
                addr = node.ip
            urls.append("http://%s:%i/v1/peers/revisions/%s" % \
                (addr, node.port, content_hash))
#        urls = ["http://%s:%i/v1/peers/revisions/%s" % \
#            (n[1],n[2],content_hash) for n in nodes]
        # TODO: Handle unresponsive peers
        headers = {'User-Agent': 'Synchrony %s' % app.version}
        threads = [gevent.spawn(requests.get, peer_url, headers=headers) for peer_url in urls]
        gevent.joinall(threads)
        threads = [t.value for t in threads]
        for response in threads:
            # Every type of scenario here is useful
            # If a peer was unresponsive then it tells us we have a peer to remove,
            # if a peer serves content that doesn't match the hash we went for then
            # there's a trust rating to adjust
            # and if we hit upon the content we're after then the sooner the better.
            if response and response.status_code != 200:
                continue
            revision = Revision()
            revision.add(response)
            if revision.hash != content_hash:
                node.trust -= 0.1
                log("Hash doesn't match content for %s", "warning")
                log("Decremented trust rating for %s." % node, "warning")
            else:
                # Adjust mimetype, set the network and increment bytes_rcvd
                if 'content-type' in response.headers:
                    revision.mimetype = response.headers['content-type']        
                if 'Content-Type' in response.headers:
                    revision.mimetype = response.headers['Content-Type']        
                revision.network = self.router.network
                app.bytes_received += revision.size

                # Remember this download in case we have feedback on it
                # Ideal data structure: {url: {hash: peerple}}
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
        #  TODO: Spawn green threads to ping these nodes.
        #  NOTE: Don't permit a spammer to abuse the routing topology.
        #        This can include decrementing the senders trust rating for
        #        referring us to dead nodes.
        if 'peers' in data:
            for peer in data['peers']:
                node = Node(*peer['node'], pubkey=peer['pubkey'])
                if node != self.source_node and self.router.is_new_node(node):
                    self.router.add_contact(node)

        # Update last_seen times for contacts or add if new
        node          = Node(*data['node'], pubkey=data['pubkey'])
        existing_node = self.router.get_existing_node(node)
        if existing_node:
            existing_node.last_seen = time.time()
            return existing_node
        elif node != self.source_node:
            self.router.add_contact(node)
            return node

    def decrement_trust(self, addr, severity):
        """
        Implements the feedback mechanism for our trust metric.
        
        "addr" is an (ip, port) tuple to match to a known peer.
        "severity" is a floating point severity level indicating how bad the
        content in question was perceived to be.

        Notes on how this all works in sum as a distributed system are here:
        http://nlp.stanford.edu/pubs/eigentrust.pdf
        http://www.cc.gatech.edu/~lingliu/papers/2012/XinxinFan-EigenTrust++.pdf
        http://dimacs.rutgers.edu/Workshops/InformationSecurity/slides/gamesandreputation.pdf

        The second PDF is highly recommended.
        """
        for node in self.router:
            if node.ip == addr[0] and node.port == addr[1]:
                amount = severity / 100.0
                log("Decrementing trust rating for %s by %f." % (node, amount), "warning")
                node.trust -= amount
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
            nodenode = self.replacement_nodes.pop()
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

class Node(object):
    def __init__(self, id, ip=None, port=None, pubkey=None):
        if isinstance(id, long):
            id = unhexlify('%x' % id)
        self.id        = id
        self.ip        = ip
        self.port      = port
        self.trust     = 0.00
        self.pubkey    = pubkey
        self.last_seen = time.time()
        self.long_id   = long(id.encode('hex'), 16) 
        self.name      = str(self.long_id)

    def same_home(self, node):
        return self.ip == node.ip and self.port == node.port

    def distance_to(self, node):
        return self.long_id ^ node.long_id

    @property
    def printable_id(self):
        return bin(self.long_id)[2:]

    @property
    def threeple(self):
        return (self.long_id, self.ip, self.port)

    def __iter__(self):
        return iter([self.id, self.ip, self.port])

    def __repr__(self):
        return "<Node %s:%s %.2fT>" % \
            (self.ip, str(self.port), self.trust)

    def __eq__(self, other):
        if other is None: return False
        return self.ip == other.ip and self.port == other.port 

    def jsonify(self, string_id=False):
        res = {}
        res['node']      = self.threeple
        res['trust']     = self.trust
        res['pubkey']    = self.pubkey
        res['last_seen'] = self.last_seen
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

class Siblings(object):
    """
    S/Kademlia sibling list.
    """
    def __init__(self, s=32):
        self.s = s

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
        self.revisions = 1000000000

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
        t = time.time()
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
        else:
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
        if self.bound and key in self.data and isinstance(self.data[key][1],list):
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
        self.left_buckets = table.buckets[:index]
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

class Routers(object):
    """
    Ease access to multiple overlay networks by network name.

    new_network         = RoutingTable(options, httpd, None, nodes)
    new_network.network = "private"
    routes              = Routers()
    routes['private']   = new_network

    routes['private']
    routes.get('private', None)
    """
    def __init__(self, routes={}):
        self.routes        = routes
        if not routes:
            self._default_name = None
        else:
            self._default_name = routes.values()[0].network

    def __getattr__(self, attr):
        if not attr.startswith("_") and attr in self.routes:
            return self.routes[attr]
        raise AttributeError

    def __getitem__(self, key):
        if key in self.routes:
            return self.routes[key]
        raise KeyError

    def __setitem__(self, key, value):
        assert isinstance(value, RoutingTable)
        if not self._default_name:
            self._default_name = value.network
        self.routes[key] = value

    def get(self, key, default=None):
        if key in self.routes:
            return self.routes[key]
        return default

    def append(self, value):
        assert isinstance(value, RoutingTable)
        self.routes[value.network] = value
        if not self._default_name:
            self._default_name     = value.network
 
    # FIXME: Subclass dictionaries instead.
    def values(self):
        return self.routes.values()

    def keys(self):
        return self.routes.keys()

    @property
    def _default(self):
        if not self.routes or not self._default_name:
            return None
        return self.routes[self._default_name]

    @property
    def routes_available(self):
        return self.routes != {}

    def leave_networks(self):
        """
        This is set as sys.exitfunc to tell all networks that we're leaving.
        """
        # TODO: Query for Node objects in the database.
        for router in self.routes.values():
            for node in router:
                p = Peer()
                p.load_node(router.network, node)
                db.session.add(p)
            router.leave_network()
        db.session.commit()
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
          1. Calls find_* to current ALPHA nearest not already queried nodes,
             adding results to current nearest list of k nodes.
          2. Current nearest list needs to keep track of who has been queried already.
             Sort by nearest, keep KSIZE.
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
                    and known_node.trust < 0:
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
    Add known peers, the public key and then
    sign the base64 encoded JSON of the data.

    For the time being we sign the time [...] as attributes
    never recombine in the same order on the receive side when
    parsed. This method guarantees that hashes match on both sides.
    """
    assert isinstance(data, dict)
    data['time']    = time.time()
    data['network'] = routes.network
    data['node']    = routes.node.threeple
    data['pubkey']  = app.key.publickey().exportKey() 
    data['peers']   = [peer.jsonify() for peer in routes.find_neighbours(routes.node)]

#    print "sending "+ sha1(json.dumps(data)).hexdigest()
    hash = SHA256.new(str(data['time'])).digest()
    data['signature'] = app.key.sign(hash, '')[0] 

    # base64 encode the json and sign.
#    import base64
#    payload = base64.b64encode(json.dumps(data))
#    hash = SHA256.new(payload).digest()
#    output = {
#        'data':      payload,
#        'signature': app.key.sign(hash, '')[0],
#        'pubkey':    app.key.publickey().exportKey()
#    }
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

def log(message, loglevel="info"):
    if isinstance(message, dict) or isinstance(message, list):
        message =  '\n' + pprint.pformat(message)
    _log("DHT: %s" % str(message), loglevel)

def digest(s):
    if not isinstance(s, str):
        s = str(s)
    return sha1(s).digest()

