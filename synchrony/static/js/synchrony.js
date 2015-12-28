/* 
   Synchrony 0.0.1
   A soft-realtime collaborative hyperdocument editor.
   Copyright Luke Brooks 2015

TODO:

/request/:url      Raw resource
/#request/:url     JavaScript to load /request/:url into .content

The iframe in .content will navigate around a site
the /request/:url endpoint merely needs to remove javascript so as not to interfere with the window object.
We can then monitor events in the iframe.


 Global stream [Notify of remote sign-ins]
 localStorage controls
 Administrative chat controls.
 Ownership data.
 Allow owners to toggle public flag on revisions
 document group revision limit
 whichever threshold is met first
 formatted JSON event messages,
 {d:title, +chr@46,r:hash,s:[usernames]}
 OT, hash content, compare, major sync if necessary.
 An awareness of revision histories in streaming
 An awareness of page deletions in streaming
 Reduce the amount of objects used
 Account View (sessions, bio, undelete)
 Account Pages View (search, histories)
 Renaming based on checking availability
 A favicon.ico
 Compress the javascript includes to a single file.

 Use /#settings to toggle:
  * Preferred peers.
  * Whether to transmit browsing activity.
    The default setting for User objects is to be private.
    This means not transmitting newly saved objects.

*/

// App init
(function(){
    window.App = {
        Config:        {},
        Views:         {},
        stream:        [],
        history:       [],
        title: " - Synchrony",
    }

    // Ask the server who we are.
    $.get("/v1/users?me=1", function(data, status){
        App.Config.user = data;
    });

//    var m = new moment();
//    if (m.hour() >= 20 || m.hour() <= 6){
        setTimeout(function(){
            $('.main').addClass("after-hours");
        }, 50);
//    }

})();

// Tell Ractive.load where our mustache templates live.
Ractive.load.baseUrl = '/static/templates/';

// Tell Backbone where our API endpoints are for documents.
App.Revision  = Backbone.Model.extend({urlRoot: '/v1/revisions' });
App.Revisions = Backbone.Collection.extend({
    model: App.Document,
    url: '/v1/revisions',
    paginate: function(perPage, page) {
        page = page - 1;
        var collection = this;
        collection = _(collection.rest(perPage*page));
        collection = _(collection.first(perPage));    
        return collection.map( function(model) { return model.toJSON() }); 
    },
});

//  URL hashes -> attributes on this router
App.Router = Backbone.Router.extend({
    routes: {
        '':                    'index',
//        'request':             'requestindex',
//        'request/:resource':   'requestresource',
        'user/:username':      'userview',
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
        if (location.hash != '') {
            $('.main').removeClass("main_background");
        }
        update_synchrony();
    },
});

// Our error handler prints to the stream for ten seconds
function renderError(statement) {
    console.log('Error: ' + statement);
    App.stream.push(statement);
    setTimeout(function(){ App.stream.pop(); }, 10000);
}

// Push a global message to the stream for eight seconds
function renderGlobal(statement) {
    console.log('Global: ' + statement);
    App.stream.reverse();
    App.stream.push( '<span class="global-message">' + statement + '</span>' );
    App.stream.reverse();
    setTimeout(function(){
        App.stream.pop();
        App.stream.reverse();
    }, 60000);
}

