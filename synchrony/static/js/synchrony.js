'use strict';
/* 
   Synchrony 0.0.1
   Copyright Luke Joshua Brooks 2015.
   A collaborative hyperdocument editor.
   
   Dedicated to God.
   There's multiple major religions. The beginning of the point.

   MIT License.

    This file contains the frontend for a peer-to-peer caching proxy that can
    make hyperdocuments collaboratively editable over the network.
    It also implements a friends list, chat and may implement WebRTC session
    initiation.

TODO:
/#request/:url     JavaScript to load /request/:url into .content

the /request/:url endpoint merely needs to remove javascript so as not to interfere with the window object.
 Global stream [Notify of remote sign-ins]
 localStorage controls
 Administrative chat controls.
 Ownership data.
 Allow owners to toggle public flag on revisions
 document group revision limit
 whichever threshold is met first
 formatted JSON event messages,
 {d:title, +chr@46,r:hash,s:[usernames]}
 OT or differential sync
 Undo/Redo
 Reduce the amount of objects used
 Account View (sessions, bio, undelete)
 Account Pages View (search, histories)
 Renaming based on checking availability
 Used a minified js file.

 Use /#settings to toggle:
  * Preferred peers.
  * Whether to transmit browsing activity.
    The default setting for User objects is to be private.
    This means not transmitting newly saved objects.

*/

// App init
(function(){
    window.App = {
        Config:          {},
        Views:           {},
        title:           " - Synchrony",
        editor:          undefined,
        history:         [],
        Friends:         new Friends(),
        stream_messages: []
    }

    // Ask the server who we are.
    $.get("/v1/users?me=1", function(data, status){
        App.Config.user = data;
    });

})();

// Tell Ractive.load where our mustache templates live.
Ractive.load.baseUrl = '/static/templates/';

/* We're using Backbone here because it gives us the option of
 * treating our Revision object as Backbone models.
 * A far nimbler alternative is to use page.js, as we're only
 * using Backbone.Router so far.
 *
 * URL hashes -> attributes on this router
 */   
App.Router = Backbone.Router.extend({
    routes: {
        '':                    'index',
//        'request':             'requestindex',
//        'request/:resource':   'requestresource',
        'user/:username':      'userview',
        'group/:name':         'groupview',
        'settings':            'settingsview',
        'settings/:network':   'networksettingsview',
        'chat':                'chatview',
        'login':               'loginview',
        'logout':              'logout',
        ':page':                'index',
//        '*default': 'renderError',
    },

//    Attributes -> functions in the environment
    index:                 indexView,
//    requestindex:       requestIndex,
//    requestresource:       requestView,
    userview:              userView,
    groupview:             groupView,
    settingsview:          settingsView,
    networksettingsview:   networkSettingsView,
    chatview:              chatView,
    loginview:             loginView,
    logout:                logout,

//    Any pre-post render behaviors
    before: function() {
        if (location.hash == '') {
            $('.main').addClass("main_background");
        }
    },
    after: function() {
        if ($('.iframe').contents().find("body").html() != ""){
            $('.main').addClass("drop_shadow");
        } else {
            $('.main').removeClass("drop_shadow");
        }
        
        if (location.hash != '') {
            $('.main').removeClass("main_background");
        }
        update_synchrony();
    },
});

// Start the Backbone URL hash monitor
new App.Router();
Backbone.history.start();

// Our error handler prints to the stream for ten seconds
function renderError(statement) {
    console.log('Error: ' + statement);
    App.stream_messages.push(statement);
    setTimeout(function(){ App.stream_messages.pop(); }, 10000);
}

// Push a global message to the stream for eight seconds
function renderGlobal(statement) {
    console.log('Global: ' + statement);
    App.stream_messages.reverse();
    App.stream_messages.push( '<span class="global-message">' + statement + '</span>' );
    App.stream_messages.reverse();
    setTimeout(function(){
        App.stream_messages.pop();
        App.stream_messages.reverse();
    }, 60000);
}

// Push $user is typing to the stream for three seconds
function renderTyping(statement) {
    App.stream_messages.push( '<span class="global-message">' + statement + '</span>' );
    setTimeout(function(){ App.stream_messages.pop(); }, 1000);
}

function linkUser(username){
    return '<a href="/#user/' + username + '">' + username + '</a>';
}

function timeStamp(ts, toNow) {
	var m = moment.unix(ts);
    if (toNow == true) { return m.toNow(true); }
	return m.format('MMMM Do YYYY, H:mm:ss');
//	return m.format('MMMM Do YYYY, h:mm:ss A');
}

// Take an array and modify a timestamp field with momentjs
function upDate(array, field, toNow){
    var array_copy = array.slice(0);
    for (var i = 0; i < array.length; i++){
        var ts = array[i][field];
        if (typeof ts != "number") { continue; }
        array_copy[i].timestamp = ts;
        array_copy[i][field]    = timeStamp(ts, toNow);
    }
    return array;
}

function pulseChat(){
    $("body").addClass("urgent-sidebar");
    setTimeout(function(){ $("body").removeClass("urgent-sidebar") }, 1000);
}

function paginate(list, page, per_page){
    if (per_page === "undefined"){ per_page = 10; }
    return list.slice(page * per_page - per_page, page * per_page)
}

function notify(message, options){
    if (!"Notification" in window) { return; }
    if (Notification.permission != "granted") {
        Notification.requestPermission();
    }
    options = options || {};
    options.icon = '/static/img/synchrony.png';
    
    var notification = new Notification(message, options);
    
    if ("onclick" in options) {
        notification.onclick = options.onclick;
    }
}

function toggle_synchrony(){
    if (App.Config.user){
        if (!$('.synchrony').hasClass("expanded")){
            update_synchrony();
            $('.synchrony').addClass("expanded");
            $('.synchrony').removeClass("contracted");
        } else {
            $('.synchrony').removeClass("expanded");
            $('.synchrony').addClass("contracted");
        }

        if (!$('.synchrony').hasClass("circular")){
            $('.synchrony').addClass("circular");
            $('.control_panel').hide();
        } else {
            $('.synchrony').removeClass("circular");
            $('.control_panel').show();
        }
    }
}

// This is for populating synchrony.tmpl on mouseover.
function update_synchrony(){
    
    if (App.Views.synchrony === undefined) { return; }

    $.get('/v1/networks', function(r){
        App.Views.synchrony.set({peers: r.peers});
    });
    
    $.get('/v1/domains/count', function(r){
        App.Views.synchrony.set({domains: r});
    });
    
    // Cool thing about the ?can parameter is it returns booleans.
    $.get('/v1/users/' + App.Config.user.username + "?can=see_all", function(response){
        App.Views.synchrony.set("showing_settings_button", response);
    });
    
    if ($('.iframe').contents().find("body").html() != "") {
        App.Views.synchrony.set("showing_edit_button", true);
        App.Views.synchrony.set("showing_hide_button", true);
        App.Views.synchrony.set("showing_invite_form", true);
    } else {
        App.Views.synchrony.set("showing_edit_button", false);
        App.Views.synchrony.set("showing_hide_button", false);
        App.Views.synchrony.set("showing_invite_form", false);
    }
    
    if (location.hash.split('/')[0] != '#' && location.hash.split('/')[0] != '') {
        App.Views.synchrony.set("showing_home_button", true);
    } else {
        App.Views.synchrony.set("showing_home_button", false);
    }

 }

function toggleMain(){
    if ($('.main').is(':visible')) {
        $('.main').hide();
        $('.show-hide').html('Show');
    } else {
        $('.main').show();
        $('.show-hide').html('Hide');
    }
}

function request(event){
    function update_address_bars(url) {
        location.hash = "request/" + url;
        if (App.Views.index != undefined) {
            App.Views.index.set({url: url});
        }
        if (App.Views.synchrony != undefined) {
            App.Views.synchrony.set({url: url});
        }
    }
    if (event.original.keyCode == 13){
        event.original.preventDefault();
        var iframe = $('.iframe');
        // Remove references to any prior stylesheets and scripts
        iframe.contents().find('head').html("");

        // Remove any schema from the url
        var url = this.get("url");
        if (url.indexOf("://") > -1){
                url = url.slice(url.indexOf("://")+3, url.length);
        }
        
        if ($('.main').is(':visible')) {
            toggleMain();
        }
        
        update_address_bars(url);
        App.history.push(url);

        if (App.editor) {
            App.editor.socket.emit("change_url", url);
        }

        $('iframe').contents().find('body').html("Loading...");

        var response = $.ajax({
            type: "GET",
            url: "/request/" + url,
            success: function(data, status){
                var headers    = response.getAllResponseHeaders();
                var header_map = {};
                headers = headers.split('\n');
                for (var i = 0; i  <= headers.length; i++) {
                    if (headers[i] && headers[i].indexOf(':') != -1) {
                        var items = headers[i].split(':');
                        header_map[items[0]] = items[1].slice(1, items[1].length);
                    }
                }
                App.current_hash = header_map["Content-Hash"];

                // Parse the received document
                var parser = new DOMParser();
                var doc    = parser.parseFromString(data, "text/html");
                // Clean out any errors
                var element = doc.getElementsByTagName("parsererror");
                for (var i = element.length - 1; i >= 0; i--) {
                    element[i].parentNode.removeChild(element[i]);
                }

                // Ensure that the <head> of the <iframe> is set properly.
                iframe.contents().find('body').html(data);
                iframe.contents().find('head').html($(doc).find('head').html());

                // Bind a callback to anchor tags so their href attribute
                // is appended to App.history when clicked.
                iframe.contents().find('a').on('click', function(){
                    var url = $(this).attr('href').split('/');
                    url = url.slice(2, url.length).join('/');
                    App.history.push(url);
                    update_address_bars(url);
                });
                
                update_synchrony();
            },
            error: function(data, status){
                console.log(data);
                console.log(status);
                var message = "There was an error loading this resource.";
                message = message + " Consult the logs for further information."
                iframe.contents().find('body').html(message);
            }
        });
    }
}

