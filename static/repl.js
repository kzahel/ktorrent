// chrome read eval print loop, included from kaptor uri /status
function dosubmit() {
}


function htmlDecode(input){
  var e = document.createElement('div');
  e.innerHTML = input;
  var val = e.childNodes[0].nodeValue;
  delete e
  return val;
}
function htmlEncode(s)
{
  var el = document.createElement("div");
  el.innerText = el.textContent = s;
  var s = el.innerHTML;
  delete el;
  return s;
}

var cmdhistory = [];
var cur_in_history = 0;

function gotohistory(input, index) {
  //console.log('history',cmdhistory,index);
  input.value = cmdhistory[index] || '';
  var range = input.createTextRange;
  if (range) {
    range = range();
    range.moveEnd('character',input.value.length);
    range.moveStart('character',0);
    console.log('selecting ranges');
    range.select();
  }
}

function keydown(input, event) {
  if (event.which == 13 || event.keyIdentifier == 'Enter') {
    url = window.location.protocol + '//' + window.location.host + '/statusv2';
    console.log(url);

    var xhr = new XMLHttpRequest();
    xhr.onreadystatechange = function() {
      if (xhr.readyState == 4) {
        console.log(xhr.getAllResponseHeaders());
        console.log(xhr.responseText);
        var span = document.createElement('div');
        span.setAttribute('style','margin:0.5em; background: #def; padding: 0.5em; border: 1px solid grey');
        span.innerHTML = htmlEncode(xhr.responseText);
        var output = document.getElementById('output');
        if (output.firstChild) {
          output.insertBefore( span, output.firstChild );
        } else {
          output.appendChild( span );
        }
      }
    }
    xhr.open('POST', url, true)
    var body = 'qs='+encodeURIComponent(input.value);
    xhr.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
    //xhr.setRequestHeader("Content-Length", body.length);
    xhr.send(body);
    cmdhistory.push(input.value);
    input.value = '';
    cur_in_history = cmdhistory.length-1;
  } else if (event.which == 38 || event.keyIdentifier == 'Up') {
    cur_in_history -= 1;
    gotohistory(input, cur_in_history);
  } else if (event.which == 40 || event.keyIdentifier == 'Down') {
    cur_in_history += 1;
    gotohistory(input, cur_in_history);
  }



}


if (window.location.hash.match('refresh')) {
  setTimeout( function() {window.location.reload()}, 50 );
}
