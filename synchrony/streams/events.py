"""
Channels, a contacts list, direct messages, message buffers.
Should loosely base this on IRC with user modes and channel modes, possibly...

Consider also WebRTC session initiation.
"""
from cgi import escape
from synchrony import app, log, db
from synchrony.controllers.auth import auth
from synchrony.streams.utils import Stream, require_auth

class AnonUser(object):
    username = "Unknown"
    created = False

class Channel(object):
    def __init__(self, name=""):
        self.name  = name
        self.topic = ""
        self.modes = []
        self.clients = set()

class EventStream(Stream):
    """
    Friends list events, Chat and RTC sessions

    """
    socket_type = "main"

    def initialize(self):
        self.user     = None
#        Access to app.routes for
#        admin users to access via the /eval command...
#        "eval" is a nonexistent privilege that has to be created
#        and associated in the database manually.
        self.routes  = app.routes
        self.channels = {}
        self.channel = None
        self.modes   = []

        # This lets us cycle through stream connections on
        # the httpd and easily determine the session type.
        self.socket.socket_type       = "main"
        self.socket.appearing_offline = False
        log("Event stream init")

    def recv_connect(self):
        user = auth(self.request)
        if not user:
            self.request_reconnect()
        else:
            log("Received chat connection from %s" % user.username)
            self.user = user
            if not user.can("chat"):
                body = {"message":"Your user group doesn't have permission to chat"}
                self.emit("disconnect", body)
                self.send("disconnect")
                log("%s isn't permitted to chat." % user.username)

    def request_reconnect(self):
        """
        Shortcut for asking a client to reconnect.
        """
        log("Received chat connection before authentication. Requesting client reconnects.")
        self.emit("reconnect", {"m":"Reconnecting.."})

    def recv_message(self, data):
        log(data)
        self.emit("test", data)
        self.socket.send_packet({"test":"hello"})

    def recv_json(self, data):
        self.emit("test", data)
        self.broadcast("test", data)
        if self.user:
            log("Received JSON from %s: %s" % (self.user.username, str(data)))
        else:
            log("Received JSON: %s" % str(data))

    @require_auth
    def on_join(self, channel_name):
        """
        Join a channel by name. If the channel name is the address of a friend
        then we initiate an RPC_CHAT session to the remote host.
        """
        if self.user and self.user.username:
            if self.user.can("chat"):
                if self.channel and channel_name == self.channel[1]: return
                log("%s joined %s" % (self.user.username, channel_name))
                channel = Channel(name=channel_name)
                channel.clients.add(self)
                self.channels['_default']   = channel
                self.channels[channel_name] = channel
                self.join(channel_name)

                # Send an "init" message via RPC_CHAT to the remote host
                if channel_name.count("/") == 2:
                    network, node_id, uid = channel_name.split("/")
                    router = self.routes.get(network, None)
                    if router == None: return
                    friend = [f for f in self.user.friends if f.address == channel_name]
                    if not friend: return
                    friend = friend[0]
                    if not friend.peer: # Return if no known pubkey
                        return
                    data         = {}
                    data['to']   = friend.uid
                    data['from'] = [self.user.uid, self.user.username]
                    data['type'] = "init"
                    data['body'] = ""

                    resp = router.protocol.rpc_chat((friend.ip, friend.port), data)
                    if resp and "state" in resp and resp['state'] == "delivered":
                        self.emit("rpc_chat_init", resp)

    @require_auth
    def on_poll_friends(self):
        self.emit("friend_state", self.user.poll_friends(app.routes))

    @require_auth
    def on_update_status(self, status):
        log("%s changed status to %s." % (self.user.username, status.title()))
        self.user.status = status
        #db.session.commit()
        self.broadcast(self.channel[1], "update_status", self.user.jsonify())
 
    def broadcast(self, channel, event, *args):
        """
        This is sent to all in the channel in this particular namespace.
        """
        pkt = dict(type="event",
                    name=event,
                    args=args,
                    endpoint=self.ns_name)
        channel_name = self.get_channel_name(channel)
        for sessid, socket in self.socket.server.sockets.iteritems():
            if 'channels' not in socket.session:
                continue
            if channel_name in socket.session['channels'] and self.socket != socket \
            and not socket.appearing_offline:
                socket.send_packet(pkt)
               
    @require_auth
    def on_msg(self, msg):
        """
        Handle sending a message to a local user or a friend on a remote instance.
        """
        if self.user and self.channels.values():
            if self.user.created:
                body = {"u":self.user.username,"m":escape(msg)}
            else:
                body = {"u":self.user.username,"m":escape(msg),"a": True}
            channel = self.channels['_default']
            # Send message via RPC_CHAT to a remote host
            if channel.name.count("/") == 2:
                network, node_id, uid = channel.name.split("/")
                router = self.routes.get(network, None)
                print 1
                if router == None: return
                friend = [f for f in self.user.friends if f.address == channel.name]
                if not friend: return
                print 2
                friend = friend[0]
                if not friend.peer: # Return if no known pubkey
                    return

                print 3
                data         = {}
                data['to']   = friend.uid
                data['from'] = [self.user.uid, self.user.username]
                data['type'] = "message"
                data['body'] = msg

                resp = router.protocol.rpc_chat((friend.ip, friend.port), data)
                print 4
                if resp:
                    self.emit("privmsg", body)
                return
            log("Message to %s from %s: %s" % (channel.name, self.user.username, msg))
            self.broadcast(channel.name, "privmsg", body)
            self.emit("privmsg", body)
        else:
            self.request_reconnect()

    @require_auth
    def on_cmd(self, command):
        if self.user and self.channels.values():
            if command == "help":
                body  = '<strong>Hello and welcome to the help system.</strong><br >'
                body += "Available commands:<br />"
                body += HELP_TABLE # Defined at the end of this file
                self.emit("response", {"r": body})
            elif command == "usage":
                import resource
                rusage_denom = 1024
                rusage_denom = rusage_denom * rusage_denom
                mem  = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / rusage_denom
                body = "<em>Synchrony is currently using <strong>%iMb</strong> of memory.</em>" % mem
                self.emit("response", {"r":body})

            elif ' ' in command:
                cmd, params = command.split(' ',1)
                if cmd == "eval" and self.user.can("eval"):
                    self.emit("response", {"r":"<em>" + escape(str(eval(params))) + "</em>"})
                else:
                    self.emit("response", {"r":"Unknown command <em>%s.</em>" % escape(str(cmd))})
            else:
                self.emit("response", {"r":"Unknown command <em>%s.</em>" % escape(str(command))})

#            if self.user.created:
#                body = {"u":self.user.username,"r":escape(command)}
#            else:
#                body = {"u":self.user.username,"r":escape(command),"a": True}
#            log("Command from %s: %s" % (self.user.username, command))
#            self.emit("response", body)
        else:
            self.request_reconnect()

    def recv_disconnect(self):
#        print "received disconnect"
        pass

HELP_TABLE = """<table><tbody>
                <tr><td>/usage</td><td>Display memory consumption.</td></tr>
                </tbody></table>"""
#                <tr><td>/list</td><td>List available channels.</td></tr>
#                <tr><td>/join</td><td>Join a channel.</td></tr>