function toggle_editing (event){
    if ($('.edit_button').hasClass('active_button')) {
        $('.edit_button').removeClass('active_button');
        $('.toolbar').hide();
    } else {
        $('.edit_button').addClass('active_button');
        $('.toolbar').show();
    }
    var iframe = $('.iframe');
    var attr = iframe.contents().find('body').attr('contenteditable');
    if (typeof attr === typeof undefined || attr == false || attr == "false") {
        iframe.contents().find('body').attr('contenteditable','true');
        iframe.contents().find('body').attr('autocorrect','false');
        iframe.contents().find('body').attr('spellcheck','false');
        App.Views.synchrony.set('edit_button', "Done");
        $('.edit_button').html("Done");
        App.Views.synchrony.set("showing_save_button", true);
   } else {
        iframe.contents().find('body').attr('contenteditable','false');
        App.Views.synchrony.set('edit_button', "Edit");
        $('.edit_button').html("Edit");
        App.Views.synchrony.set("showing_save_button", false);
    }
}

// This function is pretty general in terms of populating tables
function populate_table(view, table_type, url){
    // Grab the data
    $.get(url, function(data){
        // Update the DOM on success
        view.set(table_type + "_paging_error", undefined);
        if (data.hasOwnProperty("data")) {
            data.data = upDate(data.data, "created");
        }
        view.set(table_type, data.data);
        view[table_type] = data;

        // Show navigation links depending on the response data
        // This is where the jsonapi.org style of {links: {next: "http://"}}
        // comes in handy.
        if (data.hasOwnProperty("links")) {
            if (data.links.hasOwnProperty("self")) {
            var url = data.links.self.split('page=')[1];
                if (url != undefined) {
                    if (url > 1) {
                        view.set(table_type + "_back_available", true);
                    } else {
                        view.set(table_type + "_back_available", false);
                    }
                } 
            }
            if (data.links.hasOwnProperty("next")) {
                view.set(table_type + "_forward_available", true);
            }
        }
    }).fail(function(){
       view.set(table_type + "_paging_error", true);
    });
}

function Friends(){
    this.list            = [];
    this.visible_list    = [];
    this.pending_invites = [];
    this.stream          = null;

    // Connect to /events and join a shared channel
    this.connect = function(){
        this.stream = io.connect('/events', {resource: "stream"});
        this.stream.emit("join", "events");
        // With the activity stream, joining a shared channel is taken care of
        // for us automatically.
//        this.global_stream.emit('join', "global");
   
        // Results of polling everyone for friend state
        this.stream.on("friend_state", function(data){
            this.repopulate_list(this.list, data);
            this.repopulate_list(this.visible_list, data);
        }.bind(this));

        // Update App.Views.userpage with the new friend request
        // if it's been loaded.
        this.stream.on("recv_friend_request", function(friend){
            console.log("Received friend request", friend);
            if (App.Views.userpage){
                var friends = App.Views.userpage.get("friends");
                friends.push(friend);
                App.Views.userpage.set("friends", friends);
            }
        }.bind(this));

        // A friend or ourselves performed a status update
        this.stream.on("update_status", function(data){
            console.log(data);
        }.bind(this));
    
        // Response from a remote instance when we've invited
        // a user to an editing session
        this.stream.on("sent_invite", function(data){
            console.log(data);
        }.bind(this));

        this.stream.on("rpc_edit_invite", function(data){
            console.log(data);
            
            if (!this.list.length) { this.poll(); }
            
            var friend = _.filter(this.list, function(e){
                return e.address == data['from'];
            });

            if (!friend.length) { return; }
            friend = friend[0];

            // Join the document and confirm the invite if this notification
            // is clicked.
            var options = {};
            options.onclick = function(){
                // swap the addresses.
                var _ = data["from"];
                data["from"] = data["to"];
                data["to"] = _;
                // Let the remote instance know the invitation was accepted.
                data["accepted"] = true;
                App.Friends.stream.emit("rpl_invite_edit", data);

                App.editor.join(data.url, friend.address);
                App.editor.sync();
            };

            notify("Click to join " + friend.username + ", editing " + data.url + ".",
                   options);
        
        }.bind(this));

        // Event handler for a user on a remote instance signifying they've
        // accepted an invite to edit with us.
        this.stream.on("rpl_edit_invite", function(data){
            App.editor.add_participant(data.from);
        }.bind(this));
    
        this.poll();
    }

    // Ask relevant nodes about relevant user accounts.
    this.poll = function(){
        if (!this.stream) { this.connect(); }
        this.stream.emit("poll_friends");
    }
    
    this.update_status = function(status){
        if (!this.stream) { this.connect(); }
        this.stream.emit("update_status", status);
    }

    // Zero a list in place.
    this.repopulate_list = function(list, replacement_data){
        list.length = 0;
        list.push.apply(list, replacement_data);
    }

    // Filter a list in place with Underscore.
    this.filter = function(query){
        if (query.length < 2) {
            this.repopulate_list(this.visible_list, this.list);
        } else {
            var filtered_data = _.filter(this.visible_list, function(e){
                return e.username.indexOf(query) > -1;
            });
            this.repopulate_list(this.visible_list, filtered_data);
        }
    }
    this.send_edit_invite = function(friend_addr, url){
        if (!this.stream){ this.connect(); }
        // Send the invite through to the remote instance
        this.stream.emit("invite_edit", {"to": friend_addr, "url": url});
        this.pending_invites = [];
        this.pending_invites.push(friend_addr);
    }
}

function modal(messages){

    // Place <div class="modal"></div> in the DOM if necessary
    var modal = document.getElementsByClassName("modal");
    if (!modal.length){
        $("body").append('<div class="modal"></div>');
    }

    if (!$.isArray(messages)) {
        messages = Array(messages);
    }

    // Combine with any existing messages
    if (App.Views.modal) {
        var existing = App.Views.modal.get("messages");
        existing = existing.reverse();
        messages = existing.concat(messages);
    }
    
    messages = messages.reverse();

    messages = {"messages": messages};

    Ractive.load({
        modal: 'modal.tmpl'
    }).then(function(components){
        App.Views['modal'] = new components.modal({
            el: $('.modal'),
            data: messages
        });
    
        $('.modal').draggable();
   
        App.Views.modal.on({
            close: function(event, thing){
                event.original.preventDefault();
                console.log(thing);
                if (thing == "modal"){
                    $(".modal").remove();
                } else if (typeof thing == "number"){
                    var messages = App.Views.modal.get("messages");
                    console.log(messages);
                    messages.splice(thing, 1);
                    App.Views.modal.set({"messages": messages});
                }
            }
        });
    });
}

function indexView(page){
    document.title = "Welcome" + App.title;
    Ractive.load({
        index: 'index.tmpl',
    }).then(function(components){
        if (!App.Config.user) {
            location.hash = "login";
        }

        App.Views['index'] = new components.index({
            el: $('.main'),
            data: App.Config,
            adaptor: ['Backbone'],
        });

        if (!$('.main').is(':visible')) {
            toggleMain();
        }

        if (!$('.main').hasClass('main_background')){
            $('.main').addClass("main_background");
        }

        // Get the initial set of visible revisions
        function populate_revision_table(url){
            $.get(url, function(response){
                App.Views.index.set("paging_error", undefined);
                response.data = upDate(response.data, "created", true);
                App.Views.index.set("revisions", response.data);
                App.Views.index.revisions = response;

                // back_available in index.tmpl
                if (response.links.hasOwnProperty("self")) {
                    var url = response.links.self.split('page=')[1];
                    if (url != undefined) {
                        // Change the url hash to reflect subpage
                        window.location.hash = "/" + url;
                        if (url > 1) {
                            App.Views.index.set("back_available", true);
                        } else {
                            App.Views.index.set("back_available", false);
                        }
                    } 
                }

                // forward_available in index.tmpl
                if (response.links.hasOwnProperty("next")) {
                    App.Views.index.set("forward_available", true);
                }
            }).fail(function(){
               App.Views.index.set("paging_error", true);
            });
        }

        // Support direct linking to subviews
        if (page != undefined) {
            populate_revision_table('/v1/revisions?page=' + page);
        } else {
            populate_revision_table('/v1/revisions');
        }

        App.Views.index.on({

            forward: function(event){
                populate_revision_table(this.revisions.links.next);
            },
            back: function(event){
                var url = this.revisions.links.self.split('page=');
                var page = url[1] - 1;
                populate_revision_table(url[0] + 'page=' + page);
            },
            // index template addressbar
            request: request,
            filter: function(event){
               console.log(event);
            }
       });
    });
}

function logout(){
//    location = '/logout/';    
    $.ajax({
        type: "DELETE",
        url: "/v1/users/" + username + "/sessions",
        data: {timestamp: App.config.user.session.created},
        success: function(data, status){
            console.log(data);
            console.log("Logged out");
            App.Config.user = null;
            App.Views.synchrony.set("Config", App.Config);
            location.hash = '';
            location = '/';
        },
        error: function(data, status){
            console.log("Error logging out:" + data);
        }
    });
}

