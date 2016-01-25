# _*_ coding: utf-8 _*_
"""
Implements a base class for all Synchrony test suites to quickly create peer nodes.
"""
import time
import pprint
import random
import hashlib
import unittest
import binascii
import urlparse
from copy import deepcopy
from synchrony import app
from synchrony.models import Revision
from synchrony.controllers import dht
from synchrony.controllers import utils

class BaseSuite(unittest.TestCase):

    dfp            = 0.0          # 0% of peers are malicious by default
    alpha          = 0.0
    beta           = 0.85         # Normalisation factor
    ksize          = 20
    iterations     = 100          # calculate_trust iterates 100 times by default
    peer_amount    = 25
    storage_method = "rpc_append"

    def setUp(self):
        print "\nCreating %i peers configured to use %s." % \
            (self.peer_amount, self.storage_method)

        self.peers = create_peers(self.peer_amount, self.ksize, self.storage_method)

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
        
        dht.log("Creating %i pre-trusted peers." % honest_count)
        for j in range(honest_count):
            self.honest_peers[self.peers[count+j].node.long_id] = self.peers[count+j]

        for router in self.honest_peers.values():
            for r in self.honest_peers.values():
                if router.node.threeple == r.node.threeple: continue
                node = router.get_existing_node(r.node.threeple)
                if not node: continue
                node.trust += node.epsilon
                router.tbucket[node.long_id] = node
                # dht.log("Introduced %s to %s as a pre-trusted peer." % (node, router))

        # We add these RoutingTable objects as an attributes of mocked methods
        # so they can find other nodes and work on their protocol instances.
        #
        # Even though we're emulating dht.SynchronyProtocol to avoid network
        # and database calls, we still stick our mock functions on those instances
        # for the time being.
        mock_transmit.peers       = self.peers
        dht.transmit              = mock_transmit
        mock_get.peers            = self.peers
        dht.get                   = mock_get
        #mock_fetch_revision.peers = self.peers
        #for key in self.peers:
        #    self.peers[key].protocol.fetch_revision = mock_fetch_revision

