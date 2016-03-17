# Differential synchronisation using diff-match-patch or operational transforms
# An awareness of events (save/connect/disconnect) in streaming
#
# Think of allocations here in terms of dom fragments.
import time
import copy
from synchrony import app, log
from synchrony.controllers.auth import auth
from synchrony.streams.utils import Stream, require_auth

class DocumentStream(Stream):
    """
    Manages the lifetime of a connection in relation to channels a user is
    interested in.

    Here a channel is a URL, a user ID or a shared string.

    Channels look like this:

        self.session = {'channels': set(['/documents_main'])}
    
    "/documents" is stored in self.ns_name and corresponds to the
    io.connect("/documents", {"resource":"stream"}); part of your client-side
    code and "main" is the channel name.

    self.join("somesite.net/page") introduces "/documents_somesite.net/page"
    to the set.
    """
    
    def initialize(self):
        """
        Individual connections have timestamped versions of documents meaning
        they're garbage collected when people disconnect and remaining users
        are left with the official history.
        """
        log("Document stream init")
        self.user               = None
        self.fragments          = []
        self.documents          = []
        self.participants       = []
        self.channel            = "" # Current URL.
        self.socket_type        = "document"

        if 'channels' not in self.session:
            self.session['channels'] = set()

    @require_auth
    def on_join(self, channel):
        log('%s has subscribed to the document stream for "%s".' % \
            (self.user.username, channel))
        self.join(channel)
        self.broadcast(self.channel, "join", self.user.jsonify())

    @require_auth
    def on_part(self, channel):
        if not self.authenticate(): return
        self.leave(channel)
        self.broadcast(self.channel[1], "part", self.user.jsonify())

    @require_auth
    def on_names(self, channel):
        self.authenticate()
        response = []
        channel_name = self.get_channel_name(channel)
        for session_id, socket in self.socket.server.sockets.iteritems():
            if not "rooms" in socket.session:
                continue
            if room_name in socket.session["channels"] \
            and socket != self.socket and socket.user:
                response.append(socket.user.jsonify())
        self.emit({"names": response})

    @require_auth
    def on_edit(self, update):
        """
        Send edit data to channel subscribers (remember that the channel is a
        URL), and any known participants.
        """
        if not self.channel:
            return
        
        log('DocumentStream: %s %s:%i.' % \
        (self.user.username, self.channel, len(update)))
        
        body = {"user":self.user.username,"document":update}
        self.broadcast(self.channel, "fragment", body)
            
        for addr in self.participants:
            network, node_id, remote_uid = addr.split("/")
            router = app.routes.get(network)
            if router:
                message = {"type": "edit",
                           "url":  self.channel,
                           "body": update}
                
                message['to']   = addr
                message['from'] = self.user.get_address(router)
                response = router.protocol.rpc_edit(message)
        
        self.emit(self.channel, body)

    @require_auth
    def on_add_participant(self, addr):
        if not addr in self.participants:
            self.participants.append(addr)
            self.emit("added_participant", addr)

    @require_auth
    def on_get_participants(self):
        return self.participants

    # Given that we see an inordinate amount of disconnects this just calls pass
    @require_auth
    def recv_disconnect(self):
        pass