function accountObjects(params){

    document.title = "Your pages" + App.title;
    Ractive.load({
        accountpages: 'accountpages.tmpl',
    }).then(function(components){

        App.Views['accountpages'] = new components.accountpages({
            el: $('.original'),
            data: { user: App.Config.user },
            adaptor: ['Backbone'],
        });

        $.get('/v1/users/' + App.Config.user.username + '/pages',
            function(data, status){
                for (var i = 0; i < data.pages.length; i++){
                    var ts = data.pages[i].created;
                    data.pages[i].timestamp = ts
                    data.pages[i].created = timeStamp(ts);
                    data.pages[i].index = i;
                }
                for (var i = 0; i < data.edits.length; i++){
                    var ts = data.edits[i].created;
                    data.edits[i].timestamp = ts
                    data.edits[i].created = timeStamp(ts);
                    data.edits[i].index = i;
                }
                App.Views.accountpages.set({user: data});
        }).fail(function(){
            renderError("Couldn't contact the document server.");
        });
        $.get('/v1/users/' + App.Config.user.username + '/pages?deleted=1',
            function(data, status){
                for (var i = 0; i < data.length; i++){
                    var ts = data[i].created;
                    data[i].timestamp = ts
                    data[i].created = timeStamp(ts);
                    data[i].index = i;
                }
                App.Views.accountpages.set({deleted_pages: data});
        }).fail(function(){
            renderError("Couldn't retrieve deleted pages");
        });

        App.Views.accountpages.on({
            toggle_edits: function(){
                $('.hidden-table').toggle();
                if (!App.Views.accountpages.showing_edits){
                    App.Views.accountpages.showing_edits = true;
                    $('.edits-button').html("Hide");
                } else {
                    App.Views.accountpages.showing_edits = false;
                    $('.edits-button').html("Show");
                }
            },
        });
    });
}

