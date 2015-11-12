// Extend Backbone.Router to support before: and after:
Backbone.Router.prototype.before = function () {};
Backbone.Router.prototype.after = function () {};

Backbone.Router.prototype.route = function (route, name, callback) {
  if (!_.isRegExp(route)) route = this._routeToRegExp(route);
  if (_.isFunction(name)) {
    callback = name;
    name = '';
  }
  if (!callback) callback = this[name];

  var router = this;

  Backbone.history.route(route, function(fragment) {
    var args = router._extractParameters(route, fragment);

    router.before.apply(router, arguments);
    callback && callback.apply(router, args);
    router.after.apply(router, arguments);

    router.trigger.apply(router, ['route:' + name].concat(args));
    router.trigger('route', name, args);
    Backbone.history.trigger('route', router, name, args);
  });
  return this;
};


// Mousenter and mouseleave extensions for Ractive.js
Ractive.events.mouseenter = function ( node, fire ) {
    node.addEventListener( 'mouseover', mouseoverHandler, false );
    
    return {
        teardown: function () {
            node.removeEventListener( 'mouseover', mouseoverHandler, false );
        }
    };
    
    function mouseoverHandler ( event ) {
        if ( !node.contains( event.relatedTarget ) ) {
            fire({ node: node, original: event });
        }
    }
};

Ractive.events.mouseleave = function ( node, fire ) {
    node.addEventListener( 'mouseout', mouseoutHandler, false );
    
    return {
        teardown: function () {
            node.removeEventListener( 'mouseout', mouseoutHandler, false );
        }
    };
    
    function mouseoutHandler ( event ) {
        if ( !node.contains( event.relatedTarget ) ) {
            fire({ node: node, original: event });
        }
    }
};

/*
function timeStamp() {
// Found this handy snippet at https://gist.github.com/hurjas/2660489
// Create a date object with the current time
  var now = new Date(); 
// Create an array with the current month, day and time
  var date = [ now.getDate(), now.getMonth() + 1, now.getFullYear() ];
// Create an array with the current hour, minute and second
  var time = [ now.getHours(), now.getMinutes(), now.getSeconds() ];
// Determine AM or PM suffix based on the hour
  var suffix = ( time[0] < 12 ) ? "AM" : "PM";
// Convert hour from military time
  time[0] = ( time[0] < 12 ) ? time[0] : time[0] - 12;
// If hour is 0, set it to 12
  time[0] = time[0] || 12;
// If seconds and minutes are less than 10, add a zero
  for ( var i = 1; i < 3; i++ ) {
    if ( time[i] < 10 ) {
      time[i] = "0" + time[i];
    }
  }
// Return the formatted string
  return date.join("/") + " " + time.join(":") + " " + suffix;
}
*/

function timeStamp(ts) {
	var m = moment.unix(ts);
	return m.format('MMMM Do YYYY, h:mm:ss A');

}
