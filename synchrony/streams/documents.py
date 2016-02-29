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
        self.user        = None
        self.socket_type = "document"
        self.fragments   = []
        self.documents   = []
        self.channel     = () # Available types: url, addr, name.
                            # Eg. ("addr", "alpha/1252322141974278745698082250347869678457931551015/f50068d167fc6")
                            # This type implies we should synchronise with the local
                            # or remote user when they navigate.

        if 'channels' not in self.session:
            self.session['channels'] = set()

    @require_auth
    def on_join(self, channel):
        user = auth(self.request)
        if user:
            self.user = user
            log('%s has subscribed to the document stream for "%s"' % \
            (self.user.username, channel))
        else:
            log('An anonymous user has subscribed to the document stream for "%s"' % \
            channel)
        self.join(channel)

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
    def on_part(self, channel):
        if not self.authenticate(): return
        self.leave(channel)
        self.broadcast(self.channel[1], "part", self.user.jsonify())

    @require_auth
    def on_edit(self, update):
        if self.channel:
            log('DocumentStream: %s "%s":%i' % \
            (self.user.username, self.channel, len(update)))
            
            body = {"user":self.user.username,"document":update}
            self.broadcast(self.channel[1], "fragment", body)
            
            record = {"time":     time.time(), 
                      "channel":  copy.deepcopy(self.channel),
                      "fragment": update}

            self.emit(self.channel[1], body)

    @require_auth
    def recv_disconnect(self):
        if self.user and self.channel:
            log('%s has disconnected from channel %s' % \
            (self.user.username, str(self.channel)))
        elif self.user:
            log('%s has disconnected from an unspecified document stream.' % \
            self.user.username)