def create_peers(peer_amount, ksize, storage_method):
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
        
        # Our TestProtocol is a subclass that calls methods on peer routing
        # tables directly instead of making network calls and database commits.
        peers[i].protocol = TestProtocol(
                                peers[i],
                                dht.Storage(),
                                peers[i].ksize,
                                peers
                            )
        
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
    dht.log("Unique port numbers: %s" % str("Yes." if unique_ports else "No. Recreating."))
    if not unique_ports:
        return create_peers(peer_amount, storage_method)
 
    dht.log("Introducing peers to one another.")
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
                dht.log("%s tried to call unknown procedure %s." % \
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
    first_node = mock_fetch_revision.peers.values()[0].node
    f = lambda x: x.node.threeple == first_node.threeple
    c = filter(f, nodes)
    if not c: return
    c = c[0]
    
    return  Revision.query.filter(Revision.hash == content_hash).first()

class TestProtocol(dht.SynchronyProtocol):
    def __init__(self, router, storage, ksize, peers):
        self.peers         = peers
        self.ksize         = ksize
        self.router        = router
        self.epsilon       = 0.0001
        self.storage       = storage
        self.source_node   = router.node
        self.downloads     = dht.ForgetfulStorage()         # content_hash -> (n.ip, n.port)
        self.received_keys = dht.ForgetfulStorage(bound=2)  # node -> [republish_messages,..]

        super(dht.SynchronyProtocol, self).__init__()

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
        data = dht.transmit(self.router, addr, {"rpc_ping":True})
        # Remove peer
        if not data:
            if isinstance(addr, Node):
                self.router.remove_node(addr)
            return
        node = dht.Node(*data['node'], pubkey=data['pubkey'], router=self.router)
        self.router.add_contact(node)
        # FIXME: Ping nodes in the 'peers' part of the response.
        #        Don't let malicious nodes fill the routing table with
        #        information for peers who won't respond.
        if 'peers' in data:
            for peer in data['peers']:
                if peer['node'][0] == self.source_node.long_id:
                    continue
                peer = dht.Node(*peer['node'],
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

    def rpc_add_friend(self, local_uid, addr):
        """
        addr is of the form "network_name/node_id/remote_user_id"
        Implements ADD_FRIEND where we find the node in addr and
        tell them a local user wants to add the remote UID as a friend.
        """
        if addr.count("/") != 2:
            return False, None
        network, node_id, remote_uid = addr.split("/")
        
        if network != self.router.network:
            return False, None

        node = dht.Node(long(node_id))
        nearest = self.router.find_neighbours(node)
        if len(nearest) == 0:
            dht.log("There are no neighbours to help us add users on %s as friends." % node_id)
            return False, None
        spider  = NodeSpider(self, node, nearest, self.ksize, self.router.alpha)
        nodes   = spider.find()

        if len(nodes) != 1:
            return False, None

        node    = nodes[0]

        # Sometimes spidering doesn't get us all the way there.
        # Check who we already know:
        if node.long_id != long(node_id):
            nodes = [n for n in self.router if n.long_id == long(node_id)]
            if len(nodes) != 1:
                return False, None
            node = nodes[0]

        dht.log(node_id, "debug")
        dht.log(node.long_id, "debug")

        dht.log("Found remote instance %s." % node)
        message = {"rpc_add_friend": {"from": local_uid, "to": remote_uid}}

        response = dht.transmit(self.router, node, message)
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
           'type': Can be any of "message", "init", "close"
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
        response = dht.transmit(self.router, node, {'rpc_chat': data})
        dht.log(response, "debug")
        return response

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
        dht.transmit(self.router, addr, {'rpc_edit': data})

    def rpc_leaving(self, node):
        addr = self.get_address(node)
        return dht.transmit(self.router, addr, {"rpc_leaving":True})

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
        return dht.transmit(self.router, addr, data)

    def rpc_find_node(self, node_to_ask, node_to_find):
        address = (node_to_ask.ip, node_to_ask.port)
        message = {'key': node_to_find.id}
        message = dht.envelope(self.router, message)
        return self.handle_find_node(message)

    def rpc_find_value(self, node_to_ask, node_to_find):
        address = (node_to_ask.ip, node_to_ask.port)
        message = {'rpc_find_value': binascii.hexlify(node_to_find.id)}
        return dht.transmit(self.router, address, message)

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
        return dht.transmit(self.router, addr, data)

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
            keynode = dht.Node(sha1(key).digest())
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
        dht.log("Received rpc_ping from %s." % node)
        return dht.envelope(self.router, {'ping':"pong"})

    def handle_add_friend(self, data):
        """
        Match to UID and return a new Friend instance representing our side.
        """
        assert "rpc_add_friend" in data

        dht.log(data, "debug")
        request   = data['rpc_add_friend']

        if not "from" in request or not "to" in request:
            return False

        node         = self.read_envelope(data)
        user         = User.query.filter(User.uid == request['to']).first()
        if not user: return None
        from_addr    = "/".join([self.router.network, str(node.long_id), request['from']])
        friend       =  Friend.query.filter(
                            and_(Friend.address == from_addr, Friend.user == user)
                        ).first()
        if friend:
            # This permits the remote side to see if they're added or blocked.
            return dht.envelope(self.router, {"response": friend.jsonify()})
        
        node = dht.Node(*data['node'])

        network = Network.query.filter(Network.name == self.router.network).first()
        
        if network != None:
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

        return dht.envelope(self.router, {"response": friend.jsonify()})

    def handle_chat(self, data):
        """
        Move a message from a remote node up to the UI if the recipient
        UID has an active connection to the chat stream.
        """
        node            = self.read_envelope(data)
        # With the ciphertext being a binary string we also b64encode it
        message_content = base64.b64decode(data['rpc_chat'])
        message_content = app.key.decrypt((message_content,))
        data            = json.loads(base64.b64decode(message_content))
        dht.log(message_content, "debug")
        dht.log(data, "debug")

        user = User.query.filter(User.uid == data['to']).first()
        if user == None:
            return {"error": "No such user."}

        friend = Friend.query.filter(and_(Friend.user    == user,
                                          Friend.network == self.router.network,
                                          Friend.node_id == str(node.long_id),
                                          Friend.uid     == data['from'][0])
                                    ).first()
        if friend:

            available = utils.check_availability(self.router.httpd, "chat", user)
            if not available:
                return {"error": "The intended recipient isn't connected to chat."}

            if data['type'] == "init":
                # Enable the recipient to reply by forcing them into the channel
                dht.log("Changing chat channel of %s to %s." % \
                    (user.username, friend.address), "debug")
                utils.change_channel(self.router.httpd,
                                     "chat",
                                     user,
                                     friend.address)
                utils.broadcast(self.router.httpd,
                                "chat",
                                "rpc_chat_init",
                                data['from'],
                                user=user)
            
            if data['type'] == "message":
                utils.broadcast(self.router.httpd,
                                "chat",
                                "rpc_chat",
                                data,
                                user=user)
        return {"state": "delivered"}

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
        node = dht.Node(data['key'])
        dht.log("Finding neighbours of %s." % node.long_id)
        nodes = {'nodes': [p.jsonify() for p in \
                self.router.find_neighbours(node, exclude=source)]}
        return dht.envelope(self.router, nodes)

    def handle_find_value(self, data):
        source = self.read_envelope(data)
        if not source: return
        if not 'rpc_find_value' in data: return
        # usually comes in as unicode
        if not isinstance(data['rpc_find_value'], (unicode, str)):
            return
        key = data['rpc_find_value']
        dht.log("Finding value for %s" % key)
        value = self.storage.get(key, None)
        if key is None:
            dht.log("No value found for %s" % key)
            return self.rpc_find_node(sender, nodeid, key)
        dht.log("Found %s" % value)
        return dht.envelope(self.router,{'value':value})

    def handle_append(self, data):
        """
        Handle messages of the form {'rpc_append': {'url_hash': 'content_hash'}}
        We do this by inserting the data into a structure that looks like
        { 'url_hash': {'content_hash': [(ts,nodeple)]}}
        """
        node = self.read_envelope(data)
        if max(node.trust, 0) == 0:
            dht.log("%s with negative trust rating tried to append." % node, "warning")
            return False
        url_hash, content_hash = data['rpc_append'].items()[0]
        dht.log("Received rpc_append request from %s." % node)
        dht.log("Adjusting known peers for %s." % url_hash)
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
            dht.log("%s with negative trust rating tried to republish." % node, "warning")
            return False

        dht.log("Received rpc_republish from %s." % node)
        republished_keys = data['rpc_republish']
        for message in republished_keys:
            
            if max(node.trust, 0) == 0:
                return False

            signature = (long(message['keys'].keys()[0]),)
            data      = message['keys'].values()[0]
            hash      = SHA256.new(data).digest()
            key       = RSA.importKey(message['node'][1])
            if not key.verify(hash, signature):
                dht.log("Invalid signatures for keys provided by %s." % node, "warning")
                node.trust -= node.epsilon
                continue

            try:
                keys = json.loads(base64.b64decode(data))
            except Exception, e:
                dht.log("Error unserialising republished keys: %s" % e.message, "error")
                continue

            referee = dht.Node(*message['node'][0], pubkey=message['node'][1])
            if self.router.is_new_node(referee):
                self.rpc_ping(referee)
            
            # Get the trust rating of this referee
            referee = self.router.get_existing_node(referee)
            if not referee or referee.trust < 0:
                dht.log("%s is currently republishing for %s." % (node, referee), "warning")
                continue

            self.storage.merge(keys)
            self.received_keys[referee.id] = message

        return True

    def fetch_revision(self, url, content_hash, nodeples):
        """
        Accesses the most trustworthy peers' routing table and see if they have
        any references to themselves for the desired url/content_hash pair.
        
        Updates local download references and then returns the revision.
        """
        urls       = []
        nodes      = []
        routers    = []
        hashed_url = hashlib.sha1(url).digest() 
        revision   = Revision.query.filter(Revision.hash == content_hash).first()

        if revision == None:
            dht.log("No match for %s could be found in the current database.", "error")

        for n in nodeples:
            if n[1] == self.source_node.ip and n[2] == self.source_node.port:
                continue
            
            # Get local references to peer nodes
            node = self.router.get_existing_node(n)
            if node:
                nodes.append(node)
                continue
            node = self.rpc_ping(n)
            if node == None:
                continue

        # Get remote peer by its own routing table
        # TestProtocol.peers is test suite shorthand for all peers
        for node in dht.sort_nodes_by_trust(nodes):
            for router in self.peers.values():
                if node.threeple == router.node.threeple:
                    routers.append(router)
        
        if not any(routers):
            return None

        for router in routers:
            node = self.router.get_existing_node(router.node.threeple)
            
            node.trust += node.epsilon

            references = router.protocol.storage\
                .get(binascii.hexlify(hashed_url), None)
            if not references: continue
            
            # downloads is a list of (timestamp, node_triple) pairs.
            downloads = references.get(content_hash)
            if not any(downloads): continue
            
            for download in downloads:
                if download[1] == router.node.threeple:
                    self.downloads[url] = {revision.hash: (node.ip, node.port)}
                    return revision
        
        return None

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
            dht.log("Republishing keys.")
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
            dht.log("\"%s\" is using an incorrect node ID." % data['node'][1], "warning")
            return

        # Learn of peers
        #  TODO: Spawn green threads to ping these nodes.
        #  NOTE: Don't permit a spammer to abuse the routing topology.
        #        This can include decrementing the senders trust rating for
        #        referring us to dead nodes.
        if 'peers' in data:
            for peer in data['peers']:
                node = dht.Node(*peer['node'], pubkey=peer['pubkey'], router=self.router)
                if node != self.source_node and self.router.is_new_node(node):
                    self.router.add_contact(node)

        # Update last_seen times for contacts or add if new
        node          = dht.Node(*data['node'], pubkey=data['pubkey'], router=self.router)
        existing_node = self.router.get_existing_node(node)
        if existing_node:
            existing_node.last_seen = time.time()
            return existing_node
        elif node != self.source_node:
            self.router.add_contact(node)
            return node

    def decrement_trust(self, addr, severity=1):
        """
        Implements the feedback mechanism for our trust metric.
        
        "addr" is an (ip, port) tuple to match to a known peer.
        "severity" is a floating point severity level indicating how bad the
        content in question was perceived to be.

        Notes on how this all works in sum as a distributed system are here:
        http://nlp.stanford.edu/pubs/eigentrust.pdf
        http://www.cc.gatech.edu/~lingliu/papers/2012/XinxinFan-EigenTrust++.pdf
        http://dimacs.rutgers.edu/Workshops/InformationSecurity/slides/gamesandreputation.pdf

        The second PDF is recommended.
        """
        for node in self.router:
            if node.ip == addr[0] and node.port == addr[1]:
                amount = severity / 100.0
                dht.log("Decrementing trust rating for %s by %f." % (node, amount), "warning")
                node.trust -= 2 * node.epsilon
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
 

