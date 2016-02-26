# Differential synchronisation using diff-match-patch or operational transforms
# An awareness of events (save/connect/disconnect) in streaming
#
# Think of allocations here in terms of dom fragments.
from synchrony import app, log
from synchrony.controllers.auth import auth
from flask import session, request, Response

from socketio import socketio_manage
from socketio.packet import encode, decode
from socketio.namespace import BaseNamespace
from socketio.mixins import RoomsMixin, BroadcastMixin

class DocumentStream(BaseNamespace, RoomsMixin, BroadcastMixin):
    """
    Manages the lifetime of a connection in relation to channels a user is
    interested in.

    Here a channel is a URL, a user ID or a shared string.

    In Gevent-SocketIO channels/rooms look like this:

        self.session = {'rooms': set(['/documents_main'])}
    
    "/documents" is stored in self.ns_name and corresponds to the
    io.connect("/documents", {"resource":"stream"}); part of your client-side
    code and"main" is the channel name.

    self.join("somesite.net/page") introduces "/documents_somesite.net/page"
    to the set.
    """
    user        = None
    socket_type = "document"
    channels    = {} # available types: url, uid, name
                     # Eg. {"uid": "f50068d167fc6"}

    def initialize(self):
        """
        Individual connections have timestamped versions of documents meaning
        they're garbage collected when people disconnect and remaining users
        are left with the official history.
        """
        self.fragments = []
        self.documents = []
        log("init document stream")
        self.document = None

    def recv_connect(self):
        self.check_auth()

    def recv_json(self, data):
        self.emit("test", data)
        self.emit_to_room("test", data)
        if self.user and self.document:
            log("Received JSON from %s on %s: %s" % (self.user.username, self.document, str(data)))
        else:
            log("Received JSON: %s" % str(data))

    def on_subscribe(self, document):
        user = auth(self.request)
        if user:
            self.user = user
            log('%s has subscribed to the document stream for "%s"' % (self.user.username, document))
        else:
            log('An anonymous user has subscribed to the document stream for "%s"' % document)
        self.document = document
        self.join(document)

    def on_names(self, channel):
        self.check_auth()
        response = []
        channel_name = self._get_room_name(channel)
        for session_id, socket in self.socket.server.sockets.iteritems():
            if not "rooms" in socket.session:
                continue
            if room_name in socket.session["rooms"] and socket != self.socket and socket.user:
                response.append(socket.user.jsonify())
        self.emit({"names": response})

    def on_part(self, channel):
        self.check_auth()
        self.leave(channel)

    def on_edit(self, update):
        self.check_auth()
        if not self.user:
            log("no user ")
        if self.document and self.user:
            log('DocumentStream: %s "%s":%i' % (self.user.username, self.document, len(update)))
            body = {"user":self.user.username,"document":update}
            self.emit_to_room(self.document, "fragment", body)
            # Tell the transmitter their edit is going through
#            self.emit("document", body)

    def recv_disconnect(self):
        if self.user and self.document:
            log('%s has disconnected from document stream "%s"' % (self.user.username, self.document))
        elif self.user:
            log('%s has disconnected from an unspecified document stream.' % self.user.username)

    def check_auth(self):
        if not self.user:
            user = auth(self.request)
            if user:
                log("Received document stream connection from %s" % user.username)
                self.user = user

    @property
    def itersockets(self):
        """
        Return a list of other active connections in this same namespace. 
        """
        _ = []
        for c in self.socket.server.sockets.values():
            if c.connected:
                for ns in c.active_ns.values():
                    if ns != self and ns.ns_name == self.ns_name:
                        _.append(ns)
        return _
