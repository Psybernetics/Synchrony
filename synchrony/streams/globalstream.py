# set of channels, a contacts list, direct messages, message buffers.
from cgi import escape
from synchrony import app, log, db
from synchrony.controllers.auth import auth
from synchrony.streams.utils import Stream, require_auth

# Business logic for the global activity stream
class GlobalStream(Stream):
    """
    Responsible for friends list events generally.
    
    Responsible for starting/stopping RPC EDIT sessions.
    """
    socket_type = "global_stream"

    def initialize(self):
        self.buffer          = []
        self.inbox           = None
        self.user            = None
        self.channel         = None
        self.default_channel = "#main"
        log("Activity stream init")

    @require_auth
    def recv_connect(self):
        """
        Don't adjust self.user.status here as it permits people to return
        to their appear-offline state.
        """
        log("Received activity stream connection from %s" % self.user.username)
        db.session.add(self.user)
        self.join(self.default_channel)

    @require_auth
    def on_poll_friends(self):
        self.emit("friend_state", self.user.poll_friends(app.routes))

    @require_auth
    def on_update_status(self, status):
        if not self.channel:
            self.join(self.default_channel)
        log("%s changed status to %s." % (self.user.username, status.title()))
        self.user.status = status
        #db.session.commit()
        self.broadcast(self.channel[1], "update_status", self.user.jsonify())

    @require_auth
    def on_join(self, channel):
#       if can(self.user.username, "rx_stream"):
        log('%s joined activity stream "%s"' % (self.user.username, channel))
        self.channel = channel
        self.join(channel)

    @require_auth
    def on_poll(self):
        if self.inbox:
            last_message = self.inbox[-1]
            for key, value in last_message.items():
                if key in self.buffer: continue
                self.buffer.append(key)
                self.emit("message", value)

    @require_auth
    def on_msg(self, msg):
        if self.user and self.channel:
            if self.user.created:
                body = {"u":self.user.username,"m":escape(msg)}
            else:
                body = {"u":self.user.username,"m":escape(msg),"a": True}
            log("Message to %s from %s: %s" % (self.channel, self.user.username, msg))
            self.emit_to_room(self.channel, "privmsg", body)
            self.emit("privmsg", body)
        
#    @require_auth
#    def recv_disconnect(self):
#        pass