// This is /#users/<username>
// Should behave as a settings page for yourself but show your public revisions
// and user ID to others.
function userView(username, params){
    document.title = username + App.title;
    Ractive.load({
        userpage: 'userpage.tmpl',
    }).then(function(components){

        if (!App.Config.user) {
            location.hash = "login";
        }

        App.Views['userpage'] = new components.userpage({
            el: $('.main'),
            data: {profile: false},
            adaptor: ['Backbone'],
        });

        if (!$('.main').is(':visible')) {
            toggleMain();
        }

        // Populate the user address line
        $.get('/v1/networks', function(response){
            if (response.data.length > 0){
                var addresses = [];
                for (var i = 0; i < response.data.length; i++) {
                    var address = response.data[i].name + "/" + response.data[i].node_id;
                    address     = address + "/" + App.Config.user.uid;
                    addresses[addresses.length] = address;
                }
                App.Views.userpage.set("user_addresses", addresses);
            }
        });

        App.Views.userpage.set("public_revisions", App.Config.user.public);

        // Determine whether this is a profile or settings page.
        if (App.Config.user.username != username) {
            App.Views.userpage.set("show_profile", true);
            $.ajax({
                type: "GET",
                url: "/v1/users/" + username,
                success: function(data){
                    console.log(data);
                    if (data.sessions){
                        upDate(data.sessions, "created");
                    }
                    data.created = timeStamp(data.created);
                    App.Views.userpage.set("user", data);
                },
                error: function(data){
                    App.Views.userpage.set("profile_error", true);
                }
            });
            // Display the reset password form if viewing another user?
            $.get("/v1/users/" + App.Config.user.username + "?can=reset_user_pw",
                function(response){
                    App.Views.userpage.set("can_reset_user_pw", response);
                }
            );

//            populate_table(this, "revisions", "/v1//user/" + username + "/revisions");
            App.Views.userpage.set("can_reset_user_pw", undefined);
            App.Views.userpage.set("sessions_button",   "Show");
            App.Views.userpage.set("password_button",   "Show");
        } else {
            // Ugliest section in the file, but this stuff has to be somewhere
            App.Views.userpage.set("show_settings",     true);
            App.Views.userpage.set("sessions_button",   "Show");
            App.Views.userpage.set("revisions_button",  "Show");
            App.Views.userpage.set("avatar_button",     "Show");
            App.Views.userpage.set("friends_button",    "Show");
            App.Views.userpage.set("password_button",   "Show");
            App.Views.userpage.set("showing_sessions",  undefined);
            App.Views.userpage.set("showing_revisions", undefined);
            App.Views.userpage.set("showing_avatar",    undefined);
            App.Views.userpage.set("showing_friends",   undefined);
            App.Views.userpage.set("showing_password",  undefined);

            populate_table(App.Views.userpage, "revisions", "/v1/users/" + username + "/revisions");
            populate_table(App.Views.userpage, "friends",   "/v1/users/" + username + "/friends");
            populate_table(App.Views.userpage, "sessions",  "/v1/users/" + username + "/sessions");

            // For the correct upload endpoint for avatar images:
            App.Views.userpage.set("username", App.Config.user.username);
        }

        // Attach file drag/drop callbacks to .filedrop.
        $('.filedrop').on({
            dragover: function(event){
                event.preventDefault();
            },
            dragenter: function(event) {
                $(this).addClass("drop-hover");
            },
            dragleave: function(event) {
                $(this).removeClass("drop-hover");
            },
            drop: function(event) {
                event.preventDefault();
                $(this).removeClass("drop-hover");
                
                console.log(event.originalEvent.dataTransfer.files);
                var form     = $(".upload_revision");
                var fileData = new FormData(form);
                var files     = event.originalEvent.dataTransfer.files;
                for (var i = 0; i < event.originalEvent.dataTransfer.files.length; i++) {
                    fileData.append("revision", files[i], files[i].name);
                }

                // Perform the upload.
                var req = new XMLHttpRequest();
                req.open("POST", "/v1/users/" + App.Config.user.username + "/revisions", true);
                req.onload = function(ev){
                    if (req.status == 200) {
                        var msg = "Revision uploaded.";
                        populate_table(App.Views.userpage, "revisions", "/v1/users/" + username + "/revisions");
                    } else {
                        var msg = "Error " + req.status + " occurred loading your file : - (";
                    }
                    App.Views.userpage.set("revision_upload_message", msg);
                    setTimeout(function(){ 
                        App.Views.userpage.set("revision_upload_message", "");
                    }, 5000);
                }
                req.send(fileData);
            }
        });
        
        App.Views.userpage.on({
            toggle:  function(event, section){
                var button = section + "_button"
                var showing = App.Views.userpage.get("showing_" + section);
                if (showing === undefined) {
                    App.Views.userpage.set(button, "Hide");
                    App.Views.userpage.set("showing_" + section, true);
                } else {
                    App.Views.userpage.set(button, "Show");
                    App.Views.userpage.set("showing_" + section, undefined);
                }
            },
            toggle_menu: function(event, section, index){
                if (section == "friend") {
                    if ($("#friend-menu-" + index).css("display") == "none") {
                        $("#friend-menu-" + index).css("display", "inline");
                    } else {
                        $("#friend-menu-" + index).css("display", "none");
                    }
                }
            },
            forward: function(event, table_type){
                var url = this[table_type].links.next;
                populate_table(App.Views.userpage, table_type, url);
            },
            back:    function(event, table_type){
                var url = this[table_type].links.self.split('page=');
                var page = url[1] - 1;
                populate_table(App.Views.userpage, table_type, url[0] + 'page=' + page);
            },
            select:  function(event, type, index){
                if (type != "friend") {
                   var row = $('#' + type + '-' + index);
                   var c = row.children();
                   c = c[c.length -1];
                   if ($('#delete-' + type + '-' + index).css('visibility') === "hidden") {
                       c.style.visibility = "";
                   } else {
                       c.style.visibility = "hidden";
                   }
                }
                // Also show the toggle_public button for revisions
                if (type === "revision") {
                    if ($('#public-' + type + '-button-' + index).css('visibility') === "hidden") {
                        $('#public-' + type + '-button-' + index).css('visibility', '');
                        $('#public-' + type + '-text-'   + index).css('display',    'none');
                    } else {
                        $('#public-' + type + '-button-' + index).css('visibility', 'hidden');
                        $('#public-' + type + '-text-'   + index).css('display',    'initial');
                    }
                } else if (type == "friend") {
                    if ($('#' + type + '-menu-button-' + index).css('visibility') === "hidden") {
                        $('#' + type + '-menu-button-' + index).css('visibility', "");
                    } else {
                        $('#' + type + '-menu-button-' + index).css('visibility', "hidden");
                    }
                }
            },
            toggle_public: function(event, index){
                var revisions = this.get('revisions');
                var revision = revisions[index];
                console.log(revision);
                if (revision.public) {
                    $.ajax({
                        url: '/v1/revisions/' + revision.hash,
                        type: "POST",
                        data: {"public": null},
                        success: function(response){
                            // Replace current array at index in place.
                            console.log(response);
                            revisions[index] = response;
                            App.Views.userpage.set("revisions", revisions);
                        },
                        error: function(response){
                            console.log(response);
                        }
                    });
                } else {
                    $.ajax({
                        url: '/v1/revisions/' + revision.hash,
                        type: "POST",
                        data: {"public": true},
                        success: function(response){
                            // Replace current array at index in place.
                            console.log(response);
                            revisions[index] = response;
                            App.Views.userpage.set("revisions", revisions);
                         },
                        error: function(response){
                            console.log(response);
                        }
                     });
                 }
            },
            toggle_auto_public: function(event, default_public) {
                if (default_public) {
                    $.ajax({
                        url: "/v1/users/" + App.Config.user.username,
                        type: "POST",
                        data: {"public": true},
                        success: function(response){ App.Views.userpage.set({"public_revisions": true});  },
                        error:   function(response){ App.Views.userpage.set({"public_revisions": false}); }
                    });
               } else {
                    $.ajax({
                        url: "/v1/users/" + App.Config.user.username,
                        type: "POST",
                        data: {"public_revisions": null},
                        success: function(response){ App.Views.userpage.set({"public_revisions": null}); },
                        error:   function(response){ App.Views.userpage.set({"public_revisions": true}); }
                    });
                 }
            }, 
            delete: function(event, type, index){
                if (type === "revision") {
                    var revision = this.get('revisions')[index];
                    console.log(revision);
                    $.ajax({
                        url:  '/v1/revisions/' + revision.hash,
                        type: "DELETE",
                        success: function(response){
                            // Remove the row on success.
                            $('#' + type + '-' + index).remove();
                        }
                    });
                } else if (type === "session") {
                    var session = this.get('sessions')[index];
                    $.ajax({
                        url:  '/v1/users/' + App.Config.user.username + '/sessions',
                        type: "DELETE",
                        data: {timestamp: session.timestamp},
                        success: function(response){
                            // Remove the row on success.
                            $('#' + type + '-' + index).remove();
                        }
                    });
                } else if (type === "friend") {
                    var friend = this.get('friends')[index];
                    console.log(friend);
                    $.ajax({
                        url:  '/v1/users/' + App.Config.user.username + '/friends',
                        type: "DELETE",
                        data: {address: friend.address},
                        success: function(response){
                            // Remove the row on success.
                            $('#' + type + '-' + index).remove();
                        }
                    });
                }
            },
            create_revision: function(event){
                console.log(event);
            },
            update_avatar: function(event){
                console.log(event);
            },
            rename: function(event, type, index){
                if (event.original.keyCode == 13){
                    event.original.preventDefault();
                    if (type == "friend") {
                        var friends   = App.Views.userpage.get("friends");
                        var friend    = friends[index];
                        var new_name = App.Views.userpage.get("new_name");
                        console.log(friend);
                        $.ajax({
                            url: "/v1/users/" + App.Config.user.username + "/friends",
                            type: "POST",
                            data: {
                                    "address": friend.address,
                                    "name":    new_name
                            },
                            success: function(response){
                                friend.name    = new_name;
                                friends[index] = friend;
                                App.Views.userpage.set("friends", friends);
                                console.log(response);
                            },
                            error:   function(response){
                                var friends    = App.Views.userpage.get("friends");
                                friend.name    = "";
                                friends[index] = friend;
                                App.Views.userpage.set("friends", friends);
                            }
                        });
                    }
                }
            },
            search_revisions: function(event){
                if (event.original.keyCode == 13) {
                    event.original.preventDefault();
                }
                var search_query = this.get("search_query");
                console.log(search_query);
                if (search_query && search_query.length > 1){
                    $.ajax({
                        type: "GET",
                        url: "/v1/revisions/search/" + search_query,
                        success: function(response){
                            console.log(response);
                            if (response.data){
                                App.Views.userpage.set({"revisions": response.data});
                            }
                        }
                    });
                } else {
                    populate_table(
                        App.Views.userpage,
                        "revisions", "/v1/users/" + App.Config.user.username + "/revisions"
                    );
                }
            },
            toggle_rename: function(event, type, index){
                if (type == "friend"){
                    if ($("#friend-rename-" + index).css("display") == "none") {
                        var friend = App.Views.userpage.get("friends")[index];
                        App.Views.userpage.set("new_name", friend.name);
                        $("#friend-name-"   + index).css("display", "none"); 
                        $("#friend-rename-" + index).css("display", "inline");
                    } else {
                        $("#friend-name-" + index).css("display", "inline");
                        $("#friend-rename-" + index).css("display", "none"); 
                    }
                }
            },
            add_friend: function(event){
                if (event.original.keyCode == 13){
                    event.original.preventDefault();
                    var addr   = App.Views.userpage.get("friend_addr");
                    var count  = (addr.match(/\//g) || []).length;
                    if (count != 2) {
                        App.Views.userpage.set("friend_addr", "");
                        App.Views.userpage.set("add_friend_message", "Invalid address.");
                        setTimeout(function(){
                            App.Views.userpage.set("add_friend_message","")
                        }, 8000);
                        return;
                    }
                    $.ajax({
                        url: "/v1/users/" + App.Config.user.username + "/friends" ,
                        type: "PUT",
                        data: {address: addr},
                        success: function(response){
                            var friends = App.Views.userpage.get("friends");
                            friends.push(response);
                            App.Views.userpage.set("friends", friends);
                        },
                        error:   function(response){
                            console.log(response);
                        }
                    });
                }
            },
            accept_friend: function(event, index){
                var friends = App.Views.userpage.get("friends");
                var friend  = friends[index];
                if (friend) {
                    $.ajax({
                        url: "/v1/users/" + App.Config.user.username + "/friends",
                        type: "POST",
                        data: {"address": friend.address,
                                "state":   2},
                        success: function(response) {
                            console.log(response);
                            friends[index] = response;
                            App.Views.userpage.set("friends", friends);
                            // eugh..
                            $('#' + type + '-menu-button-' + index).css('visibility', "hidden");
                            $("#friend-menu-" + index).css("display", "none");
                        },
                        error: function(response) {
                            console.log(response);
                        }
                    });
                }
            },
            toggle_blocked_friend: function(event, index){
                var friends = App.Views.userpage.get("friends");
                var friend  = friends[index];
                if (friend) {
                    if (friend.status == "Blocked"){ // TODO: turn ints into labels
                        $.ajax({
                            url: "/v1/users/" + App.Config.user.username + "/friends",
                            type: "POST",
                            data: {"address": friend.address,
                                   "state":   2},
                            success: function(response){
                                friends[index] = response;
                                App.Views.userpage.set({"friends": friends});
                            },
                            error:   function(response){
                                console.log(response);
                            }
                        });
                    } else {
                        $.ajax({
                            url: "/v1/users/" + App.Config.user.username + "/friends",
                            type: "POST",
                            data: {"address": friend.address,
                                   "state":   3},
                            success: function(response){
                                friends[index] = response;
                                App.Views.userpage.set({"friends": friends});
                            },
                            error:   function(response){
                                console.log(response);
                            }
                        });
                    }
                }
            },
            initiate_chat: function(event, index){
                var friends = App.Views.userpage.get("friends");
                var friend  = friends[index];
                if (friend) {
                    // Ensures the back button takes us to the current view:
                    // location.hash = "chat";
                    // Load the template
                    chatView();
                    // Wait 1ms before requesting a chat session with a remote user
                    setTimeout(function(){
                        App.Views.chat.socket.emit("join", friend.address);
                    }, 100);
                }
            },
            initiate_collab: function(event, index){
                var friends = App.Views.userpage.get("friends");
                var friend  = friends[index];
                if (friend) {}
            },
            change_password: function(event){
                event.original.preventDefault();
                var current = App.Views.userpage.get("pass0");
                var pass1   = App.Views.userpage.get("pass1");
                var pass2   = App.Views.userpage.get("pass2");
                // Bit of client-side validation.
                if (pass1 != pass2) {
                    App.Views.userpage.set("password_message", "Passwords were mismatched.");
               } else {
                   // Validate current password
                    $.ajax({
                        type:    "POST",
                        url:     "/v1/users/" + username,
                        data:    {verify_password: App.Views.userpage.get("pass0")},
                        success: function(data){
                            console.log(data);
                            if (data != true) {
                                App.Views.userpage.set("password_message", "Incorrect password.");
                            } else {
                                // POST new password
                                $.ajax({
                                    type: "POST",
                                    url:  "/v1/users/" + username,
                                    data: {password: App.Views.userpage.get("pass1")},
                                    success: function(data, success, jq_obj){
                                        if (jq_obj.status == 304){
                                            App.Views.userpage.set("password_message", "Passwords must be at least six characters.");
                                        } else {
                                            App.Views.userpage.set("password_message", "Password successfully changed.");
                                        }
                                    }
                                }).fail(function(){
                                    App.Views.userpave.set({password_message: "Couldn't contact the server."});
                                });
                            }
                        }
                    }).fail(function(){
                        App.Views.userpage.set({password_message: "Couldn't contact the server."});
                    });
               }
            }
        });
    });
}

function groupView(name, params){
    document.title = name + " group" + App.title;
    Ractive.load({
        grouppage: 'grouppage.tmpl',
    }).then(function(components){

        if (!App.Config.user) {
            location.hash = "login";
        }

        App.Views['grouppage'] = new components.grouppage({
            el: $('.main'),
            data: {},
            adaptor: ['Backbone'],
        });

        if (!$('.main').is(':visible')) {
            toggleMain();
        }
       
        App.Views.grouppage.set({users_button:"Show",privileges_button:"Show"});

        function filterResponse(response){
        // Sticks the key attrs on a response 
            for (var i = 0; i < response.privileges.length; i++) {
                var key = Object.keys(response.privileges[i])[0];
                response.privileges[i].key   = key;
                response.privileges[i].value = response.privileges[i][key];
            }
            return response;
        }

        $.when(
            $.get('/v1/users/' + App.Config.user.username + '?can=modify_usergroup',
            function(response){
                App.Views.grouppage.set("can_modify_usergroup", response);
            })
         ).done(function(){
            if (App.Views.grouppage.get("can_modify_usergroup") != true) {
                window.location.hash = "#";
                return;
            }
        });

        $.ajax({
            url: "/v1/groups/" + name,
            success: function(response){
                response = filterResponse(response);
                App.Views.grouppage.set("group", response);
                App.Views.grouppage.set("no_such_group", false);
                App.Views.grouppage.set("server_unavailable", false);
            },
            error: function(response){
                if (response.status == 404) {
                    App.Views.grouppage.set("no_such_group", true)
                } else {
                    App.Views.grouppage.set("server_unavailable", true);
                }
            }
        });
        
        // Get all the privs from the server
        var privileges = [];
        var next = "/v1/privs"
        while (true){
            var r = undefined;
            $.ajax({
                url: next,
                type: "get",
                async: false,
                success: function(response){
                    r = response;
                }
            });
            if (!r || typeof r == "string") {
                break;
            } 
            console.log(r);
            privileges = privileges.concat(r.data);
            if (!"next" in r.links) {
                break;
            }
            next = r.links.next;
            console.log(privileges);
        }
        
        App.Views.grouppage.set("privileges", privileges);
        
        // Make privs draggable
        function dragMoveListener (event) {
            var target = event.target,
                // keep the dragged position in the data-x/data-y attributes
                x = (parseFloat(target.getAttribute('data-x')) || 0) + event.dx,
                y = (parseFloat(target.getAttribute('data-y')) || 0) + event.dy;

            // translate the element
            target.style.webkitTransform =
            target.style.transform =
              'translate(' + x + 'px, ' + y + 'px)';

            target.setAttribute('data-x', x);
            target.setAttribute('data-y', y);
        }
        
        interact('.draggable').draggable({
            inertia: false,
            restrict: {
                restriction: ".privileges-container",
                endOnly: true,
                elementRect: { top: 0, left: 0, bottom: 1, right: 1 }
            },
            autoScroll: true,

            // call this function on every dragmove event
            onmove: dragMoveListener,
            // call this function on every dragend event
            onend: function (event) {
                var textEl = event.target.querySelector('p');

                textEl && (textEl.textContent =
                'moved a distance of '
                + (Math.sqrt(event.dx * event.dx +
                             event.dy * event.dy)|0) + 'px');
            }
        });

        interact('.available-privileges').dropzone({
            // only accept elements matching this CSS selector
            accept: '.draggable',
            // Require a 75% element overlap for a drop to be possible
            overlap: 0.75,

            ondropactivate: function(event) {},
            ondragenter: function(event) {},
            ondragleave: function(event) {
                // remove the drop feedback style
                console.log("leave", event);
                if (event.target.className.indexOf("current-privileges") != -1) {
                    console.log("1Removing ",event.relatedTarget.outerText,"from",name);
                }
            },
            ondrop: function(event) {},
            ondropdeactivate: function (event) {
                if (event.relatedTarget.offsetParent.className == "available-privileges") {
                    return;
                }
                if (event.target.className == "current-privileges" &&
                    event.relatedTarget.parentElement.className == "available-privileges") {
                    return;
                }

                // Check that the dragged element didn't land in the container
                // it started in
                // for (var i = 0; i <= 3; i++) {
                //     if (i == 0) { var target = event.relatedTarget; }
                //     target = target['parentElement'];
                //     console.log(target);
                //     if (target.className == "current-privileges") { return; }
                // }

                if (event.target.className.indexOf("available-privileges") -1) {
                    console.log("Removing",event.relatedTarget.innerText,"from",name);
                    var priv = event.relatedTarget.innerText;
                    var privileges = App.Views.grouppage.get("group.privileges");
                    $.ajax({
                        url: "/v1/groups/" + name,
                        type: "POST",
                        data: {detach: priv},
                        success: function(response){
                            console.log(response);
                            for (var i = 0; i <= privileges.length; i++) {
                                if (privileges[i].key == priv) {
                                    privileges.splice(i, 1);
                                }
                            }
                            App.Views.grouppage.set("group.privileges", privileges); 
                            console.table(privileges);
                        }
                    });
                }
            }
        });

        interact('.current-privileges').dropzone({
            // only accept elements matching this CSS selector
            accept: '.draggable',
            // Require a 75% element overlap for a drop to be possible
            overlap: 0.75,
            ondropactivate: function(event) {},
            ondragenter: function(event) {},
            ondragleave: function(event) {
                console.log("leave", event);
                if (event.target.className.indexOf("available-privileges") != -1) {
                    console.log("Removing",event.relatedTarget.outerText,"from",name);
                }
            },
            ondrop: function(event) {},
            ondropdeactivate: function (event) {
                if (event.relatedTarget.offsetParent.className == "current-privileges") {
                    return;
                }
                console.log(event);
                if (event.target.className.indexOf("current-privileges") -1) {
                    console.log("Moving",event.relatedTarget.innerText,"to",name);
                    var priv = {key: event.relatedTarget.innerText, value: null}
                    var privileges = App.Views.grouppage.get("group.privileges");
                    var j = _.filter(privileges, function(p){
                        if (p.key == priv.key) {return true;}
                    });
                    // return if the privilege is already attached to the group
                    if (j.length) { return; }
                    $.ajax({
                        url: "/v1/groups/" + name,
                        type: "POST",
                        data: {attach: priv.key},
                        success: function(response){
                            console.log(response);
                            // Otherwise append it to current-privileges
                            privileges.push(priv);
                            App.Views.grouppage.set("group.privileges", privileges); 
                            console.table(privileges);
                        }
                    });
                }
            }
        });

        App.Views.grouppage.on({
            select:  function(event, type, index){
                if (type === "heading") {
                    if ($('#delete-button').is(':visible')) {
                        $('#delete-button').hide();
                   } else {
                        $('#delete-button').show();
                   }
                }
                // Also show the toggle_public button for revisions
                if (type === "priv") {
                    if ($('#' + type + '-button-' + index).css('visibility') === "hidden") {
                        $('#' + type + '-button-' + index).css('visibility', '');
                        $('#remove-' + type + '-button-' + index).css('visibility', '');
                        $('#' + type + '-text-'   + index).css('display',    'none');
                    } else {
                        $('#' + type + '-button-' + index).css('visibility', 'hidden');
                        $('#remove-' + type + '-button-' + index).css('visibility', 'hidden');
                        $('#' + type + '-text-'   + index).css('display',    'initial');
                    }
                }
            },
            toggle: function(event, section){
                var button = section + "_button";
                var showing = App.Views.grouppage.get("showing_" + section);
                if (showing === undefined) {
                    App.Views.grouppage.set(button, "Hide");
                    App.Views.grouppage.set("showing_" + section, true);
                } else {
                    App.Views.grouppage.set(button, "Show");
                    App.Views.grouppage.set("showing_" + section, undefined);
                }
            },
            delete: function(event){
                event.original.preventDefault();
                var group = this.get("group");
                if (group.name === undefined) { return; }
                $.ajax({
                    url: "/v1/groups",
                    type: "DELETE",
                    data: {"name": group.name},
                    success: function(response){
                        location.hash = '#settings';
                    },
                    error:   function(response){}
                });
            },
            toggle_allowed: function(event, index){
                event.original.preventDefault();
                var group = this.get("group");
                var priv = group.privileges[index];
                if (priv.value) {
                    $.ajax({
                        url: "/v1/groups/" + group.name,
                        type: "POST",
                        data: {deny: priv.key},
                        success: function(response){
                            response = filterResponse(response);
                            App.Views.grouppage.set("group", response);
                        }
                    });
                } else {
                    $.ajax({
                        url: "/v1/groups/" + group.name,
                        type: "POST",
                        data: {allow: priv.key},
                        success: function(response){
                            response = filterResponse(response);
                            App.Views.grouppage.set("group", response);
                        }
                    });
                }
            },
            remove: function(event, type, index) {
                if (type == "priv") {
                    var privileges = App.Views.grouppage.get("group.privileges");
                    var priv = privileges[index];
                    console.log(priv);
                    $.ajax({
                        url: "/v1/groups/" + name,
                        type: "POST",
                        data: {detach: priv.key},
                        success: function(response){
                            console.log(response);
                            privileges.splice(index, 1);
                            App.Views.grouppage.set("group.privileges", privileges); 
                        }
                    });
                }
            },
        });
    });
}

Ractive.load({
    content:   'content.tmpl',
    toolbar:   'toolbar.tmpl',
    synchrony: 'synchrony.tmpl',

}).then(function(components){

/*
    This is the content area of the page that holds external resources in an iframe
    it's loaded here so it can be displayed at all times alongside SPA templates.

    Also responsible for the toolbar of editor controls.

*/   App.Views['content'] = new components.content({
        el: $('.content'),
    });
    
    App.Views.content.editor = new SynchronyEditor($('.iframe'));
    
    App.editor = App.Views.content.editor;
    
    App.Views.content.editor.connect();


    App.Views['toolbar'] = new components.toolbar({
        el: $('.toolbar'),
    });

    $('.toolbar').hide();   

    App.Views.toolbar.on({
        exec: function(event, button_name) {
            App.Views.content.editor.exec(button_name, true);
        
        },
        inserthtml: function(event){
            if (event.original.keyCode == 13){
                event.original.preventDefault();
                var data = App.Views.toolbar.get("insert_html");
                App.Views.content.editor.exec("insertHTML", true, data);
                App.Views.toolbar.set("insert_html", "");
            }
        },
        insertimage: function(event){
            if (event.original.keyCode == 13){
                event.original.preventDefault();
                var data = App.Views.toolbar.get("image_url");
                App.Views.content.editor.exec("insertImage", true, data);
                App.Views.toolbar.set("image_url", "");
            }
        },
        createlink: function(event){
            if (event.original.keyCode == 13){
                event.original.preventDefault();
                var data = App.Views.toolbar.get("link_url");
                App.Views.content.editor.exec("createLink", true, data);
                App.Views.toolbar.set("link_url", "");
            }
        },
        toggle: function(event, type){
            if (type == "toolbar"){
                if ($(".toolbar_buttons").is(":visible")){
                    $(".toolbar_buttons").hide();
                } else {
                    $(".toolbar_buttons").show();
                }
            }
            if (type == "inserthtml" || type == "insertimage" || type == "createlink"){
                if ($("#toggle_" + type).is(":visible")){
                    $("#toggle_" + type).hide();
                } else {
                    $("#toggle_" + type).show();
                }
            }
        },
        select: function(event, cls){
            if ($("." + cls).hasClass("toolbar_selection")){
                $("." + cls).removeClass("toolbar_selection");
            } else {
                $("." + cls).addClass("toolbar_selection");
            }
        }
    });

    App.Views['synchrony'] = new components.synchrony({
        el: $('.synchrony'),
        data: {
            Config:      App.Config,
            stream:      App.stream_messages,
            friends:     App.Friends,
            edit_button: "Edit"
        },
    });

    App.Views.synchrony.set("showing_friends", false);

    if (!App.Friends.stream) {
        App.Friends.connect();
    }

    App.Friends.stream.on("message", function(data){
        App.stream.push(data.message);
        setTimeout(function(){ App.stream.pop(); }, 1000)
    });

    App.Views.synchrony.on({
        request: request, // Globally available request function
        edit: toggle_editing,
        save: function(event){
            $.ajax({
                url: "/v1/revisions/" + App.current_hash,
                type: "PUT",
                data: {"document": $('.iframe').contents()[0].all[0].innerHTML},
                success: function(response){
                    console.log(response);
                },
                error: function(response){
                    console.log(response);
                }
           });
        },
        settings: function(event){
            if (!$('.main').is(':visible')) {
                toggleMain();
            }
            window.location.hash = "#settings";
        },
        show_hide: function(event){ toggleMain(); },
        chat: function(event){
            if (!$('.main').is(':visible')) {
                toggleMain();
            }
            window.location.hash = "#chat";
        },
        invite: function(event){
            if (event.original.keyCode != 13){
                return;
            }
            event.original.preventDefault();
            var addr = App.Views.synchrony.get("invite_addr");
            var count  = (addr.match(/\//g) || []).length;
            if (count != 2) {
                // TODO: Consider i18n:
                modal("That field's for inviting remote addresses to edit with you.");
                App.Views.synchrony.set("invite_addr", "");
                return;
            }
            // An async friends request first
            $.ajax({
                url: "/v1/users/" + App.Config.user.username + "/friends" ,
                type: "PUT",
                data: {address: addr},
                success: function(response){ console.log(response); },
                error:   function(response){ console.log(response); }
            });
            
            var url = App.history[App.history.length - 1];
            if (!App.editor){
                renderError("No editor found.");
            }
            if (!App.editor.socket){
                App.editor.connect();
            }

            // Send the invitation to edit via App.Friends.stream
            App.Friends.send_edit_invite(addr, url);
            App.Views.synchrony.set("invite_addr", "");
        },
        friends: function(event){
            var showing_friends = App.Views.synchrony.get("showing_friends");
            App.Views.synchrony.set("showing_friends", !showing_friends);
            if (!showing_friends) {
                App.Friends.poll();
                $(".control_panel").addClass("friends_list_mode");
            } else {
                $(".control_panel").removeClass("friends_list_mode");
            }
        },
        filter_friends: function(event){
            if (event.original.keyCode == 13){
                event.original.preventDefault();
                App.Views.synchrony.set("filter_value", "");
            }
            var query = App.Views.synchrony.get("filter_value");
            App.Friends.filter(query);
        },
        select: function(event, type, index){
            if (type == "friend"){
                var selection = $("#friend_" + index);
                if (selection.css("display") == "none"){
//                    selection.css("display", "initial");
                    selection.show("fast");
                } else {
                    selection.hide("fast");
//                    selection.css("display", "none");
                }
            }
        },
        edit_with: function(event, friend){
            // Demo implementation for the time being
            // Assumes the remote side wants to edit
            if (!App.history.length){
                renderError("Unable to discern current URL from App.history");
                return;
            }
            var attr = $(".iframe").contents().find("body")
                                   .attr("contenteditable");
            if (attr != "true") {
                renderError("You must enter edit mode on a page first.");
                return;
            }
            var url = App.history[App.history.length - 1];
            if (!App.editor){
                renderError("No editor found.");
            }
            if (!App.editor.socket){
                App.editor.connect();
            }

            // Send the invitation to edit via App.Friends.stream
            App.Friends.send_edit_invite(friend.address, url);
    
            // App.editor.socket.join(friend.address);
        },
        chat_with: function(event, friend){
            console.log(friend);
        },
        block:     function(event, friend){
            console.log(friend);
        },
        update_status: function(event){
            var status = App.Views.synchrony.get("status");
            App.Friends.update_status(status);
        },
        logout: function(event){
            $.ajax({
                url:     "/v1/users/" + App.Config.user.username + "/sessions",
                type:    "DELETE",
                data:    {timestamp: App.Config.user.session.created},
                success: function(data){
                    
                    if ($(".control_panel").is(":visible")) {
                        toggle_synchrony();
                    }
                   
                    $(".toolbar").hide();

                    delete App.Config.user;
                    window.location.hash = "#login";
                },
                error:   function(data){
                    console.log("error");
                    console.log(data);
                },
            });
        },
    });
});

function chatView() {
    document.title = "Chat" + App.title;
    Ractive.load({chat: 'chat.tmpl'}).then(function(components){
        App.Views['chat'] = new components.chat({
            el: $('.main'),
            data: {chat_available: true},
            adaptor: ['Backbone']
        });
        
        if (!App.Config.user) {
            location.hash = "login";
        }
       
        $('.chat').draggable();
        var welcome_message = "Use <em>/help</em> for a list of commands.<br />";
        $('.chat-messages').append(welcome_message);

        App.Views.chat.visible = false;

        // An array of messages typed into the input field.
        App.Views.chat.doskeys = [];
        App.Views.chat.current_doskey = 0;

        // Join channel "main" and listen for messages
        if (!App.Friends.stream) { App.Friends.connect(); }

        // Recieve chat messages.
        App.Friends.stream.on("privmsg", function(data){
            console.log(data);
//            if (!App.Views.sidebar.visible){ pulseSidebar(); }
//            The anonymous flag is for if you've permitted unsigned-up users to chat
//            via the auth server.
//            data = {m:message, u:username, a:anonymous_flag}
            $('.chat-messages').append('&lt;' + linkUser(data.u) + '&gt; ' + data.m + "<br />");
            $(".chat").animate({ scrollTop: $('.chat-messages').height() }, "slow");
        });

        // Recieve the responses from commands
        App.Friends.stream.on("response", function(data){
            console.log(data);
//            if (!App.Views.chat.visible){ pulseChat(); }
            $('.chat-messages').append('<br />' + data.r);
            $(".chat").animate({ scrollTop: $('.chat-messages').height() }, "slow");
        });

        // We've connected to chat before authenticating and the
        // server is telling us to reconnect.
        App.Friends.stream.on("reconnect", function(data){
            $('.chat-messages').append('<br />Reconnecting . . .');
            $(".chat").animate({ scrollTop: $('.chat-messages').height() }, "slow");
            App.Friends.connect();
            console.log(data.m);
       });

        // RPC_CHAT event listeners for messages from remote Synchrony instances.
        App.Friends.stream.on("rpc_chat_init", function(data){
            console.log(data);
            if (data.state == "delivered") {
                var message = "The remote side has been notified and is available to chat.<br />";
                $('.chat-messages').append(message);
                $(".chat").animate({ scrollTop: $('.chat-messages').height() }, "slow");
            } else {
                notify(data[1] + " wants to chat");
                // App.Views.chat.socket.emit("join", friend.address);
            }
        });
        App.Friends.stream.on("rpc_chat", function(data){
            console.log(data);
            var message = "&lt;" + data.from[1] + "&gt; " + data.body + "<br />";
            $('.chat-messages').append(message);
            $(".chat").animate({ scrollTop: $('.chat-messages').height() }, "slow");
        });
        App.Friends.stream.on("rpc_chat_close", function(data){
            console.log(data);
        });

        if (App.Config.user){
            App.Views.chat.set("chat_available", true);
        }

    }).then(function(components){
        App.Views.chat.on({
            send: function(event){
                console.log("Sending");
            },

//            Transmit chat messages. this is an on-submit event.
            privmsg: function(event){
                event.original.preventDefault();
                var message = this.get("message");
    
                this.doskeys.push(message);
                App.Views.chat.current_doskey = 1;

                if (message){
                    if (message[0] === "/") {
                        App.Friends.stream.emit('cmd', message.substring(1));
                        console.log(this.get("message"));
                        $('#chat-input').val('');
                        App.Views.chat.set("message", '');
                    } else {
                        var response = App.Friends.stream.emit('msg', message);
                        if (!response.socket.connected) {
                            $('.chat-messages').append("No connection . . .");
                            $(".chat").animate({ scrollTop: $('.chat-messages').height() }, "slow");
                        }
                        console.log(this.get("message"));
                        $('#chat-input').val('');
                        App.Views.chat.set("message", '');
                    }
                }
            },

//            Implements a buffer of entered messages
//            available with the up and down arrow keys
//            Went with the name doskeys instead of buffer etc because it's more descriptive.
            doskeys: function(event){
                if (event.original.keyCode == 38){
                // If up arrow
                var current_line = this.get("message");
                    var doskeys = App.Views.chat.doskeys;
    
                    if (doskeys.length && App.Views.chat.current_doskey <= doskeys.length){
                        var line = App.Views.chat.doskeys[
                            App.Views.chat.doskeys.length - App.Views.chat.current_doskey
                        ];
                        App.Views.chat.set({message: line});
                        App.Views.chat.current_doskey += 1;
                    }

                } 
                else if (event.original.keyCode == 40){
                // If down arrow
                    var doskeys = App.Views.chat.doskeys;
                    if (doskeys.length && App.Views.chat.current_doskey != 1){
                        App.Views.chat.current_doskey -= 1;
                        var line = App.Views.chat.doskeys[
                            App.Views.chat.doskeys.length - App.Views.chat.current_doskey
                        ];
                        App.Views.chat.set({message:line});
                    }
                }
            },

            chat_settings: function(event){
                if ($('.chat-messages').is(':visible')) {
                    $('.chat-messages').hide();
                    $('.chat-settings-panel').show();
                } else {
                    $('.chat-settings-panel').hide();
                    $('.chat-messages').show();
                }
            },

        });
    });
}

function loginView() {
    document.title = "Log in or create an account" + App.title;
    Ractive.load({login: 'login.tmpl'}).then(function(components){
        App.Views['login'] = new components.login({
            el: $('.main'),
            adaptor: ['Backbone']
        });
    }).then(function(components){

        
        // Tell the template whether to display the signup form
        $.get("/v1/users?signups=1", function(response){
            App.Views.login.set("new_accounts", response);
        });
        
        App.Views.login.on({
            login: function(event){

                event.original.preventDefault();

                var username = this.get("username0");
                var pass1    = this.get("pass0");
                App.Views.login.set("message", "Logging in...");
                // Use jQuery to make a PUT to /v1/users/:username/sessions
                $.ajax({
                    type: "PUT",
                    url: "/v1/users/" + username + "/sessions",
                    data: {password: pass1},
                    success: function(data, status){
                        // TODO: Reconnect to active sockets.
                        console.log(data);
                        console.log("Great success");
                        App.Config.user = data;
                        App.Views.synchrony.set("Config", App.Config);
                        location.hash = '';
                    },
                    error: function(data, status){
                        App.Views.login.set("message", "Incorrect username or password.");
                    }
                });

            },
            create: function(event){
                event.original.preventDefault();
                var username = this.get("username1");
                var pass1 = this.get("pass1");
                var pass2 = this.get("pass2");
                var email = this.get("email");
                if (pass1 != pass2 || pass1 == '') {
                    App.Views.login.set("message", "Passwords must match.");
                } else {
                    App.Views.login.set("message", "Give it a minute..");
                    $.ajax({
                        type: "PUT",
                        url: "/v1/users",
                        data: {
                            username: username,
                            password: pass1,
                            email:    email
                        },
                        success: function(data, status){
                            console.log(data);
                            console.log("Great success");
                            App.Views.login.set("message", "Great success.");
                        },
                        error: function(data, status){
                            App.Views.login.set("message", "Server error.");
                        }
                    });
                }
            },
        });
    });
}

function settingsView() {
    document.title = "Settings" + App.title;
    Ractive.load({settings: 'settings.tmpl'}).then(function(components){
        App.Views['settings'] = new components.settings({
            el: $('.main'),
            data: App.Config,
            adaptor: ['Backbone']
        });
    }).then(function(components){

        // Return immediately if no user or they can't see_all
        if (!App.Config.user) {
            location.hash = "login";
            return;
        }

        $.when(
            $.get('/v1/users/' + App.Config.user.username + '?can=see_all', function(response){
                App.Views.settings.set("permitted", response);
            })
        ).done(function(){
            if (App.Views.settings.get("permitted") != true) {
                window.location.hash = "#";
                return;
            }
        });

        // Populate the page.
        // Should be /v1/networks/<name>/peers
        // We use two variables here, peers_permitted and downloads_permitted
        // to determine which sections to display and whether to just navigate
        // away from the view.
        $.when(
            $.get('/v1/users/' + App.Config.user.username + '?can=toggle_signups',
            function(response){
                App.Views.settings.set("toggle_signups_permitted", response);
            }),
             $.get('/v1/users/' + App.Config.user.username + '?can=manage_networks',
            function(response){
                App.Views.settings.set("networks_permitted", response);
            }),
            $.get('/v1/users/' + App.Config.user.username + '?can=browse_peer_nodes',
            function(response){
                App.Views.settings.set("peers_permitted", response);
            }),
            $.get('/v1/users/' + App.Config.user.username + '?can=review_downloads',
            function(response){
                App.Views.settings.set("downloads_permitted", response);
            }),
            $.get('/v1/config', function(response){
                if ("PERMIT_NEW_ACCOUNTS" in response) {
                    App.Views.settings.set({allow_signups: response.PERMIT_NEW_ACCOUNTS});
                }
                if ("OPEN_PROXY" in response) {
                    App.Views.settings.set({open_proxy: response.OPEN_PROXY});
                }
                if ("HTTP_TIMEOUT" in response) {
                    App.Views.settings.set({http_timeout: response.HTTP_TIMEOUT});
                }
                if ("NO_PRISONERS" in response) {
                    App.Views.settings.set({no_prisoners: response.NO_PRISONERS});
                }
                if ("DISABLE_JAVASCRIPT" in response) {
                    App.Views.settings.set({disable_javascript: response.DISABLE_JAVASCRIPT});
                }
            })
        ).done(function(){
            // Navigate away from the view if neither section is permitted
//           if (App.Views.settings.get("peers_permitted") != true &&
//               App.Views.settings.get("downloads_permitted") != true) {
//               window.location.hash = "#";
//           }
        });

        // Ugly but has to be done.
        App.Views.settings.set("accounts_button", "Show");
        App.Views.settings.set("groups_button",   "Show");
        App.Views.settings.set("networks_button", "Show");
        App.Views.settings.set("misc_button",     "Show");

        // Closes the sections if we left some open previously
        App.Views.settings.set("showing_accounts",  undefined);
        App.Views.settings.set("showing_groups",    undefined);
        App.Views.settings.set("showing_networks",  undefined);
        App.Views.settings.set("showing_downloads", undefined);
        App.Views.settings.set("showing_misc",      undefined);

        populate_table(App.Views.settings, "accounts",  "/v1/users");
        populate_table(App.Views.settings, "groups"  ,  "/v1/groups");
        populate_table(App.Views.settings, "downloads", "/v1/revisions/downloads");
        populate_table(App.Views.settings, "networks",  "/v1/networks");

        if (App.Views.settings.get("showing_downloads") === undefined) {
            App.Views.settings.set("downloads_button", "Show");
        } else {
            App.Views.settings.set("downloads_button", "Hide");
        }

        // POST /v1/revisions/downloads/<network>
        App.Views.settings.on({
            // button for show/hide section
            toggle:  function(event, section){
                var button = section + "_button";
                var showing = App.Views.settings.get("showing_" + section);
                if (showing === undefined) {
                    App.Views.settings.set(button, "Hide");
                    App.Views.settings.set("showing_" + section, true);
                } else {
                    App.Views.settings.set(button, "Show");
                    App.Views.settings.set("showing_" + section, undefined);
                }
            },
            // mouseover a url
            select: function(event, type, index){
                if (type === "url") {
                    var network_index = event.node.parentElement.parentElement.id;
                    var network       = App.Views.settings.get("downloads." + network_index);
                    console.log(network.downloads);
                    for (var i = 0; i < network.downloads.length; i++) {
                        var downloads = network.downloads[i];
                        var url = Object.keys(downloads)[0];
                        if (url == index) {
                            // Get downloaded versions of this url (can be multiple hashes)
                            var hashes = new Array();
                            for (j in Object.keys(downloads[url])) {
                                var hash = Object.keys(downloads[url]);
                                hashes.push({"hash": hash[j], "peers": downloads[url][hash[j]]});
                            }
                            var selection = {
                                "network": network.network,
                                "url":  url,
                                "hashes": hashes,
                            };
                            console.log(hashes);
                            App.Views.settings.set("selection", selection);
                        }
                    }
                } else if (type === "network") {
                    console.log(type);
                    console.log(index);
//                    var row = $('#' + type + '-' + index);
                } else if (type == "user") {
                    // If the button's hidden, show the button and hide the text in the
                    // column reporting whether the user account at this index is active
                    if ($('#user-button-' + index).css("display") == "none") {
                        $('#user-button-'  + index).css("display", "inherit");
                        $('#user-text-'  + index).css("display", "none");
                    } else {
                        $('#user-button-'  + index).css("display", "none");
                        $('#user-text-'  + index).css("display", "inherit");
                    }
                }
            },
            forward: function(event, table_type){
                var url = this[table_type].links.next;
                populate_table(App.Views.settings, table_type, url);
            },
            back:    function(event, table_type){
                var url  = this[table_type].links.self.split('page=');
                var page = url[1] - 1;
                populate_table(App.Views.settings, table_type, url[0] + 'page=' + page);
            },
            toggle_signups: function(event, permit){
                if (permit) {
                    $.ajax({
                        url: "/v1/config",
                        type: "POST",
                        data: {"PERMIT_NEW_ACCOUNTS": true},
                        success: function(response){ App.Views.settings.set({allow_signups: true}); },
                        error: function(response){ App.Views.settings.set({allow_signups: false}); }
                    });
               } else {
                    $.ajax({
                        url: "/v1/config",
                        type: "POST",
                        data: {"PERMIT_NEW_ACCOUNTS": null},
                        success: function(response){ App.Views.settings.set({allow_signups: null}); },
                        error: function(response){ App.Views.settings.set({allow_signups: true}); }
                    });
                 }
            },
            toggle_active: function(event, index){
                var accounts = App.Views.settings.get("accounts");
                if (index >= accounts.length) { return; }
                var account  = accounts[index];
                if (account.active) {
                    $.ajax({
                        url: "/v1/users/" + account.username,
                        type: "POST",
                        data: {active: null},
                        success: function(response){
                            accounts[index] = response;
                            App.Views.settings.set("accounts", accounts);
                        },
                        error: function(response){}
                    });
                } else {
                    $.ajax({
                        url: "/v1/users/" + account.username,
                        type: "POST",
                        data: {active: true},
                        success: function(response){
                            accounts[index] = response;
                            App.Views.settings.set("accounts", accounts);
                        },
                        error: function(response){}
                    });
                }
            },
            add_group: function(event){
                if (event.original.keyCode == 13){
                    event.original.preventDefault();
                    var name = this.get("group_name");
                    $.ajax({
                        url: "/v1/groups",
                        type: "PUT",
                        data: {"name": name},
                        success: function(response){
                            response.created = timeStamp(response.created);
                            var groups = App.Views.settings.get("groups");
                            groups.push(response)
                            var groups = upDate(groups);
                            App.Views.settings.set("groups", groups);
                            App.Views.settings.set("group_name", "");
                        },
                        error: function(response){}
                    });
                }
            },
            add_network: function(event){
                if (event.original.keyCode == 13){
                    event.original.preventDefault();
                    var name = this.get("network_name");
                    $.ajax({
                        url: "/v1/networks",
                        type: "PUT",
                        data: {"name": name},
                        success: function(response){
                            var networks = App.Views.settings.get("networks");
                            networks.push(response)
                            App.Views.settings.set("networks", networks);
                            App.Views.settings.set("network_name", "");
                        },
                        error:   function(response){}
                    });
                }
            },
            // clicking a hash to mark as improper
            decrement: function(event, hash){
                var selection = App.Views.settings.get("selection");
                console.log(selection);
                $.ajax({
                    url: "/v1/revisions/downloads/" + selection.network,
                    type: "POST",
                    data: {
                        "url":  selection.url,
                        "hash": hash,
                    },
                    success: function(response){
                        $.get('/v1/peers', function(response){
                            console.log(response.data);
                            App.Views.settings.set("selection", undefined);
                            App.Views.settings.set("peers", response.data);
                        });
                        console.log(response);
                    },
                    error: function(response){
                        var m = "Couldn't contact the server. Please try again later.";
                        App.Views.settings.set("decrement_error", m);
                    },
                });
            },
            toggle_open_proxy: function(event, open){
                if (open) {
                    $.ajax({
                        url: "/v1/config",
                        type: "POST",
                        data: {"OPEN_PROXY": true},
                        success: function(response){ App.Views.settings.set({open_proxy: true}); },
                        error: function(response){ App.Views.settings.set({open_proxy: null}); }
                    });
               } else {
                    $.ajax({
                        url: "/v1/config",
                        type: "POST",
                        data: {"OPEN_PROXY": null},
                        success: function(response){ App.Views.settings.set({open_proxy: null}); },
                        error: function(response){   App.Views.settings.set({open_proy: true}); }
                    });
                 }
            },
            set_http_timeout: function(event){
                event.original.preventDefault();
                var timeout = App.Views.settings.get("http_timeout");
                $.ajax({
                    url: "/v1/config",
                    type: "POST",
                    data: {"HTTP_TIMEOUT": timeout},
                    success: function(response){ 
                        if ("HTTP_TIMEOUT" in response){
                            App.Views.settings.set({http_timeout: response.HTTP_TIMEOUT});
                        }
                    },
                    error: function(response){
                        console.log(response);
                    }
                });
            },
            toggle_no_prisoners: function(event, prisoners){
                if (prisoners) {
                    $.ajax({
                        url: "/v1/config",
                        type: "POST",
                        data: {"NO_PRISONERS": true},
                        success: function(response){ App.Views.settings.set({no_prisoners: true}); },
                        error: function(response){ App.Views.settings.set({no_prisoners: null}); }
                    });
               } else {
                    $.ajax({
                        url: "/v1/config",
                        type: "POST",
                        data: {"NO_PRISONERS": null},
                        success: function(response){ App.Views.settings.set({no_prisoners: null}); },
                        error: function(response){   App.Views.settings.set({no_prisoners: true}); }
                    });
                 }
            },
            toggle_javascript: function(event, enabled){
                if (enabled) { // Note the logical inversion with this one.
                    $.ajax({
                        url: "/v1/config",
                        type: "POST",
                        data: {"DISABLE_JAVASCRIPT": null},
                        success: function(response){ App.Views.settings.set({disable_javascript: null}); },
                        error: function(response){ App.Views.settings.set({disable_javascript: true}); }
                    });
               } else {
                    $.ajax({
                        url: "/v1/config",
                        type: "POST",
                        data: {"DISABLE_JAVASCRIPT": true},
                        success: function(response){ App.Views.settings.set({disable_javascript: true}); },
                        error: function(response){   App.Views.settings.set({disable_javascript: null}); }
                    });
                 }
            },
       });
    });
}

function networkSettingsView(network){
    console.log(network);
    document.title = "Network Settings for " + network + App.title;
    Ractive.load({networksettings: 'networksettings.tmpl'}).then(function(components){
        App.Views['networksettings'] = new components.networksettings({
            el: $('.main'),
            data: App.Config,
            adaptor: ['Backbone']
        });
    }).then(function(components){

        // Return immediately if no user or they can't see_all
        if (!App.Config.user) {
            location.hash = "login";
            return;
        }

        // Again, it's handy that the ?can parameter to /v1/users/<username>
        // returns a truthy response.
        $.when(
            $.get('/v1/users/' + App.Config.user.username + '?can=manage_networks',
            function(response){

                App.Views.networksettings.set("can_manage_networks", response);
            }),
            $.get('/v1/users/' + App.Config.user.username + '?can=browse_peers',
            function(response){
         
                App.Views.networksettings.set("can_browse_peers", response);
            })
         ).done(function(){
            if (App.Views.networksettings.get("can_manage_networks") != true) {
                window.location.hash = "#";
                return;
            }
        });

        // Get peers
        $.get("/v1/networks/" + network + "/peers", function(response){
            console.log(response);
            var peers = upDate(response.data, "last_seen")
            App.Views.networksettings.set("peers", peers); 
        });

        // Get network metadata
        $.get("/v1/networks/" + network, function(response){
            console.log(response);
            App.Views.networksettings.set("network", response); 
        });

        App.Views.networksettings.on({
            select:  function(event, type, index){
                if (type === "network" && index == 0) {
                    if ($('#delete-button').is(':visible')) {
                        $('#delete-button').hide();
                    } else {
                        $('#delete-button').show();
                    }
                }
                var row = $('#' + type + '-' + index);
                var c = row.children();
                c = c[c.length -1];
                if ($('#delete-' + type + '-' + index).css('visibility') === "hidden") {
                    $("#delete-" + type + "-" + index).css("visibility","");
                } else {
                    $("#delete-" + type + "-" + index).css("visibility","hidden");
                }
                // Also show the public key for this node.
                if (type === "peer") {
                    if ($('#pubkey-' + index).css('display') === "none") {
                        $('#pubkey-' + index).css('display', 'inline');
                    } else {
                        $('#pubkey-' + index).css('display', 'none');
                    }
                }
            },
            delete: function(event, type, id) {
                if (type === "network") {
                    var network = this.get("network");
                    $.ajax({
                        url:  "/v1/networks/" + network.name,
                        type: "DELETE",
                        success: function(response){
                            window.location.hash = "settings";
                        },
                        error:   function(response){
                            console.log(response);
                        }
                    });

                } else if (type === "peer") {
                    var peer    = this.get("peers")[id];
                    var network = this.get("network.name");
                    if (peer.node === undefined) { return; }
                    $.ajax({
                        url: "/v1/networks/" + network + "/peers",
                        type: "DELETE",
                        data: {
                            id:   peer.node[0],
                            ip:   peer.node[1],
                            port: peer.node[2]
                        },
                        success: function(response){
                            $('#pubkey-' + id).remove();
                            $('#' + type + '-' + id).remove();
                        },
                        error:   function(response){}
                    });
                }
            },
            add_hosts: function(event) {
                if (event.original.keyCode == 13) {
                    event.original.preventDefault();
                    var hosts   = this.get("hosts");
                    var network = this.get("network");
                    console.log(hosts);
                    // post some hosts
                    $.ajax({
                        url:     "/v1/networks/" + network.name + "/peers",
                        type:    "POST",
                        data:    {"hosts": hosts},
                        success: function(response){
                            console.log(response)
                            var peers = App.Views.networksettings.get("peers");
                            if (peers === undefined) { peers = []; }
                            peers = peers.concat(response);
                            peers = upDate(peers, "last_seen");
                            network.peers += response.length;
                            App.Views.networksettings.set("hosts", "");
                            App.Views.networksettings.set("peers", peers);
                            App.Views.networksettings.set("network.peers", network.peers);
                        },
                        error:   function(response){}
                    });
                }
            },
        });
     });
}