// Push $user is typing to the stream for three seconds
function renderTyping(statement) {
    App.stream.push( '<span class="global-message">' + statement + '</span>' );
    setTimeout(function(){ App.stream.pop(); }, 1000);
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

function notify(message){
    if (!"Notification" in window) { return; }
    if (Notification.permission != "granted") {
        Notification.requestPermission();
    }
    var options = {icon:'/static/img/synchrony.png'};
    var notification = new Notification(message, options);
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
    } else {
        App.Views.synchrony.set("showing_edit_button", false);
        App.Views.synchrony.set("showing_hide_button", false);
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
    if (event.original.keyCode == 13){
        event.original.preventDefault();

        // Grab the iframe div
        var iframe = $('.iframe');

        // Remove any schema from the url
        var url = this.get("url");
        if (url.indexOf("://") > -1){
                url = url.slice(url.indexOf("://")+3, url.length);
        }
        if ($('.main').is(':visible')) {
            toggleMain();
        }

        function update_address_bars(url) {
            location.hash = "request/" + url;
            if (App.Views.index != undefined) {
                App.Views.index.set({url: url});
            }
            if (App.Views.synchrony != undefined) {
                App.Views.synchrony.set({url: url});
            }
        }
        
        update_address_bars(url);
        App.history.push(url);

        $('iframe').contents().find('body').html("Loading...");

        $.ajax({
            type: "GET",
            url: "/request/" + url,
            success: function(data, status){
                iframe.contents().find('body').html(data);

                // Bind a callback to anchor tags so their href attribute
                // is appended to App.history when clicked.
                iframe.contents().find('a').on('click', function(){
                    var url = $(this).attr('href').split('/');
                    url     = url.slice(2, url.length).join('/');
                    App.history.push(url);
                    update_address_bars(url);
                });
                // Also caching the unedited document in the event it's ever
                // sent directly over webrtc.
                App.document = data;

                update_synchrony();
            },
            error: function(data, status){
                var message = "There was an error loading this resource.";
                message = message + " Consult the logs for further explanation."
                iframe.contents().find('body').html(message);
            }
        });
    }
}

// Start the Backbone URL hash monitor
new App.Router();
Backbone.history.start();

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
            back:    function(event){
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

        // This function is pretty general in terms of populating tables
        function populate_table(table_type, url){
            // Grab the data
            $.get(url, function(data){
                // Update the DOM on success
                App.Views.userpage.set(table_type + "_paging_error", undefined);
                data.data = upDate(data.data, "created");
                App.Views.userpage.set(table_type, data.data);
                App.Views.userpage[table_type] = data;

                // Show navigation links depending on the response data
                // This is where the jsonapi.org style of {links: {next: "http://"}}
                // comes in handy.
                if (data.links.hasOwnProperty("self")) {
                    var url = data.links.self.split('page=')[1];
                    if (url != undefined) {
                        if (url > 1) {
                            App.Views.userpage.set(table_type + "_back_available", true);
                        } else {
                            App.Views.userpage.set(table_type + "_back_available", false);
                        }
                    } 
                }

                if (data.links.hasOwnProperty("next")) {
                    App.Views.userpage.set(table_type + "_forward_available", true);
                }
            }).fail(function(){
               App.Views.userpage.set(table_type + "_paging_error", true);
            });
        }

        // Populate the user address line
        $.get('/v1/networks', function(response){
            if (response.data.length > 0){
                var addresses = [];
                for (var i = 0; i < response.data.length; i++) {
                    var address = response.data[i].name + "/" + response.data[i].node_id;
                    address     = address + "/" + App.Config.user.uid;
                    addresses.push(address);
                }
                App.Views.userpage.set("user_addresses", addresses);
            }
        });

        // Determine whether this is a profile or settings page.
        if (App.Config.user.username != username) {
//            populate_table("revisions", "/v1//user/" + username + "/revisions");
        } else {
            // Ugliest section in the file, but this stuff has to be somewhere
            App.Views.userpage.set("show_settings",     true);
            App.Views.userpage.set("sessions_button",   "Show");
            App.Views.userpage.set("revisions_button",  "Show");
            App.Views.userpage.set("friends_button",    "Show");
            App.Views.userpage.set("password_button",   "Show");
            App.Views.userpage.set("showing_sessions",  undefined);
            App.Views.userpage.set("showing_revisions", undefined);
            App.Views.userpage.set("showing_friends",   undefined);
            App.Views.userpage.set("showing_password",  undefined);

            populate_table("revisions", "/v1/users/" + username + "/revisions");
            populate_table("friends",   "/v1/users/" + username + "/friends");
            populate_table("sessions",  "/v1/users/" + username + "/sessions");
        }

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
                populate_table(table_type, url);
            },
            back:    function(event, table_type){
                var url = this[table_type].links.self.split('page=');
                var page = url[1] - 1;
                populate_table(table_type, url[0] + 'page=' + page);
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
                }
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
                    if (friend.status == "Blocked"){
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

Ractive.load({
    content:   'content.tmpl',
    synchrony: 'synchrony.tmpl',

}).then(function(components){

/*
    This is the content area of the page that holds external resources in an iframe
    it's loaded here so it can be displayed at all times alongside SPA templates.

*/    App.Views['content'] = new components.content({
        el: $('.content'),
        data: {events: App.stream},
        adaptor: ['Backbone'],
    });
/*
 * The current strategy revolves around subscribing to a channel named "public"
 * though this could just as well be a User UID to follow them through their
 * use of the proxy.
 *
 * DOM nodes are matched up to two parent nodes and changes are then reintegrated
 * where they're found to match. This strategy is not terribly effective /right now/
 * but is generally better than transmitting the entire document.
 *
 * The hardest fragment to match is a single character that's the only inhabitant of
 * its surrounding nodes.
 *
 * The protocol appears to want two major message types: "document" and "fragment"
 * where "document" is the entire tree and "fragment" is a subtree.
 *
 * This should be as simple as doing dom.patch(subtree)
 *
 */
    App.Views.content.socket = io.connect('/documents', {resource: "stream"})
    App.Views.content.socket.emit('subscribe', 'public')
    App.Views.content.socket.on("fragment", function(data){
        // Someone is sending us some DOM nodes.
        console.log(data);
        parser = new DOMParser();
        doc = parser.parseFromString(data.document, "text/xml");
        // Clean out errors found by the parser.
        var element = doc.getElementsByTagName("parsererror");
        for (index = element.length - 1; index >= 0; index--) {
                element[index].parentNode.removeChild(element[index]);
        }
        console.log(doc);
        console.log(element);
        var doc_text = $(doc).text();
        console.log("doc_text: "+ doc_text);
//        window.doc = doc;
        var nodes = "";
        var text_data = "";
//        doc.children[0].className
        nodes = nodes + doc.children[0].nodeName
        if (doc.children[0].children) {
            nodes = nodes + ' ' + doc.children[0].children[0].nodeName
            if (doc.children[0].children[0].children) {
                nodes = nodes + ' ' + doc.children[0].children[0].children[0].nodeName
                text_data = doc.children[0].children[0].children[0].innerHTML
            } else {
                text_data = doc.children[0].children[0].innerHTML
            }
        } else {
            text_data = doc.children[0].innerHTML
        }
        console.log("nodes: " + nodes);
        console.log("text_data: " + text_data);
        var length = text_data.length;
        // First half
        var c = $('.iframe').contents().find(nodes + ':contains(' + text_data.slice(0,Math.ceil(length / 2)) + ')');
        var swapped = $('.iframe').contents().find(nodes + ':contains(' + text_data.slice(0,Math.ceil(length / 2)) + ')').first().html(data.document);
        console.log("swap attempt 1:");
        console.log(swapped.length);
        console.log(swapped.text());
        // Second half
        if (swapped.length != 1) {
            c.push.apply(c, $('.iframe').contents().find(nodes + ':contains(' + text_data.slice(Math.ceil(length / 2), length) + ')'));
            var swapped = $('.iframe').contents().find(nodes + ':contains(' + text_data.slice(Math.ceil(length / 2), length) + ')').first().html(data.document);
            console.log("swap attempt 2:")
            console.log(swapped.length);
            console.log(swapped.text());
        }
        console.log("c: " + c.length);
        console.log(c);
        for (var i = 0; i < c.length; i++) {
            console.log($(c[i]).text());
        }
    });

//    Only transmit when textnode characters have been modified
    $('.iframe').contents().find('body').on('DOMCharacterDataModified', function(event){
//        Traverse to up to two parent elements and transmit the outerHTML.
        if (event.target.parentElement) {
            if (event.target.parentElement.parentElement) {
                edit_data = event.target.parentElement.parentElement.outerHTML;
            } else {
                edit_data = event.target.parentElement.outerHTML;
            }
        } else {
            edit_data = event.target.outerHTML;
        }
        
        App.Views.content.socket.emit('edit', edit_data);

        console.log(event);
        App.e = event;
    });

/*
    App.Views['results'] = new components.results({
        el: $('.results'),
        adaptor: ['Backbone'],
    });
    $('.results').hide();
    $('.results').click(function(){
        App.Views.search.set('term', '');
    });
*/
    // Search bar and an event handler for searching on input
    App.Views['synchrony'] = new components.synchrony({
        el: $('.synchrony'),
        data: {
        Config: App.Config,
        edit_button:"Edit",
        stream: App.stream,
        },
        adaptor: ['Backbone'],
    });

    App.Views.synchrony.socket = io.connect('/global', {resource:"stream"});
    App.Views.synchrony.socket.emit('join', "global");
    App.Views.synchrony.socket.on("message", function(data){
        App.stream.push(data.message);
        setTimeout(function(){ App.stream.pop(); }, 1000)
    });

    App.Views.synchrony.on({
        request: request, // Globally available request function

        edit: function(event){
            if ($('.edit_button').hasClass('active_button')) {
                $('.edit_button').removeClass('active_button');
            } else {
                $('.edit_button').addClass('active_button');
            }
            iframe = $('.iframe');
            var attr = iframe.contents().find('body').attr('contenteditable');
//            console.log(attr);
            if (typeof attr === typeof undefined || attr == false || attr == "false") {
                iframe.contents().find('body').attr('contenteditable','true');
                iframe.contents().find('body').attr('autocorrect','false');
                iframe.contents().find('body').attr('spellcheck','false');
                App.Views.synchrony.set('edit_button', "Done");
                $('.edit_button').html("Done");
           } else {
                iframe.contents().find('body').attr('contenteditable','false');
                App.Views.synchrony.set('edit_button', "Edit");
                $('.edit_button').html("Edit");
            }
        },
        settings:  function(event){
            window.location.hash = "#settings";
        },
        sessions:  function(event){
            window.location.hash = "#sessions";
        },
        show_hide: function(event){ // Show/hide the .main panel over content
            toggleMain();
        },
        chat:      function(event){
            window.location.hash = "#chat";
        },
        logout:    function(event){
            $.ajax({
                url:     "/v1/users/" + App.Config.user.username + "/sessions",
                type:    "DELETE",
                data:    {timestamp: App.Config.user.session.created},
                success: function(data){
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
            data: {chat_available:true},
            adaptor: ['Backbone']
        });
        
        if (!App.Config.user) {
            location.hash = "login";
        }
       
        $('.chat').draggable();
        var welcome_message = "Use <em>/help</em> to see a list of commands.<br />";
        $('.chat-messages').append(welcome_message);

        App.Views.chat.visible = false;

        // An array of messages typed into the input field.
        App.Views.chat.doskeys = [];
        App.Views.chat.current_doskey = 0;

        // Join the public channel and listen for messages
        App.Views.chat.socket = io.connect('/chat', {resource:"stream"});
        App.Views.chat.socket.emit('join', '#public');

        // Recieve chat messages.
        App.Views.chat.socket.on("privmsg", function(data){
            console.log(data);
//            if (!App.Views.sidebar.visible){ pulseSidebar(); }
//            The anonymous flag is for if you've permitted unsigned-up users to chat
//            via the auth server.
//            data = {m:message, u:username, a:anonymous_flag}
            $('.chat-messages').append('&lt;' + linkUser(data.u) + '&gt; ' + data.m + "<br />");
            $(".chat").animate({ scrollTop: $('.chat-messages').height() }, "slow");
        });

        // Recieve the responses from commands
        App.Views.chat.socket.on("response", function(data){
            console.log(data);
//            if (!App.Views.chat.visible){ pulseChat(); }
            $('.chat-messages').append('<br />' + data.r);
            $(".chat").animate({ scrollTop: $('.chat-messages').height() }, "slow");
        });

        // Server disappeared. TODO: Set a reconnect timer here.
//        App.Views.chat.socket.on("disconnect", function(data){
//            console.log(data);
//            App.Views.chat.set("chat_available", false);
//            App.Views.chat.set("chat_error", data.message);
//        });

        // We've connected to chat before authenticating and the
        // server is telling us to reconnect.
        App.Views.chat.socket.on("reconnect", function(data){
            $('.chat-messages').append('<br />Reconnecting...');
            $(".chat").animate({ scrollTop: $('.chat-messages').height() }, "slow");
            // Actually recreate the connection to re-auth.
            // Using chat.socket.disconnect and socket.connect doesn't work.
            App.Views.chat.socket.disconnect();
            delete App.Views.chat.socket;
            App.Views.chat.socket = io.connect('/chat', {resource:"stream"});
            console.log(data.m);
       });

        App.Views.chat.socket.on("appear_offline", function(data){
            $('[name="appear_offline"]').attr("checked", data);
        });

        // RPC_CHAT event listeners for messages from remote Synchrony instances.
        App.Views.chat.socket.on("rpc_chat_init", function(data){
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
        App.Views.chat.socket.on("rpc_chat", function(data){
            console.log(data);
            var message = "&lt;" + data.from[1] + "&gt; " + data.body + "<br />";
            $('.chat-messages').append(message);
            $(".chat").animate({ scrollTop: $('.chat-messages').height() }, "slow");
        });
        App.Views.chat.socket.on("rpc_chat_close", function(data){
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
                        App.Views.chat.socket.emit('cmd', message.substring(1));
                        console.log(this.get("message"));
                        $('#chat-input').val('');
                        App.Views.chat.set("message", '');
                    } else {
                        App.Views.chat.socket.emit('msg', message);
                        console.log(this.get("message"));
                        $('#chat-input').val('');
                        App.Views.chat.set("message", '');
                    }
                }
            },

            chat_appear_offline: function(event){
//                event.original.preventDefault();
                console.log(event);
                var appearing_offline = this.get("appearing_offline");
                console.log(appearing_offline)
                // We've prevented the default, so transmit the inverse,
                // as it's the state the user is aiming for
                if (appearing_offline){
                    App.Views.chat.socket.emit("appear_offline", 0);
                } else {
                    App.Views.chat.socket.emit("appear_offline", 1);
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
                        App.Views.chat.set({message:line});
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
                            email: email
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
            $.get("/v1/users?signups=1", function(response){
                if (response == true) {
                    App.Views.settings.set({signups_allow: true});
                } else {
                    App.Views.settings.set({signups_deny: true});
                }
            }),
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
        App.Views.settings.set("open_button",     "Show");

        // Closes the sections if we left some open previously
        App.Views.settings.set("showing_accounts",  undefined);
        App.Views.settings.set("showing_groups",    undefined);
        App.Views.settings.set("showing_networks",  undefined);
        App.Views.settings.set("showing_downloads", undefined);
        App.Views.settings.set("showing_open",      undefined);

        // Populate the view
//        $.get('/v1/peers', function(response){
//            console.log(response.data);
//            App.Views.peers.set("peers", response.data);
//        });

        $.get('/v1/revisions/downloads', function(response){
            App.Views.settings.set("downloads", response.data);
        });

        $.get('/v1/networks', function(response){
            App.Views.settings.set("networks", response.data);
        });

//       if (App.Views.settings.get("showing_peers") === undefined) {
//           App.Views.settings.set("peers_button","Hide");
//           App.Views.settings.set("showing_peers",true);
//       }

        if (App.Views.settings.get("showing_downloads") === undefined) {
            App.Views.settings.set("downloads_button", "Show");
        } else {
            App.Views.settings.set("downloads_button", "Hide");
        }

        // POST /v1/revisions/downloads/<network>
        // {reason: integer_severity_level}
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
                }
            },
            toggle_signups: function(event, permit){
                if (permit) {
                    $.ajax({
                        url: "/v1/users",
                        type: "POST",
                        data: {signups: true},
                        success: function(response){
                            App.Views.settings.set({signups_allow: true});
                            App.Views.settings.set({signups_deny: null});
                         },
                        error:   function(response){
                            App.Views.settings.set({signups_allow: true});
                            App.Views.settings.set({signups_deny: null});
                         }
                    });
               } else {
                    $.ajax({
                        url: "/v1/users",
                        type: "POST",
                        data: {signups: null},
                        success: function(response){
                            App.Views.settings.set({signups_allow: null});
                            App.Views.settings.set({signups_deny: true});
                         },
                        error:   function(response){
                            App.Views.settings.set({signups_allow: true});
                            App.Views.settings.set({signups_deny: null});
                         }
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
                        "severity": 1
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
